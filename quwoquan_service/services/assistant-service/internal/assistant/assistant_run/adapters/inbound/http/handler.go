// Package http is the AssistantRun inbound adapter. AssistantRun owns its own
// transport boundary so run commands, the run event journal and the run SSE
// stream never travel through AssistantSession orchestration.
package http

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	rtfailures "quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/streaming"
	runerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_run"
	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/streaming"
)

const (
	runEventPollInterval  = 250 * time.Millisecond
	runEventHeartbeat     = 15 * time.Second
	runEventPageSize      = 500
	runRequestBodyMaxSize = 1 << 20
	// streamRunEventsOperationID is the canonical operation whose declared
	// reliability.stream_budget bounds the run event stream.
	streamRunEventsOperationID = "assistant.assistant_run.StreamAssistantRunEvents"
)

// runEventStreamBudget is derived from the generated descriptor for
// StreamAssistantRunEvents. Writing these three durations as literals here is
// exactly how a transport value ends up preempting the contract, so this fails
// at wiring time when the operation declares no stream budget instead of
// falling back to a hand-picked default.
var runEventStreamBudget = rtauth.StreamBudgetForOperation(
	operationsecurity.ForDomain("assistant"),
	streamRunEventsOperationID,
)

// RunEventStreamBudget is the contract-declared handshake, idle and connection
// lifetime the run event stream enforces.
func RunEventStreamBudget() rtauth.OperationStreamBudget {
	return runEventStreamBudget
}

type Handler struct {
	commands     *runruntime.CommandService
	runs         *runapplication.UseCases
	preferences  runapplication.PreferenceSnapshotReader
	context      *runapplication.ContextResolver
	streamBudget rtauth.OperationStreamBudget
}

type HandlerOption func(*Handler)

func WithPreferenceSnapshots(reader runapplication.PreferenceSnapshotReader) HandlerOption {
	return func(handler *Handler) { handler.preferences = reader }
}

func WithContextResolver(resolver *runapplication.ContextResolver) HandlerOption {
	return func(handler *Handler) { handler.context = resolver }
}

// WithRunEventStreamBudget scales the contract-declared stream budget so tests
// can observe each bound firing without waiting out the production connection
// lifetime. Production composition must never pass it: the default is the only
// value derived from the operation descriptor.
func WithRunEventStreamBudget(
	budget rtauth.OperationStreamBudget,
) HandlerOption {
	return func(handler *Handler) { handler.streamBudget = budget }
}

func NewHandler(
	commands *runruntime.CommandService,
	options ...HandlerOption,
) *Handler {
	handler := &Handler{
		commands:     commands,
		streamBudget: runEventStreamBudget,
	}
	for _, option := range options {
		option(handler)
	}
	if handler.commands != nil {
		handler.runs = runapplication.NewUseCases(
			handler.commands,
			runapplication.WithPreferenceSnapshots(handler.preferences),
			runapplication.WithContextResolver(handler.context),
		)
	}
	return handler
}

// RegisterRoutes binds every AssistantRun api_route declared by
// contracts/assistant/assistant_run/operations.yaml.
func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /assistant/sessions/{sessionId}/runs", h.handleStartRun)
	mux.HandleFunc("GET /assistant/runs/{runId}", h.handleGetRun)
	mux.HandleFunc("POST /assistant/runs/{runId}/cancel", h.handleCancelRun)
	mux.HandleFunc("POST /assistant/runs/{runId}/pause", h.handlePauseRun)
	mux.HandleFunc("POST /assistant/runs/{runId}/resume", h.handleResumeRun)
	mux.HandleFunc("POST /assistant/runs/{runId}/steer", h.handleSteerRun)
	mux.HandleFunc(
		"POST /assistant/runs/{runId}/tool-invocations/{toolInvocationId}/approval",
		h.handleApproveToolUse,
	)
	mux.HandleFunc(
		"POST /assistant/runs/{runId}/tool-invocations/{toolInvocationId}/device-action-receipt",
		h.handleSubmitDeviceActionReceipt,
	)
	mux.HandleFunc("GET /assistant/runs/{runId}/events", h.handleStreamRunEvents)
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	h.RegisterRoutes(mux)
	return mux
}

