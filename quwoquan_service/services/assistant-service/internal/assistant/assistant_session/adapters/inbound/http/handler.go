package http

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/streaming"
	"strconv"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	rtfailures "quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/streaming"
	runerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_run"
	sessionerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

type Handler struct {
	service     *orchestration.AssistantService
	runCommands *runruntime.CommandService
	runs        *runapplication.UseCases
	preferences runapplication.PreferenceSnapshotReader
	context     *runapplication.ContextResolver
}

type HandlerOption func(*Handler)

func WithRunCommandService(commands *runruntime.CommandService) HandlerOption {
	return func(handler *Handler) {
		handler.runCommands = commands
	}
}

func WithRunPreferenceSnapshots(reader runapplication.PreferenceSnapshotReader) HandlerOption {
	return func(handler *Handler) { handler.preferences = reader }
}

func WithRunContextResolver(resolver *runapplication.ContextResolver) HandlerOption {
	return func(handler *Handler) { handler.context = resolver }
}

func NewHandler(
	service *orchestration.AssistantService,
	options ...HandlerOption,
) *Handler {
	handler := &Handler{service: service}
	if service != nil && service.RunCommandService() != nil {
		handler.runCommands = service.RunCommandService()
	}
	for _, option := range options {
		option(handler)
	}
	if handler.runCommands != nil {
		handler.runs = runapplication.NewUseCases(
			handler.runCommands,
			runapplication.WithPreferenceSnapshots(handler.preferences),
			runapplication.WithContextResolver(handler.context),
		)
	}
	return handler
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", h.handleHealthz)
	mux.HandleFunc("GET /livez", h.handleHealthz)
	mux.HandleFunc("GET /startupz", h.handleHealthz)
	mux.HandleFunc("POST /assistant/sessions/{sessionId}/runs", h.handleStartRun)
	mux.HandleFunc("GET /assistant/runs/{runId}", h.handleGetRun)
	mux.HandleFunc("POST /assistant/runs/{runId}/cancel", h.handleCancelRun)
	mux.HandleFunc("POST /assistant/runs/{runId}/pause", h.handlePauseRun)
	mux.HandleFunc("POST /assistant/runs/{runId}/resume", h.handleResumeRun)
	mux.HandleFunc("POST /assistant/runs/{runId}/steer", h.handleSteerRun)
	mux.HandleFunc(
		"POST /assistant/runs/{runId}/tool-uses/{toolUseId}/continue",
		h.handleContinueToolUse,
	)
	mux.HandleFunc("GET /assistant/runs/{runId}/events", h.handleStreamRunEvents)
	mux.HandleFunc("POST /assistant/intersections/reminders/tick", h.handleTickIntersectionReminders)
	mux.HandleFunc("POST /assistant/sessions", h.handleCreateSession)
	mux.HandleFunc("GET /assistant/sessions", h.handleListSessions)
	mux.HandleFunc("GET /assistant/sessions/{sessionId}", h.handleGetSession)
	return mux
}

func (h *Handler) handleHealthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *Handler) handleTickIntersectionReminders(w http.ResponseWriter, r *http.Request) {
	var input orchestration.IntersectionReminderTickInput
	if err := readJSON(r, &input); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	if strings.TrimSpace(input.UserID) == "" {
		input.UserID = resolveUserID(r)
	}
	result, err := h.service.TickIntersectionReminders(r.Context(), input)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

// requireIdentifiedUser 供对象公开读写路径使用：身份来自 JWT principal
// 或 auth middleware 白名单化后的可信 identity header，二者皆空时拒绝，
// 不再回退 anonymous（metadata 声明 auth_mode: required + actor persona）。
func requireIdentifiedUser(
	r *http.Request,
	unauthorized func(string) *rterr.AppError,
) (string, error) {
	if claims, ok := rtauth.PrincipalFromContext(r.Context()); ok && strings.TrimSpace(claims.Subject) != "" {
		return strings.TrimSpace(claims.Subject), nil
	}
	if uid := strings.TrimSpace(r.Header.Get("X-Client-User-Id")); uid != "" {
		return uid, nil
	}
	return "", unauthorized("assistant object requires an identified persona")
}

func requireSessionUser(r *http.Request) (string, error) {
	return requireIdentifiedUser(r, sessionerrors.AppErrorFromSessionUnauthorized)
}

func requireRunUser(r *http.Request) (string, error) {
	return requireIdentifiedUser(r, runerrors.AppErrorFromRunUnauthorized)
}

// requireCanonicalCommandIdentity enforces the one stable mutation identity
// declared by assistant command metadata. The body identifies the aggregate
// replay key; the HTTP header lets middleware, traces, and retrying transports
// observe the same key. Accepting either one alone would create two divergent
// idempotency paths.
func requireCanonicalCommandIdentity(
	r *http.Request,
	clientRequestID string,
) (string, error) {
	bodyID := strings.TrimSpace(clientRequestID)
	if bodyID == "" {
		return "", rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"clientRequestId 不能为空",
			"missing clientRequestId",
		)
	}
	headerID := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if headerID == "" {
		return "", rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"幂等请求头不能为空",
			"missing Idempotency-Key",
		)
	}
	if headerID != bodyID {
		return "", rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"幂等身份不一致",
			"clientRequestId does not match Idempotency-Key",
		)
	}
	return bodyID, nil
}