// requireRunUser resolves the run owner from the JWT principal or the
// allowlisted trusted identity header; metadata declares auth_mode: required
// with actor persona, so an unidentified caller is rejected instead of
// falling back to anonymous.
func requireRunUser(r *http.Request) (string, error) {
	if claims, ok := rtauth.PrincipalFromContext(r.Context()); ok &&
		strings.TrimSpace(claims.Subject) != "" {
		return strings.TrimSpace(claims.Subject), nil
	}
	if uid := strings.TrimSpace(r.Header.Get("X-Client-User-Id")); uid != "" {
		return uid, nil
	}
	return "", runerrors.AppErrorFromRunUnauthorized(
		"assistant run requires an identified persona",
	)
}

// requireRunCommandIdentity enforces the one stable mutation identity declared
// by AssistantRun command metadata. The body identifies the aggregate replay
// key; the HTTP header lets middleware, traces and retrying transports observe
// the same key. Accepting either one alone would create two divergent
// idempotency paths.
func requireRunCommandIdentity(
	r *http.Request,
	clientRequestID string,
) (string, error) {
	bodyID := strings.TrimSpace(clientRequestID)
	if bodyID == "" {
		return "", runerrors.AppErrorFromRunInvalidArgument("missing clientRequestId")
	}
	headerID := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if headerID == "" {
		return "", runerrors.AppErrorFromRunInvalidArgument("missing Idempotency-Key")
	}
	if headerID != bodyID {
		return "", runerrors.AppErrorFromRunInvalidArgument(
			"clientRequestId does not match Idempotency-Key",
		)
	}
	return bodyID, nil
}

// requireInjectedRunCommandIdentity serves the run commands whose replay key is
// carried only by the transport header.
func requireInjectedRunCommandIdentity(r *http.Request) (string, error) {
	requestID := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if requestID == "" {
		return "", runerrors.AppErrorFromRunInvalidArgument("missing Idempotency-Key")
	}
	return requestID, nil
}