// requireRunCommandIdentity preserves the operation-specific failure contract.
// Session creation has its own error surface, while StartAssistantRun
// declares ASSISTANT.USER.run_invalid_argument for every malformed command
// identity variant.
func requireRunCommandIdentity(
	r *http.Request,
	clientRequestID string,
) (string, error) {
	requestID, err := requireCanonicalCommandIdentity(r, clientRequestID)
	if err != nil {
		return "", orchestration.AssistantRunInvalidArgument(err.Error())
	}
	return requestID, nil
}

func requireInjectedRunCommandIdentity(r *http.Request) (string, error) {
	requestID := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if requestID == "" {
		return "", orchestration.AssistantRunInvalidArgument(
			"missing Idempotency-Key",
		)
	}
	return requestID, nil
}

func (h *Handler) handleCreateSession(w http.ResponseWriter, r *http.Request) {
	userID, err := requireSessionUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	var input assistant.CreateSessionInput
	if err := readJSON(r, &input); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleAssistant, "请求体无效", err.Error()))
		return
	}
	input.ClientRequestID, err = requireCanonicalCommandIdentity(
		r,
		input.ClientRequestID,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	session, err := h.service.CreateSession(r.Context(), userID, input)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, session)
}

func (h *Handler) handleGetSession(w http.ResponseWriter, r *http.Request) {
	userID, err := requireSessionUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	session, err := h.service.GetSession(r.Context(), userID, r.PathValue("sessionId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
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
		writeHTTPError(w, r, orchestration.AssistantRunInvalidArgument(err.Error()))
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
	input.ClientRequestID, err = requireRunCommandIdentity(
		r,
		input.ClientRequestID,
	)
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

func (h *Handler) handleListSessions(w http.ResponseWriter, r *http.Request) {
	userID, err := requireSessionUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	view, err := h.service.ListSessions(
		r.Context(),
		userID,
		parseLimit(r, 20),
		r.URL.Query().Get("cursor"),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
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
		writeHTTPError(w, r, orchestration.AssistantRunInvalidArgument(err.Error()))
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
		writeHTTPError(w, r, orchestration.AssistantRunInvalidArgument(err.Error()))
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

func (h *Handler) handleContinueToolUse(w http.ResponseWriter, r *http.Request) {
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
	var input runapplication.ContinueToolUseInput
	if err := readJSON(r, &input); err != nil {
		writeHTTPError(w, r, orchestration.AssistantRunInvalidArgument(err.Error()))
		return
	}
	commandID, err := requireInjectedRunCommandIdentity(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	run, err := runs.ContinueToolUse(
		r.Context(),
		userID,
		r.PathValue("runId"),
		r.PathValue("toolUseId"),
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
	run, err := runs.Get(r.Context(), userID, runID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if _, err := runs.EventsAfter(
		r.Context(),
		userID,
		runID,
		int64(afterSeq),
		500,
	); err != nil {
		writeHTTPError(w, r, err)
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
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no")
	w.WriteHeader(http.StatusOK)
	if flusher != nil {
		flusher.Flush()
	}
	nextSequence := int64(afterSeq)
	emitted := 0
	poll := time.NewTicker(250 * time.Millisecond)
	defer poll.Stop()
	heartbeat := time.NewTicker(15 * time.Second)
	defer heartbeat.Stop()
	for {
		events, streamErr := runs.EventsAfter(
			r.Context(),
			userID,
			runID,
			nextSequence,
			500,
		)
		if streamErr != nil {
			log.Printf(
				"assistant http stream_run_events_failed runId=%s afterSeq=%d err=%v",
				runID,
				nextSequence,
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
			nextSequence = event.Sequence
			emitted++
		}
		current, getErr := runs.Get(r.Context(), userID, runID)
		if getErr != nil {
			log.Printf(
				"assistant http stream_run_events_state_failed runId=%s err=%v",
				runID,
				getErr,
			)
			return
		}
		if current.CompletedAt != nil &&
			nextSequence >= current.JournalSequence {
			break
		}
		select {
		case <-r.Context().Done():
			return
		case <-heartbeat.C:
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
		return 0, orchestration.AssistantRunInvalidArgument("invalid assistant stream resume token")
	}
	return seq, nil
}

func (h *Handler) requireRunUseCases() (*runapplication.UseCases, error) {
	if h.runs != nil {
		return h.runs, nil
	}
	appErr := rterr.NewAppError(
		rterr.NewCode(
			rterr.ModuleAssistant,
			rterr.KindSystem,
			"run_storage_unavailable",
		),
		"助手执行服务暂不可用，请稍后重试",
		"assistant run command service is not configured",
	)
	appErr.HTTPStatus = http.StatusServiceUnavailable
	return nil, appErr
}

func projectAssistantRunEnvelope(run runruntime.Run) map[string]any {
	completed := run.CompletedAt != nil
	completedAt := ""
	if run.CompletedAt != nil {
		completedAt = run.CompletedAt.UTC().Format(time.RFC3339Nano)
	}
	terminalSnapshot := any(nil)
	if len(run.TerminalSnapshot) > 0 {
		terminalSnapshot = projectAssistantRunTerminalSnapshot(run.TerminalSnapshot)
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

func projectAssistantRunTerminalSnapshot(snapshot map[string]any) map[string]any {
	processes := any([]map[string]any{})
	if value, found := snapshot["processes"]; found && value != nil {
		processes = value
	}
	projected := map[string]any{
		"answerText": snapshot["answerText"],
		"processes":  processes,
	}
	for _, field := range []string{"failure", "selectedPolicyRef"} {
		if value, found := snapshot[field]; found && value != nil {
			projected[field] = value
		}
	}
	return projected
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

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func writeStreamingSSE(w http.ResponseWriter, r *http.Request, envelopes []streaming.Envelope) {
	flusher, _ := w.(http.Flusher)
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no")
	w.WriteHeader(http.StatusOK)
	for _, envelope := range envelopes {
		writeStreamingSSEEnvelope(w, envelope, flusher)
	}
}

func writeStreamingSSEEnvelope(w http.ResponseWriter, envelope streaming.Envelope, flusher http.Flusher) {
	event := envelope.SSEEvent()
	log.Printf("assistant http sse_emit streamId=%s eventType=%s seq=%d traceId=%s", envelope.StreamID, envelope.EventType, envelope.Seq, envelope.TraceID)
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

func mustStreamingEnvelope(event string, seq uint64, data any) streaming.Envelope {
	envelope, err := streaming.NewEnvelope(event, seq, data)
	if err != nil {
		panic(err)
	}
	return envelope.Normalized()
}

func readJSON(r *http.Request, v any) error {
	body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
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

func applyRunRequestContext(input *assistant.CreateTurnInput, r *http.Request) {
	if input == nil {
		return
	}
	input.RequestContext = assistant.AssistantRunRequestContext{
		ClientSessionID: resolveClientSessionID(r),
		PageID:          resolvePageID(r),
		SurfaceID:       resolveSurfaceID(r),
		RouteID:         resolveRouteID(r),
		OperationID:     resolveOperationID(r),
		TraceID:         resolveTraceID(r),
		PersonaID:       resolvePersonaID(r),
	}.Normalized()
}

func parseLimit(r *http.Request, fallback int) int {
	if fallback <= 0 {
		fallback = 20
	}
	raw := strings.TrimSpace(r.URL.Query().Get("limit"))
	if raw == "" {
		return fallback
	}
	limit, err := strconv.Atoi(raw)
	if err != nil || limit <= 0 {
		return fallback
	}
	return limit
}

func resolveUserID(r *http.Request) string {
	if principal, ok := rtauth.PrincipalFromContext(r.Context()); ok {
		if accountID := strings.TrimSpace(principal.Actor.AccountID); accountID != "" {
			return accountID
		}
	}
	if uid := strings.TrimSpace(r.Header.Get("X-Client-User-Id")); uid != "" {
		return uid
	}
	return "anonymous"
}

func resolvePersonaID(r *http.Request) string {
	if principal, ok := rtauth.PrincipalFromContext(r.Context()); ok {
		if personaID := strings.TrimSpace(principal.Actor.PersonaID); personaID != "" {
			return personaID
		}
	}
	return strings.TrimSpace(r.Header.Get("X-Client-Persona-Id"))
}

func resolveClientSessionID(r *http.Request) string {
	if sessionID := strings.TrimSpace(r.Header.Get("X-Client-Session-Id")); sessionID != "" {
		return sessionID
	}
	return "unknown-session"
}

func resolvePageID(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("X-Client-Page-Id"))
}

func resolveSurfaceID(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("X-Client-Surface-Id"))
}

func resolveRouteID(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("X-Client-Route-Id"))
}

func resolveOperationID(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("X-Client-Operation-Id"))
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

func buildRunResponseText(query string) string {
	if strings.TrimSpace(query) == "" {
		return "小趣已收到请求，可以继续补充问题以获取完整答案。"
	}
	return "小趣已收到你的问题：" + query + "。当前 assistant-service 已按最终态提供独立 ingress，可继续承接完整对话编排。"
}

func fmtString(value any) string {
	if value == nil {
		return ""
	}
	return strings.TrimSpace(fmt.Sprint(value))
}