func (h *Handler) handleStartRun(w http.ResponseWriter, r *http.Request) {
	userID, err := requireRunUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	runs, err := h.requireRunUseCases()
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	var input runapplication.StartInput
	if err := readJSON(r, &input); err != nil {
		writeHTTPError(w, r, runerrors.AppErrorFromRunInvalidArgument(err.Error()))
		return
	}
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok || strings.TrimSpace(principal.Actor.PersonaID) == "" {
		writeHTTPError(
			w,
			r,
			runerrors.AppErrorFromRunUnauthorized(
				"StartAssistantRun requires a trusted persona principal",
			),
		)
		return
	}
	input.TrustedPersonaID = strings.TrimSpace(principal.Actor.PersonaID)
	input.TrustedRequestContext = runruntime.RequestContext{
		ClientSessionID: r.Header.Get("X-Client-Session-Id"),
		PageID:          r.Header.Get("X-Client-Page-Id"),
		SurfaceID:       r.Header.Get("X-Client-Surface-Id"),
		RouteID:         r.Header.Get("X-Client-Route-Id"),
		OperationID:     r.Header.Get("X-Client-Operation-Id"),
		TraceID:         resolveTraceID(r),
		PersonaID:       input.TrustedPersonaID,
	}
	input.ClientRequestID, err = requireRunCommandIdentity(r, input.ClientRequestID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	run, err := runs.Start(
		r.Context(),
		userID,
		r.PathValue("sessionId"),
		resolveTraceID(r),
		input,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	log.Printf(
		"assistant http start_run sessionId=%s runId=%s traceId=%s",
		run.SessionID,
		run.RunID,
		run.TraceID,
	)
	writeJSON(w, http.StatusCreated, projectAssistantRunEnvelope(run))
}

func (h *Handler) handleGetRun(w http.ResponseWriter, r *http.Request) {
	userID, err := requireRunUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	runs, err := h.requireRunUseCases()
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	run, err := runs.Get(r.Context(), userID, r.PathValue("runId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, projectAssistantRunEnvelope(run))
}

func (h *Handler) handleCancelRun(w http.ResponseWriter, r *http.Request) {
	userID, err := requireRunUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	runs, err := h.requireRunUseCases()
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	commandID, err := requireInjectedRunCommandIdentity(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	run, err := runs.Cancel(
		r.Context(),
		userID,
		r.PathValue("runId"),
		commandID,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	log.Printf(
		"assistant http cancel_run runId=%s status=%s",
		run.RunID,
		run.State,
	)
	writeJSON(w, http.StatusOK, projectAssistantRunEnvelope(run))
}

func (h *Handler) handlePauseRun(w http.ResponseWriter, r *http.Request) {
	userID, err := requireRunUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	runs, err := h.requireRunUseCases()
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	var input runapplication.PauseInput
	if err := readJSON(r, &input); err != nil {
		writeHTTPError(w, r, runerrors.AppErrorFromRunInvalidArgument(err.Error()))
		return
	}
	commandID, err := requireInjectedRunCommandIdentity(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	run, err := runs.Pause(
		r.Context(),
		userID,
		r.PathValue("runId"),
		commandID,
		input,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, projectAssistantRunEnvelope(run))
}

func (h *Handler) handleResumeRun(w http.ResponseWriter, r *http.Request) {
	userID, err := requireRunUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	runs, err := h.requireRunUseCases()
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	commandID, err := requireInjectedRunCommandIdentity(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	run, err := runs.Resume(
		r.Context(),
		userID,
		r.PathValue("runId"),
		commandID,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, projectAssistantRunEnvelope(run))
}

func (h *Handler) handleSteerRun(w http.ResponseWriter, r *http.Request) {
	userID, err := requireRunUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	runs, err := h.requireRunUseCases()
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	var input runapplication.SteerInput
	if err := readJSON(r, &input); err != nil {
		writeHTTPError(w, r, runerrors.AppErrorFromRunInvalidArgument(err.Error()))
		return
	}
	commandID, err := requireInjectedRunCommandIdentity(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	run, err := runs.Steer(
		r.Context(),
		userID,
		r.PathValue("runId"),
		commandID,
		input,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, projectAssistantRunEnvelope(run))
}

func (h *Handler) handleApproveToolUse(w http.ResponseWriter, r *http.Request) {
	userID, err := requireRunUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	runs, err := h.requireRunUseCases()
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	var input runapplication.ApproveToolUseInput
	if err := readJSON(r, &input); err != nil {
		writeHTTPError(w, r, runerrors.AppErrorFromRunInvalidArgument(err.Error()))
		return
	}
	commandID, err := requireInjectedRunCommandIdentity(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	run, permit, err := runs.ApproveToolUse(
		r.Context(),
		userID,
		r.PathValue("runId"),
		r.PathValue("toolInvocationId"),
		commandID,
		input,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"runId":              run.RunID,
		"state":              run.State,
		"deviceActionPermit": permit,
	})
}

func (h *Handler) handleSubmitDeviceActionReceipt(
	w http.ResponseWriter,
	r *http.Request,
) {
	userID, err := requireRunUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	runs, err := h.requireRunUseCases()
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	var input runapplication.DeviceActionExecutionReceiptInput
	if err := readJSON(r, &input); err != nil {
		writeHTTPError(w, r, runerrors.AppErrorFromRunInvalidArgument(err.Error()))
		return
	}
	commandID, err := requireInjectedRunCommandIdentity(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	run, err := runs.SubmitDeviceActionReceipt(
		r.Context(),
		userID,
		r.PathValue("runId"),
		r.PathValue("toolInvocationId"),
		commandID,
		input,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, projectAssistantRunEnvelope(run))
}

func (h *Handler) handleStreamRunEvents(w http.ResponseWriter, r *http.Request) {
	runID := r.PathValue("runId")
	// The declared stream budget owns every bound on this connection, so its
	// clocks start at admission. Before this existed, a run that never reached
	// a terminal state left the loop below with no exit condition of its own:
	// the only bound was whatever deadline an outer middleware happened to
	// supply, and a single scalar timeout cannot express handshake, idle and
	// connection lifetime at once anyway.
	guard := streaming.NewBudgetGuard(r.Context(), h.streamBudget)
	defer guard.Stop()
	streamCtx := guard.Context()
	userID, err := requireRunUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	afterSeq, err := runResumeAfterSeq(r, runID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	runs, err := h.requireRunUseCases()
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	run, err := runs.Get(streamCtx, userID, runID)
	if err != nil {
		writeHTTPError(w, r, runStreamAdmissionError(guard, err))
		return
	}
	if _, err := runs.EventsAfter(
		streamCtx,
		userID,
		runID,
		int64(afterSeq),
		runEventPageSize,
	); err != nil {
		writeHTTPError(w, r, runStreamAdmissionError(guard, err))
		return
	}
	if limit := guard.Limit(); limit != streaming.BudgetLimitNone {
		writeHTTPError(w, r, runStreamAdmissionError(guard, nil))
		return
	}
	log.Printf(
		"assistant http stream_run_events_requested runId=%s afterSeq=%d requestId=%s traceId=%s",
		runID,
		afterSeq,
		resolveRequestID(r),
		resolveTraceID(r),
	)
	flusher, _ := w.(http.Flusher)
	// http.Server.WriteTimeout is a per-connection deadline that is never
	// refreshed per flush, so leaving it in place would end this stream at a
	// transport value instead of its declared max_duration_ms. Handing the
	// budget over is only safe because the guard owns all three bounds.
	if err := streaming.ReleaseTransportWriteDeadline(w); err != nil {
		// A transport that cannot carry a write deadline has none to preempt
		// the contract either, so there is nothing to hand over.
		log.Printf(
			"assistant http stream_write_deadline_absent runId=%s err=%v",
			runID,
			err,
		)
	}
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no")
	w.WriteHeader(http.StatusOK)
	if flusher != nil {
		flusher.Flush()
	}
	// First byte is on the wire: the handshake bound is satisfied and the idle
	// bound takes over.
	guard.HandshakeCompleted()
	nextSequence := int64(afterSeq)
	emitted := 0
	poll := time.NewTicker(runEventPollInterval)
	defer poll.Stop()
	heartbeat := time.NewTicker(runEventHeartbeat)
	defer heartbeat.Stop()
	for {
		events, streamErr := runs.EventsAfter(
			streamCtx,
			userID,
			runID,
			nextSequence,
			runEventPageSize,
		)
		if streamErr != nil {
			log.Printf(
				"assistant http stream_run_events_failed runId=%s afterSeq=%d limit=%s err=%v",
				runID,
				nextSequence,
				guard.Limit(),
				streamErr,
			)
			return
		}
		for _, event := range events {
			payload := cloneRunEventPayload(event.Payload)
			payload["sessionId"] = run.SessionID
			payload["runId"] = run.RunID
			envelope := streaming.Envelope{
				EventID:   event.EventID,
				StreamID:  run.RunID,
				EventType: projectRunJournalEventType(event),
				Seq:       uint64(event.Sequence),
				TraceID:   run.TraceID,
				Payload:   payload,
				CreatedAt: event.CreatedAt,
			}
			envelope.RuntimeFailure = projectRunRuntimeFailure(payload)
			writeStreamingSSEEnvelope(w, envelope, flusher)
			// One payload frame is one unit of progress, which is what the idle
			// bound measures.
			guard.FrameEmitted()
			nextSequence = event.Sequence
			emitted++
		}
		current, getErr := runs.Get(streamCtx, userID, runID)
		if getErr != nil {
			log.Printf(
				"assistant http stream_run_events_state_failed runId=%s limit=%s err=%v",
				runID,
				guard.Limit(),
				getErr,
			)
			return
		}
		if current.CompletedAt != nil &&
			nextSequence >= current.JournalSequence {
			break
		}
		select {
		case <-guard.Done():
			// The client resumes from the last emitted id, so a bounded close
			// needs no synthetic terminal event: inventing one would report a
			// run state that the aggregate does not have.
			log.Printf(
				"assistant http stream_run_events_bounded runId=%s limit=%s events=%d",
				runID,
				guard.Limit(),
				emitted,
			)
			return
		case <-heartbeat.C:
			// Keep-alive only. It is deliberately not reported to the guard:
			// a stalled worker still produces heartbeats, so counting them as
			// progress would make the idle bound unable to fire at all.
			_, _ = fmt.Fprint(w, ": assistant-run-heartbeat\n\n")
			if flusher != nil {
				flusher.Flush()
			}
		case <-poll.C:
		}
	}
	log.Printf(
		"assistant http stream_run_events_ready runId=%s events=%d",
		runID,
		emitted,
	)
}

// runStreamAdmissionError keeps a handshake violation distinguishable from a
// storage or authorization failure. Nothing has been written to the wire yet, so
// this is a real HTTP error and must carry the declared stream error code rather
// than a raw cancellation.
func runStreamAdmissionError(
	guard *streaming.BudgetGuard,
	cause error,
) error {
	if guard.Limit() == streaming.BudgetLimitHandshake {
		return runerrors.AppErrorFromStreamUnavailable(
			"assistant run stream exceeded its declared handshake budget",
		)
	}
	if cause != nil {
		return cause
	}
	return runerrors.AppErrorFromStreamUnavailable(
		"assistant run stream exceeded its declared budget before first byte",
	)
}

func runResumeAfterSeq(r *http.Request, runID string) (uint64, error) {
	token := strings.TrimSpace(r.Header.Get("Last-Event-ID"))
	if token == "" {
		token = strings.TrimSpace(r.URL.Query().Get("resumeToken"))
	}
	if token == "" {
		return 0, nil
	}
	streamID, seq, err := streaming.ParseResumeToken(token)
	if err != nil || streamID != strings.TrimSpace(runID) {
		return 0, runerrors.AppErrorFromRunInvalidArgument(
			"invalid assistant stream resume token",
		)
	}
	return seq, nil
}

func (h *Handler) requireRunUseCases() (*runapplication.UseCases, error) {
	if h != nil && h.runs != nil {
		return h.runs, nil
	}
	return nil, runerrors.AppErrorFromRunStorageUnavailable(
		"assistant run command service is not configured",
	)
}

func projectAssistantRunEnvelope(run runruntime.Run) map[string]any {
	completed := run.CompletedAt != nil
	completedAt := ""
	if run.CompletedAt != nil {
		completedAt = run.CompletedAt.UTC().Format(time.RFC3339Nano)
	}
	terminalSnapshot := any(nil)
	if run.TerminalSnapshot != nil {
		terminalSnapshot = run.TerminalSnapshot
	}
	return map[string]any{
		"runId":            run.RunID,
		"sessionId":        run.SessionID,
		"status":           run.State.WireName(),
		"reasoningProfile": run.ReasoningProfile.WireName(),
		"goal":             run.DefinitionOfDone.Outcome,
		"terminalSnapshot": terminalSnapshot,
		"traceId":          run.TraceID,
		"revision":         run.Revision,
		"streamState": map[string]any{
			"lastSeq":   run.JournalSequence,
			"completed": completed,
			"resumeToken": streaming.NewResumeToken(
				run.RunID,
				uint64(run.JournalSequence),
			),
		},
		"createdAt":   run.CreatedAt.UTC().Format(time.RFC3339Nano),
		"completedAt": completedAt,
	}
}

func projectRunJournalEventType(event runruntime.JournalEvent) string {
	switch event.Kind {
	case "run_accepted":
		return string(assistantstreaming.AssistantStreamEventRunStarted)
	case "completed", "failed", "cancelled",
		"run_state_changed", "task_graph_patch", "checkpoint_committed",
		"presentation_snapshot", "presentation_patch", "presentation_commit",
		"waiting_input", "waiting_approval", "process_replace",
		"process_append", "process_commit", "answer_delta":
		return event.Kind
	case "run_cancelled":
		return string(assistantstreaming.AssistantStreamEventCancelled)
	default:
		return "run_state_changed"
	}
}

func cloneRunEventPayload(source map[string]any) map[string]any {
	cloned := make(map[string]any, len(source)+2)
	for key, value := range source {
		cloned[key] = value
	}
	return cloned
}

func projectRunRuntimeFailure(payload map[string]any) *rtfailures.Failure {
	raw, ok := payload["runtimeFailure"]
	if !ok || raw == nil {
		return nil
	}
	encoded, err := json.Marshal(raw)
	if err != nil {
		return nil
	}
	var decoded rtfailures.Failure
	if err := json.Unmarshal(encoded, &decoded); err != nil ||
		strings.TrimSpace(decoded.Code) == "" {
		return nil
	}
	normalized := decoded.Normalized()
	return &normalized
}

func writeStreamingSSEEnvelope(
	w http.ResponseWriter,
	envelope streaming.Envelope,
	flusher http.Flusher,
) {
	event := envelope.SSEEvent()
	log.Printf(
		"assistant http sse_emit streamId=%s eventType=%s seq=%d traceId=%s",
		envelope.StreamID,
		envelope.EventType,
		envelope.Seq,
		envelope.TraceID,
	)
	if event.ID != "" {
		_, _ = fmt.Fprintf(w, "id: %s\n", event.ID)
	}
	if event.Event != "" {
		_, _ = fmt.Fprintf(w, "event: %s\n", event.Event)
	}
	normalized := envelope.Normalized()
	data := map[string]any{
		"schema":    "assistant_stream_event",
		"eventId":   normalized.EventID,
		"sessionId": streamPayloadString(normalized.Payload, "sessionId"),
		"runId":     streamPayloadString(normalized.Payload, "runId"),
		"seq":       normalized.Seq,
		"eventType": normalized.EventType,
		"traceId":   normalized.TraceID,
		"payload":   normalized.Payload,
		"createdAt": normalized.CreatedAt.Format(time.RFC3339Nano),
	}
	if normalized.RuntimeFailure != nil {
		data["runtimeFailure"] = normalized.RuntimeFailure
	}
	payload, _ := json.Marshal(data)
	_, _ = fmt.Fprintf(w, "data: %s\n\n", payload)
	if flusher != nil {
		flusher.Flush()
	}
}

func streamPayloadString(payload map[string]any, key string) string {
	value, _ := payload[key].(string)
	return strings.TrimSpace(value)
}

func resolveTraceID(r *http.Request) string {
	if traceID := strings.TrimSpace(r.Header.Get("X-Trace-Id")); traceID != "" {
		return traceID
	}
	return resolveRequestID(r)
}

func resolveRequestID(r *http.Request) string {
	if requestID := strings.TrimSpace(r.Header.Get("X-Request-Id")); requestID != "" {
		return requestID
	}
	return "assistant-request"
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func readJSON(r *http.Request, v any) error {
	body, err := io.ReadAll(io.LimitReader(r.Body, runRequestBodyMaxSize))
	if err != nil {
		return err
	}
	if len(strings.TrimSpace(string(body))) == 0 {
		return io.EOF
	}
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(v); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("request body must contain exactly one JSON value")
		}
		return err
	}
	return nil
}
