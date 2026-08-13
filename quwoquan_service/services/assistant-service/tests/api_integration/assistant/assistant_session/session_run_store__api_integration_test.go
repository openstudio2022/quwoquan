// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/spec.md#sit-001
// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001.t3
// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001.t4
// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-sync-contract/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-sync-contract/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-sync-contract/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-sync-contract/spec.md#gwt-001.t3
// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-sync-contract/spec.md#gwt-001.t4
// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-sync-contract/spec.md#gwt-001.t5
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/long-term-memory-compaction/spec.md#gwt-002
// readiness_case: create-assistant-session-api
// readiness_case: list-assistant-sessions-api
// readiness_case: get-assistant-session-api
// readiness_case: compact-assistant-session-api
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/generated/serviceclients"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/runtime/streaming"
	preferencehttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/adapters/inbound/http"
	preferenceapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/application"
	runorchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	runruntime "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	runmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	sessioncompaction "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/compaction"
	sessionorchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/notificationclient"
	turnviewhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/adapters/inbound/http"
	turnviewapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/application"
	turnviewmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/domain/model"
	consentapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
	subscriptionhttp "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/adapters/inbound/http"
	subscriptionapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
	skillmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
	"quwoquan_service/services/assistant-service/tests/support/assistantingress"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/long-term-memory-compaction/spec.md#gwt-002
func TestMongoSessionCompactionCommitsSummaryAndReplayReceiptAtomically(t *testing.T) {
	resetIntegrationState(t)
	now := time.Date(2026, 8, 4, 10, 0, 0, 0, time.UTC)
	_, _, err := integrationSessionStore.InsertSession(t.Context(), assistant.AssistantSession{
		SessionID: "session-mongo-compaction",
		UserID:    "user-mongo-compaction",
		State:     "active",
		CreatedAt: now.Add(-time.Hour),
		UpdatedAt: now.Add(-time.Hour),
	})
	if err != nil {
		t.Fatalf("insert AssistantSession: %v", err)
	}
	providerCalls := 0
	service := sessioncompaction.NewService(
		integrationSessionStore,
		sessioncompaction.NarrativeGeneratorFunc(func(
			context.Context,
			sessioncompaction.NarrativeInput,
		) (string, error) {
			providerCalls++
			return "你已完成第一轮计划，仍需确认酒店。", nil
		}),
	)
	source := sessioncompaction.CompletedRunSource{
		CompletionEventID: "run-mongo-compaction:terminal",
		RunID:             "run-mongo-compaction",
		SessionID:         "session-mongo-compaction",
		UserID:            "user-mongo-compaction",
		CurrentGoal:       "完成杭州行程",
		UserInput:         "继续规划杭州行程",
		AnswerText:        "已完成第一轮计划",
		PendingItems:      []string{"确认酒店"},
		ConfirmedSlots:    map[string]string{"destination": "杭州"},
		CompletedAt:       now,
	}
	first, err := service.CompactCompletedRun(t.Context(), source)
	if err != nil {
		t.Fatalf("compact completed Run: %v", err)
	}
	replayed, err := service.CompactCompletedRun(t.Context(), source)
	if err != nil {
		t.Fatalf("replay completed Run: %v", err)
	}
	if replayed.SummaryID != first.SummaryID || providerCalls != 1 {
		t.Fatalf("replay changed summary or called provider: first=%+v replay=%+v calls=%d", first, replayed, providerCalls)
	}
	persisted, found, err := integrationSessionStore.GetSession(
		t.Context(),
		source.SessionID,
	)
	if err != nil || !found || persisted.ContextSummary == nil ||
		persisted.ContextSummary.SummaryID != first.SummaryID ||
		persisted.SummaryVersion != 1 || persisted.SummarySourceSequence != 1 ||
		persisted.CompletionSequence != 1 {
		t.Fatalf("persisted summary=%+v found=%t err=%v", persisted, found, err)
	}
	receiptCount, err := integrationMongoDB.Collection(
		"assistant_session_summary_receipts",
	).CountDocuments(t.Context(), bson.M{
		"_id":       source.CompletionEventID,
		"sessionId": source.SessionID,
		"summaryId": first.SummaryID,
	})
	if err != nil || receiptCount != 1 {
		t.Fatalf("summary receipt count=%d err=%v", receiptCount, err)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/long-term-memory-compaction/spec.md#gwt-002
func TestTerminalRunRelayInvokesSessionCoordinatorBeforeMongoSourceAck(t *testing.T) {
	resetIntegrationState(t)
	ctx := t.Context()
	handler := assistantHTTPHandlerWithTurnView(newIntegrationAssistantService())
	create := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/sessions",
		"terminal-compaction-owner",
		map[string]any{
			"summary":         "terminal coordinator integration",
			"clientRequestId": "terminal-coordinator-session",
		},
	)
	if create.Code != http.StatusCreated {
		t.Fatalf("create terminal session status=%d body=%s", create.Code, create.Body.String())
	}
	var session assistant.AssistantSession
	if err := json.Unmarshal(create.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode terminal session: %v", err)
	}
	start := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/sessions/"+session.SessionID+"/runs",
		"terminal-compaction-owner",
		map[string]any{
			"intent": map[string]any{
				"kind":   "answer",
				"answer": map[string]any{"text": "规划杭州行程并确认酒店"},
			},
			"clientRequestId": "terminal-coordinator-run",
		},
	)
	if start.Code != http.StatusCreated {
		t.Fatalf("start terminal Run status=%d body=%s", start.Code, start.Body.String())
	}
	var run assistantRunEnvelope
	if err := json.Unmarshal(start.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode terminal Run: %v", err)
	}
	worker := runruntime.NewDurableWorker(
		integrationRunRepository,
		integrationRunRepository,
		recoveredRunExecutor{},
		"terminal-coordinator-worker",
	)
	worked, err := worker.ProcessNext(ctx)
	if err != nil || !worked {
		t.Fatalf("complete terminal Run: worked=%t err=%v", worked, err)
	}
	hooks, err := runruntime.NewHookRegistry()
	if err != nil {
		t.Fatalf("create terminal hook registry: %v", err)
	}
	providerCalls := 0
	coordinator := sessioncompaction.NewAssistantRunTerminalCoordinator(
		integrationRunRepository,
		sessioncompaction.NewService(
			integrationSessionStore,
			sessioncompaction.NarrativeGeneratorFunc(func(
				context.Context,
				sessioncompaction.NarrativeInput,
			) (string, error) {
				providerCalls++
				return "已完成可回查回答，并保留下一步。", nil
			}),
		),
		hooks,
	)
	relay := runruntime.NewTerminalRunRelay(
		integrationRunRepository,
		runruntime.TerminalEventPublisherFunc(func(
			context.Context,
			runruntime.TerminalEvent,
		) error {
			return nil
		}),
		[]runruntime.TerminalEventHandler{coordinator},
		"terminal-session-coordinator",
		time.Second,
		16,
	)
	processed, err := relay.FlushOnce(ctx)
	if err != nil || processed != 1 {
		t.Fatalf("relay terminal compaction: processed=%d err=%v", processed, err)
	}
	persisted, found, err := integrationSessionStore.GetSession(ctx, session.SessionID)
	if err != nil || !found || persisted.ContextSummary == nil ||
		persisted.ContextSummary.ToTurnID != run.RunID || providerCalls != 1 {
		t.Fatalf(
			"terminal summary=%+v found=%t providerCalls=%d err=%v",
			persisted,
			found,
			providerCalls,
			err,
		)
	}
	acknowledged, err := integrationMongoDB.Collection("assistant_run_terminal_outbox").
		CountDocuments(ctx, bson.M{
			"runId":       run.RunID,
			"processedAt": bson.M{"$type": "date"},
		})
	if err != nil || acknowledged != 1 {
		t.Fatalf("terminal source ACK count=%d err=%v", acknowledged, err)
	}
}

func assistantHTTPHandlerWithTurnView(
	service *sessionorchestration.AssistantService,
) http.Handler {
	mux := http.NewServeMux()
	turnviewhttp.NewHandler(turnviewapplication.NewQueryFacade(
		integrationTurnViewStore,
		integrationSessionStore,
		integrationTurnViewProjector,
	)).RegisterRoutes(mux)
	preferencehttp.NewHandler(
		preferenceapplication.NewCommandFacade(integrationPreferenceStore, integrationSessionStore),
		preferenceapplication.NewQueryFacade(integrationPreferenceStore),
	).RegisterRoutes(mux)
	subscriptionhttp.NewHandler(
		subscriptionapplication.NewUseCases(
			integrationSubscriptionStore,
			nil,
			service,
			time.Now,
		),
	).RegisterRoutes(mux)
	mux.Handle("/", assistantingress.Routes(service))
	return mux
}

func assistantAPIRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	userID string,
	body any,
) *httptest.ResponseRecorder {
	t.Helper()
	var payload []byte
	if body != nil {
		var err error
		payload, err = json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal assistant request: %v", err)
		}
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(payload))
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	if userID != "" {
		request.Header.Set("X-Client-User-Id", userID)
		request = request.WithContext(rtauth.WithPrincipal(
			request.Context(),
			rtauth.Principal{
				Actor: operation.ActorContext{
					AccountID: userID,
					PersonaID: userID + ":persona",
				},
			},
		))
	}
	if body != nil {
		var commandIdentity struct {
			ClientRequestID string `json:"clientRequestId"`
		}
		if err := json.Unmarshal(payload, &commandIdentity); err != nil {
			t.Fatalf("decode assistant command identity: %v", err)
		}
		if strings.TrimSpace(commandIdentity.ClientRequestID) != "" {
			request.Header.Set("Idempotency-Key", commandIdentity.ClientRequestID)
		}
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func assistantAPIInjectedRunCommand(
	t *testing.T,
	handler http.Handler,
	path string,
	userID string,
	commandID string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(http.MethodPost, path, nil)
	request.Header.Set("X-Client-User-Id", userID)
	request.Header.Set("Idempotency-Key", commandID)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{
			AccountID: userID,
			PersonaID: userID + ":persona",
		}},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

type assistantRunEnvelope struct {
	RunID            string                                 `json:"runId"`
	SessionID        string                                 `json:"sessionId"`
	Status           string                                 `json:"status"`
	ReasoningProfile string                                 `json:"reasoningProfile"`
	Goal             string                                 `json:"goal"`
	TerminalSnapshot *runmodel.AssistantRunTerminalSnapshot `json:"terminalSnapshot"`
	TraceID          string                                 `json:"traceId"`
	Revision         int64                                  `json:"revision"`
	StreamState      struct {
		LastSeq     int64  `json:"lastSeq"`
		Completed   bool   `json:"completed"`
		ResumeToken string `json:"resumeToken"`
	} `json:"streamState"`
	CreatedAt   string `json:"createdAt"`
	CompletedAt string `json:"completedAt"`
}

func assertAssistantRunEnvelopePublicKeys(
	t *testing.T,
	response map[string]any,
) {
	t.Helper()
	allowed := map[string]bool{
		"runId":            true,
		"sessionId":        true,
		"status":           true,
		"reasoningProfile": true,
		"goal":             true,
		"streamState":      true,
		"terminalSnapshot": true,
		"traceId":          true,
		"revision":         true,
		"createdAt":        true,
		"completedAt":      true,
	}
	for key := range response {
		if !allowed[key] {
			t.Fatalf("AssistantRun response leaked non-contract field %q: %#v", key, response)
		}
	}
	for _, required := range []string{
		"runId",
		"sessionId",
		"status",
		"reasoningProfile",
		"goal",
		"streamState",
		"traceId",
		"revision",
		"createdAt",
	} {
		if _, found := response[required]; !found {
			t.Fatalf("AssistantRun response is missing declared field %q: %#v", required, response)
		}
	}
}

func assertAssistantTerminalSnapshotPublicShape(
	t *testing.T,
	raw any,
) map[string]any {
	t.Helper()
	snapshot, ok := raw.(map[string]any)
	if !ok {
		t.Fatalf("terminalSnapshot must be an object: %#v", raw)
	}
	assertAssistantJSONKeys(t, "terminalSnapshot", snapshot, map[string]bool{
		"answerText":        true,
		"processes":         true,
		"failure":           true,
		"selectedPolicyRef": true,
	})
	if _, found := snapshot["answerText"]; !found {
		t.Fatalf("terminalSnapshot is missing answerText: %#v", snapshot)
	}
	processes, ok := snapshot["processes"].([]any)
	if !ok {
		t.Fatalf("terminalSnapshot.processes must be an array: %#v", snapshot)
	}
	for index, rawProcess := range processes {
		process, ok := rawProcess.(map[string]any)
		if !ok {
			t.Fatalf("terminalSnapshot.processes[%d] must be an object", index)
		}
		assertAssistantJSONKeys(t, "terminalSnapshot.process", process, map[string]bool{
			"processId":              true,
			"scope":                  true,
			"stage":                  true,
			"actionCode":             true,
			"status":                 true,
			"order":                  true,
			"summary":                true,
			"skillId":                true,
			"domainId":               true,
			"searchedDocumentCount":  true,
			"processedDocumentCount": true,
			"acceptedDocumentCount":  true,
			"acceptedReferences":     true,
		})
		references, ok := process["acceptedReferences"].([]any)
		if !ok {
			t.Fatalf("terminal process acceptedReferences must be an array: %#v", process)
		}
		for _, rawReference := range references {
			reference, ok := rawReference.(map[string]any)
			if !ok {
				t.Fatalf("terminal reference must be an object: %#v", rawReference)
			}
			assertAssistantJSONKeys(t, "terminalSnapshot.reference", reference, map[string]bool{
				"title":       true,
				"destination": true,
				"source":      true,
				"snippet":     true,
			})
		}
	}
	if rawFailure := snapshot["failure"]; rawFailure != nil {
		failure, ok := rawFailure.(map[string]any)
		if !ok {
			t.Fatalf("terminalSnapshot.failure must be an object: %#v", rawFailure)
		}
		assertAssistantJSONKeys(t, "terminalSnapshot.failure", failure, map[string]bool{
			"code":   true,
			"origin": true,
			"kind":   true,
			"nature": true,
		})
	}
	return snapshot
}

func assertAssistantJSONKeys(
	t *testing.T,
	label string,
	value map[string]any,
	allowed map[string]bool,
) {
	t.Helper()
	for key := range value {
		if !allowed[key] {
			t.Fatalf("%s leaked non-contract field %q: %#v", label, key, value)
		}
	}
}

func awaitAssistantRunScorecard(
	t *testing.T,
	ctx context.Context,
	turnID string,
) {
	t.Helper()

	waitCtx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	deadline := time.Now().Add(2 * time.Second)
	for {
		count, err := integrationMongoDB.Collection("assistant_learning_facts").
			CountDocuments(waitCtx, bson.M{
				"eventId":  "turn:" + turnID + ":completion",
				"factType": "service_scorecard",
			})
		if err != nil {
			t.Fatalf("count run completion scorecard: %v", err)
		}
		if count == 1 {
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("run completion scorecard count=%d, want 1", count)
		}
		time.Sleep(20 * time.Millisecond)
	}
}

type assistantSSEEventFrame struct {
	id        string
	seq       int
	eventType string
	payload   map[string]any
}

func parseAssistantSSEEventFrames(
	t *testing.T,
	body string,
) []assistantSSEEventFrame {
	t.Helper()
	frames := make([]assistantSSEEventFrame, 0)
	for _, rawFrame := range strings.Split(body, "\n\n") {
		frame := strings.TrimSpace(rawFrame)
		if frame == "" {
			continue
		}
		var eventID string
		dataLines := make([]string, 0)
		for _, line := range strings.Split(frame, "\n") {
			switch {
			case strings.HasPrefix(line, "id:"):
				eventID = strings.TrimSpace(strings.TrimPrefix(line, "id:"))
			case strings.HasPrefix(line, "data:"):
				dataLines = append(
					dataLines,
					strings.TrimSpace(strings.TrimPrefix(line, "data:")),
				)
			}
		}
		if eventID == "" || len(dataLines) == 0 {
			t.Fatalf("invalid assistant SSE frame: %q", rawFrame)
		}
		var envelope struct {
			Seq       int            `json:"seq"`
			EventType string         `json:"eventType"`
			Payload   map[string]any `json:"payload"`
		}
		if err := json.Unmarshal(
			[]byte(strings.Join(dataLines, "\n")),
			&envelope,
		); err != nil {
			t.Fatalf("decode assistant SSE frame: %v", err)
		}
		if envelope.Seq <= 0 || envelope.EventType == "" {
			t.Fatalf("invalid assistant SSE envelope: %#v", envelope)
		}
		frames = append(frames, assistantSSEEventFrame{
			id:        eventID,
			seq:       envelope.Seq,
			eventType: envelope.EventType,
			payload:   envelope.Payload,
		})
	}
	if len(frames) == 0 {
		t.Fatalf("assistant SSE response has no frames: %q", body)
	}
	return frames
}

// TestAssistantSessionCreatePersistedAndIdempotent 验证一次创建：
// 会话持久化到 assistant_sessions，相同 clientRequestId 重放返回首个会话，
// 新服务实例（模拟重启）仍可读。
func TestAssistantSessionCreatePersistedAndIdempotent(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	handler := assistantHTTPHandlerWithTurnView(newIntegrationAssistantService())

	create := map[string]any{
		"summary":         "商用闭环验证会话",
		"clientRequestId": "conv-req-1",
	}
	first := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/sessions", "user-conv-1", create)
	if first.Code != http.StatusCreated {
		t.Fatalf("create session status=%d body=%s", first.Code, first.Body.String())
	}
	var created assistant.AssistantSession
	if err := json.Unmarshal(first.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode session: %v", err)
	}
	replay := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/sessions", "user-conv-1", create)
	var replayed assistant.AssistantSession
	if err := json.Unmarshal(replay.Body.Bytes(), &replayed); err != nil {
		t.Fatalf("decode replayed session: %v", err)
	}
	if replayed.SessionID != created.SessionID {
		t.Fatalf("idempotent replay must return first session: first=%s replay=%s",
			created.SessionID, replayed.SessionID)
	}
	count, err := integrationMongoDB.Collection("assistant_sessions").
		CountDocuments(ctx, bson.M{"userId": "user-conv-1"})
	if err != nil || count != 1 {
		t.Fatalf("persisted session count=%d err=%v", count, err)
	}

	// 模拟重启：全新 service 实例（无进程内状态）仍能读到会话。
	restarted := assistantingress.Routes(newIntegrationAssistantService())
	get := assistantAPIRequest(t, restarted, http.MethodGet,
		"/assistant/sessions/"+created.SessionID, "user-conv-1", nil)
	if get.Code != http.StatusOK {
		t.Fatalf("session must survive restart: status=%d body=%s", get.Code, get.Body.String())
	}
}

// TestAssistantCommandIdentityRequiresMatchedHeaderAndBody ensures the
// metadata-required replay identity cannot split between HTTP transport and
// persisted aggregate identity.
func TestAssistantCommandIdentityRequiresMatchedHeaderAndBody(t *testing.T) {
	resetIntegrationState(t)
	handler := assistantHTTPHandlerWithTurnView(newIntegrationAssistantService())

	for _, testCase := range []struct {
		name          string
		idempotencyID string
	}{
		{name: "missing idempotency header"},
		{name: "mismatched idempotency header", idempotencyID: "different-key"},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			request := httptest.NewRequest(
				http.MethodPost,
				"/assistant/sessions",
				strings.NewReader(`{"summary":"identity","clientRequestId":"body-key"}`),
			)
			request.Header.Set("Content-Type", "application/json")
			request.Header.Set("X-Client-User-Id", "identity-user")
			if testCase.idempotencyID != "" {
				request.Header.Set("Idempotency-Key", testCase.idempotencyID)
			}
			recorder := httptest.NewRecorder()
			handler.ServeHTTP(recorder, request)
			if recorder.Code != http.StatusBadRequest {
				t.Fatalf(
					"status=%d want=%d body=%s",
					recorder.Code,
					http.StatusBadRequest,
					recorder.Body.String(),
				)
			}
		})
	}

	create := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/sessions",
		"identity-user",
		map[string]any{"clientRequestId": "identity-session"},
	)
	if create.Code != http.StatusCreated {
		t.Fatalf("create identity session: status=%d body=%s", create.Code, create.Body.String())
	}
	var session assistant.AssistantSession
	if err := json.Unmarshal(create.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode identity session: %v", err)
	}
	for _, testCase := range []struct {
		name          string
		idempotencyID string
	}{
		{name: "run missing idempotency header"},
		{name: "run mismatched idempotency header", idempotencyID: "different-run-key"},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			request := httptest.NewRequest(
				http.MethodPost,
				"/assistant/sessions/"+session.SessionID+"/runs",
				strings.NewReader(
					`{"input":{"text":"identity"},"clientRequestId":"body-run-key"}`,
				),
			)
			request.Header.Set("Content-Type", "application/json")
			request.Header.Set("X-Client-User-Id", "identity-user")
			if testCase.idempotencyID != "" {
				request.Header.Set("Idempotency-Key", testCase.idempotencyID)
			}
			recorder := httptest.NewRecorder()
			handler.ServeHTTP(recorder, request)
			if recorder.Code != http.StatusBadRequest {
				t.Fatalf(
					"run status=%d want=%d body=%s",
					recorder.Code,
					http.StatusBadRequest,
					recorder.Body.String(),
				)
			}
		})
	}
}

func TestAssistantRunPersistsTrustedTransportContextWithoutEchoingIt(t *testing.T) {
	resetIntegrationState(t)
	handler := assistantHTTPHandlerWithTurnView(newIntegrationAssistantService())
	const (
		userID      = "run-context-owner"
		sessionID   = "session-run-context"
		pageID      = "assistant_dialog"
		surfaceID   = "personal_assistant_dialog_surface"
		routeID     = "/assistant"
		operationID = "StartAssistantRun"
		traceID     = "trace-run-context"
		personaID   = "run-context-persona"
	)

	create := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/sessions",
		userID,
		map[string]any{"clientRequestId": "run-context-session"},
	)
	if create.Code != http.StatusCreated {
		t.Fatalf("create context session: status=%d body=%s", create.Code, create.Body.String())
	}
	var session assistant.AssistantSession
	if err := json.Unmarshal(create.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode context session: %v", err)
	}

	untrusted := httptest.NewRequest(
		http.MethodPost,
		"/assistant/sessions/"+session.SessionID+"/runs",
		strings.NewReader(
			`{"intent":{"kind":"answer","answer":{"text":"context"}},"clientRequestId":"run-context-untrusted","requestContext":{"traceId":"forged"}}`,
		),
	)
	untrusted.Header.Set("Content-Type", "application/json")
	untrusted.Header.Set("X-Client-User-Id", userID)
	untrusted.Header.Set("Idempotency-Key", "run-context-untrusted")
	untrustedRecorder := httptest.NewRecorder()
	handler.ServeHTTP(untrustedRecorder, untrusted)
	if untrustedRecorder.Code != http.StatusBadRequest {
		t.Fatalf(
			"untrusted body context status=%d want=%d body=%s",
			untrustedRecorder.Code,
			http.StatusBadRequest,
			untrustedRecorder.Body.String(),
		)
	}
	if !strings.Contains(
		untrustedRecorder.Body.String(),
		"ASSISTANT.USER.run_invalid_argument",
	) {
		t.Fatalf(
			"untrusted body context must return canonical run_invalid_argument: %s",
			untrustedRecorder.Body.String(),
		)
	}

	request := httptest.NewRequest(
		http.MethodPost,
		"/assistant/sessions/"+session.SessionID+"/runs",
		strings.NewReader(
			`{"intent":{"kind":"answer","answer":{"text":"context"}},"clientRequestId":"run-context-command"}`,
		),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Client-User-Id", userID)
	request.Header.Set("Idempotency-Key", "run-context-command")
	request.Header.Set("X-Client-Session-Id", sessionID)
	request.Header.Set("X-Client-Page-Id", pageID)
	request.Header.Set("X-Client-Surface-Id", surfaceID)
	request.Header.Set("X-Client-Route-Id", routeID)
	request.Header.Set("X-Client-Operation-Id", operationID)
	request.Header.Set("X-Client-Persona-Id", personaID)
	request.Header.Set("X-Trace-Id", traceID)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{
			AccountID: userID,
			PersonaID: personaID,
		}},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusCreated {
		t.Fatalf("start context run: status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var response map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode context run response: %v", err)
	}
	if _, exists := response["requestContext"]; exists {
		t.Fatal("start run response must not echo internal requestContext")
	}
	assertAssistantRunEnvelopePublicKeys(t, response)
	runID, _ := response["runId"].(string)
	if runID == "" || response["traceId"] != traceID {
		t.Fatalf("run response=%#v, want runId and traceId=%q", response, traceID)
	}

	stored, err := integrationRunRepository.Load(
		context.Background(),
		runID,
	)
	if err != nil {
		t.Fatalf("load persisted context run: %v", err)
	}
	if stored.UserID != userID || stored.TraceID != traceID {
		t.Fatalf("stored run user/trace=%q/%q", stored.UserID, stored.TraceID)
	}
	wantContext := runruntime.RequestContext{
		ClientSessionID: sessionID,
		PageID:          pageID,
		SurfaceID:       surfaceID,
		RouteID:         routeID,
		OperationID:     operationID,
		TraceID:         traceID,
		PersonaID:       personaID,
	}
	if stored.RequestContext != wantContext {
		t.Fatalf(
			"stored request context=%#v, want %#v",
			stored.RequestContext,
			wantContext,
		)
	}
	get := assistantAPIRequest(
		t,
		handler,
		http.MethodGet,
		"/assistant/runs/"+runID,
		userID,
		nil,
	)
	if get.Code != http.StatusOK {
		t.Fatalf("get context run: status=%d body=%s", get.Code, get.Body.String())
	}
	var getResponse map[string]any
	if err := json.Unmarshal(get.Body.Bytes(), &getResponse); err != nil {
		t.Fatalf("decode get context run response: %v", err)
	}
	assertAssistantRunEnvelopePublicKeys(t, getResponse)
}

// TestAssistantSessionOwnerIsolation 验证 owner 隔离与匿名拒绝。
func TestAssistantSessionOwnerIsolation(t *testing.T) {
	resetIntegrationState(t)
	handler := assistantingress.Routes(newIntegrationAssistantService())

	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/sessions",
		"owner-a", map[string]any{
			"summary": "私密会话", "clientRequestId": "owner-isolation-session",
		})
	var created assistant.AssistantSession
	if err := json.Unmarshal(create.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode session: %v", err)
	}

	foreign := assistantAPIRequest(t, handler, http.MethodGet,
		"/assistant/sessions/"+created.SessionID, "intruder-b", nil)
	if foreign.Code != http.StatusNotFound {
		t.Fatalf("foreign read must be not_found: status=%d body=%s", foreign.Code, foreign.Body.String())
	}
	anonymous := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/sessions",
		"", map[string]any{"summary": "匿名"})
	if anonymous.Code != http.StatusUnauthorized {
		t.Fatalf("anonymous create must be 401: status=%d body=%s", anonymous.Code, anonymous.Body.String())
	}
}

// TestAssistantRunStartPersistedAndIdempotent 验证 run 一次创建、幂等重放与重启后可读。
func TestAssistantRunStartPersistedAndIdempotent(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	handler := assistantingress.Routes(newIntegrationAssistantService())

	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/sessions",
		"user-run-1", map[string]any{
			"summary": "run 会话", "clientRequestId": "run-persistence-session",
		})
	var session assistant.AssistantSession
	if err := json.Unmarshal(create.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode session: %v", err)
	}
	startBody := map[string]any{
		"intent": map[string]any{
			"kind": "answer", "answer": map[string]any{"text": "帮我看看今天的天气"},
		},
		"clientRequestId": "run-req-1",
	}
	runPath := "/assistant/sessions/" + session.SessionID + "/runs"
	first := assistantAPIRequest(t, handler, http.MethodPost, runPath, "user-run-1", startBody)
	if first.Code != http.StatusCreated {
		t.Fatalf("start run status=%d body=%s", first.Code, first.Body.String())
	}
	var run assistantRunEnvelope
	if err := json.Unmarshal(first.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v", err)
	}
	replay := assistantAPIRequest(t, handler, http.MethodPost, runPath, "user-run-1", startBody)
	var replayedRun assistantRunEnvelope
	if err := json.Unmarshal(replay.Body.Bytes(), &replayedRun); err != nil {
		t.Fatalf("decode replayed run: %v", err)
	}
	if replayedRun.RunID != run.RunID {
		t.Fatalf("idempotent replay must return first run: first=%s replay=%s", run.RunID, replayedRun.RunID)
	}
	count, err := integrationMongoDB.Collection("assistant_runs").
		CountDocuments(ctx, bson.M{"sessionId": session.SessionID})
	if err != nil || count != 1 {
		t.Fatalf("persisted run count=%d err=%v", count, err)
	}

	restarted := assistantingress.Routes(newIntegrationAssistantService())
	get := assistantAPIRequest(t, restarted, http.MethodGet, "/assistant/runs/"+run.RunID, "user-run-1", nil)
	if get.Code != http.StatusOK {
		t.Fatalf("run must survive restart: status=%d body=%s", get.Code, get.Body.String())
	}
}

// TestAssistantRunOwnerIsolation 验证 run 的 owner 隔离与匿名拒绝。
func TestAssistantRunOwnerIsolation(t *testing.T) {
	resetIntegrationState(t)
	handler := assistantingress.Routes(newIntegrationAssistantService())

	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/sessions",
		"owner-run", map[string]any{
			"summary": "run 隔离", "clientRequestId": "run-owner-isolation-session",
		})
	var session assistant.AssistantSession
	if err := json.Unmarshal(create.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode session: %v", err)
	}
	start := assistantAPIRequest(t, handler, http.MethodPost,
		"/assistant/sessions/"+session.SessionID+"/runs",
		"owner-run", map[string]any{
			"intent": map[string]any{
				"kind": "answer", "answer": map[string]any{"text": "隔离测试"},
			},
			"clientRequestId": "run-owner-isolation",
		})
	var run assistantRunEnvelope
	if err := json.Unmarshal(start.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v", err)
	}

	foreign := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/runs/"+run.RunID, "intruder", nil)
	if foreign.Code != http.StatusNotFound {
		t.Fatalf("foreign run read must be not_found: status=%d", foreign.Code)
	}
	anonymous := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/runs/"+run.RunID, "", nil)
	if anonymous.Code != http.StatusUnauthorized {
		t.Fatalf("anonymous run read must be 401: status=%d", anonymous.Code)
	}
}

// TestAssistantRunStreamResumeSemantics 验证 SSE：首跑落终态；
// 重启后重放 SSE 返回持久化终态事件而非 404。
func TestAssistantRunStreamResumeSemantics(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	handler := assistantHTTPHandlerWithTurnView(newIntegrationAssistantService())

	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/sessions",
		"user-sse", map[string]any{
			"summary": "SSE 会话", "clientRequestId": "stream-resume-session",
		})
	var session assistant.AssistantSession
	if err := json.Unmarshal(create.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode session: %v", err)
	}
	start := assistantAPIRequest(t, handler, http.MethodPost,
		"/assistant/sessions/"+session.SessionID+"/runs",
		"user-sse", map[string]any{
			"intent": map[string]any{
				"kind": "answer", "answer": map[string]any{"text": "今天上海天气怎么样"},
			},
			"clientRequestId": "stream-resume-run",
		})
	var run assistantRunEnvelope
	if err := json.Unmarshal(start.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v", err)
	}
	worker := runruntime.NewDurableWorker(
		integrationRunRepository,
		integrationRunRepository,
		recoveredRunExecutor{},
		"stream-resume-worker",
	)
	worked, err := worker.ProcessNext(ctx)
	if err != nil || !worked {
		t.Fatalf("complete stream resume run: worked=%t err=%v", worked, err)
	}

	stream := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/runs/"+run.RunID+"/events", "user-sse", nil)
	if stream.Code != http.StatusOK || !strings.Contains(stream.Body.String(), "event:") {
		t.Fatalf("first stream status=%d body=%s", stream.Code, stream.Body.String())
	}
	initialEvents := parseAssistantSSEEventFrames(t, stream.Body.String())
	stored, err := integrationRunRepository.Load(ctx, run.RunID)
	if err != nil {
		t.Fatalf("load stored run: %v", err)
	}
	if stored.State.WireName() == "running" || stored.JournalSequence == 0 {
		t.Fatalf("run must reach terminal state with journal: %+v", stored)
	}
	resumeToken := streaming.NewResumeToken(run.RunID, uint64(stored.JournalSequence))

	restarted := assistantHTTPHandlerWithTurnView(newIntegrationAssistantService())
	resume := assistantAPIRequest(t, restarted, http.MethodGet, "/assistant/runs/"+run.RunID+"/events", "user-sse", nil)
	if resume.Code != http.StatusOK {
		t.Fatalf("resume after restart status=%d", resume.Code)
	}
	if !strings.Contains(resume.Body.String(), resumeToken) &&
		!strings.Contains(resume.Body.String(), run.RunID) {
		t.Fatalf("terminal replay must include its persisted identity: body=%s", resume.Body.String())
	}

	// 使用服务端签发的首个 event id 重新建连。该请求必须只返回严格更大的
	// 序号，证明 Mongo event journal、HTTP Last-Event-ID 和单次 run 的
	// SSE transport 共同满足断点续传语义。
	resumeRequest := httptest.NewRequest(
		http.MethodGet,
		"/assistant/runs/"+run.RunID+"/events",
		nil,
	)
	resumeRequest.Header.Set("X-Client-User-Id", "user-sse")
	resumeRequest.Header.Set("Last-Event-ID", initialEvents[0].id)
	resumedRecorder := httptest.NewRecorder()
	restarted.ServeHTTP(resumedRecorder, resumeRequest)
	if resumedRecorder.Code != http.StatusOK {
		t.Fatalf(
			"Last-Event-ID resume status=%d body=%s",
			resumedRecorder.Code,
			resumedRecorder.Body.String(),
		)
	}
	resumedEvents := parseAssistantSSEEventFrames(
		t,
		resumedRecorder.Body.String(),
	)
	for _, event := range resumedEvents {
		if event.seq <= initialEvents[0].seq {
			t.Fatalf(
				"resumed event must advance strictly: resumeAfter=%d event=%#v",
				initialEvents[0].seq,
				event,
			)
		}
	}

	// SSE journal 只保留有限窗口；terminalSnapshot 是 GetRun、SSE 终态重放与
	// history 的共同无 TTL 真相源。
	var storedAnswerText string
	if stored.TerminalSnapshot == nil {
		t.Fatalf("terminal run is missing durable terminalSnapshot: %#v", stored)
	}
	storedAnswerText = stored.TerminalSnapshot.AnswerText
	if stored.State.WireName() == "completed" && strings.TrimSpace(storedAnswerText) == "" {
		t.Fatalf("completed run is missing durable answer text: %#v", stored)
	}
	if stored.State.WireName() == "failed" && stored.TerminalSnapshot.Failure == nil {
		t.Fatalf("failed run is missing durable canonical failure: %#v", stored)
	}
	if _, err := integrationMongoDB.Collection("assistant_run_events").DeleteMany(
		ctx,
		bson.M{"runId": run.RunID},
	); err != nil {
		t.Fatalf("simulate run event journal expiry: %v", err)
	}
	getAfterExpiry := assistantAPIRequest(
		t,
		restarted,
		http.MethodGet,
		"/assistant/runs/"+run.RunID,
		"user-sse",
		nil,
	)
	if getAfterExpiry.Code != http.StatusOK {
		t.Fatalf(
			"get terminal run after journal expiry: status=%d body=%s",
			getAfterExpiry.Code,
			getAfterExpiry.Body.String(),
		)
	}
	var terminalResponse map[string]any
	if err := json.Unmarshal(getAfterExpiry.Body.Bytes(), &terminalResponse); err != nil {
		t.Fatalf("decode terminal run after journal expiry: %v", err)
	}
	assertAssistantRunEnvelopePublicKeys(t, terminalResponse)
	terminalSnapshot := assertAssistantTerminalSnapshotPublicShape(
		t,
		terminalResponse["terminalSnapshot"],
	)
	if terminalSnapshot["answerText"] != storedAnswerText {
		t.Fatalf(
			"terminal answer after journal expiry=%q want=%q",
			terminalSnapshot["answerText"],
			storedAnswerText,
		)
	}
	if terminalResponse["status"] != stored.State.WireName() {
		t.Fatalf(
			"terminal status after journal expiry=%q want=%q",
			terminalResponse["status"],
			stored.State.WireName(),
		)
	}
	if stored.TerminalSnapshot.Failure != nil && terminalSnapshot["failure"] == nil {
		t.Fatalf(
			"terminal failure after journal expiry is absent: %#v",
			terminalResponse,
		)
	}

	streamAfterExpiry := assistantAPIRequest(
		t,
		restarted,
		http.MethodGet,
		"/assistant/runs/"+run.RunID+"/events",
		"user-sse",
		nil,
	)
	if streamAfterExpiry.Code != http.StatusOK {
		t.Fatalf(
			"terminal stream after journal expiry: status=%d body=%s",
			streamAfterExpiry.Code,
			streamAfterExpiry.Body.String(),
		)
	}
	replayed := parseAssistantSSEEventFrames(t, streamAfterExpiry.Body.String())
	terminalReplay := replayed[len(replayed)-1]
	assertAssistantJSONKeys(t, "terminal SSE payload", terminalReplay.payload, map[string]bool{
		"sessionId":   true,
		"runId":       true,
		"status":      true,
		"resumeToken": true,
		"processes":   true,
		"finalAnswer": true,
	})
	if terminalReplay.eventType != stored.State.WireName() {
		t.Fatalf(
			"terminal replay after journal expiry=%#v want status=%q",
			terminalReplay,
			stored.State.WireName(),
		)
	}
	if stored.State.WireName() == "completed" &&
		terminalReplay.payload["finalAnswer"] != storedAnswerText {
		t.Fatalf(
			"terminal replay answer=%q want=%q",
			terminalReplay.payload["finalAnswer"],
			storedAnswerText,
		)
	}

	history := assistantAPIRequest(
		t,
		restarted,
		http.MethodGet,
		"/assistant/sessions/"+session.SessionID+"/turns",
		"user-sse",
		nil,
	)
	if history.Code != http.StatusOK {
		t.Fatalf(
			"history after journal expiry: status=%d body=%s",
			history.Code,
			history.Body.String(),
		)
	}
	var historyView turnviewmodel.AssistantTurnListView
	if err := json.Unmarshal(history.Body.Bytes(), &historyView); err != nil {
		t.Fatalf("decode history after journal expiry: %v", err)
	}
	if len(historyView.Items) != 1 ||
		historyView.Items[0].TerminalSnapshot == nil ||
		historyView.Items[0].TerminalSnapshot.AnswerText != storedAnswerText {
		t.Fatalf(
			"history must recover canonical terminal snapshot after journal expiry: %#v",
			historyView.Items,
		)
	}

	for _, path := range []string{
		"/assistant/runs/" + run.RunID,
		"/assistant/runs/" + run.RunID + "/events",
	} {
		foreign := assistantAPIRequest(
			t,
			restarted,
			http.MethodGet,
			path,
			"intruder-sse",
			nil,
		)
		if foreign.Code != http.StatusNotFound {
			t.Fatalf(
				"foreign terminal recovery must fail closed: path=%s status=%d body=%s",
				path,
				foreign.Code,
				foreign.Body.String(),
			)
		}
	}
}

// TestAssistantRunWritesScorecardOnCompletion 验证 run 终态时服务端自评
// scorecard 落唯一 AssistantLearningFact 且 eventId 幂等。
func TestAssistantRunWritesScorecardOnCompletion(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	service := newIntegrationAssistantService()
	handler := assistantHTTPHandlerWithTurnView(service)

	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/sessions",
		"user-score", map[string]any{
			"summary": "评分会话", "clientRequestId": "scorecard-session",
		})
	var session assistant.AssistantSession
	if err := json.Unmarshal(create.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode session: %v", err)
	}
	start := assistantAPIRequest(t, handler, http.MethodPost,
		"/assistant/sessions/"+session.SessionID+"/runs",
		"user-score", map[string]any{
			"intent": map[string]any{
				"kind": "answer", "answer": map[string]any{"text": "给我一句鼓励"},
			},
			"clientRequestId": "scorecard-run",
		})
	var run assistantRunEnvelope
	if err := json.Unmarshal(start.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v", err)
	}
	worker := runruntime.NewDurableWorker(
		integrationRunRepository,
		integrationRunRepository,
		recoveredRunExecutor{},
		"scorecard-terminal-worker",
	)
	worked, err := worker.ProcessNext(ctx)
	if err != nil || !worked {
		t.Fatalf("complete scorecard run: worked=%t err=%v", worked, err)
	}
	outboxCount, err := integrationMongoDB.Collection("assistant_run_terminal_outbox").
		CountDocuments(ctx, bson.M{"runId": run.RunID, "outcome": "completed"})
	if err != nil || outboxCount != 1 {
		t.Fatalf("terminal outbox must commit with run: count=%d err=%v", outboxCount, err)
	}
	var terminalDocument bson.M
	if err := integrationMongoDB.Collection("assistant_run_terminal_outbox").FindOne(
		ctx, bson.M{"runId": run.RunID},
	).Decode(&terminalDocument); err != nil {
		t.Fatalf("load terminal outbox document: %v", err)
	}
	for _, field := range []string{
		"runId", "userId", "personaId", "personaContextVersion", "outcome",
		"toolsCalled", "llmModel", "llmTokensUsed", "latencyMs",
		"satisfactionScore", "occurredAt",
	} {
		if _, exists := terminalDocument[field]; !exists {
			t.Fatalf("terminal outbox omits contract fact %q: %v", field, terminalDocument)
		}
	}
	if terminalDocument["llmTokensUsed"] != int64(120) ||
		terminalDocument["latencyMs"] == nil ||
		terminalDocument["personaContextVersion"] != nil ||
		terminalDocument["llmModel"] != nil ||
		terminalDocument["satisfactionScore"] != nil {
		t.Fatalf("terminal facts must be real values or BSON null: %v", terminalDocument)
	}
	claimAt := time.Now().UTC().Add(time.Minute)
	claimed, err := integrationRunRepository.ClaimPendingTerminalEvents(
		ctx, "terminal-owner-a", claimAt, time.Minute, 1,
	)
	if err != nil || len(claimed) != 1 || claimed[0].AttemptCount != 1 {
		t.Fatalf("claim terminal outbox=%+v err=%v", claimed, err)
	}
	retryAt := claimAt.Add(5 * time.Second)
	if err := integrationRunRepository.ScheduleTerminalEventRetry(
		ctx, claimed[0].EventID, "terminal-owner-a", claimAt,
		retryAt, "transport_unavailable",
	); err != nil {
		t.Fatalf("schedule terminal retry: %v", err)
	}
	if beforeDue, err := integrationRunRepository.ClaimPendingTerminalEvents(
		ctx, "terminal-owner-b", retryAt.Add(-time.Millisecond), time.Minute, 1,
	); err != nil || len(beforeDue) != 0 {
		t.Fatalf("claim terminal before nextAttemptAt=%+v err=%v", beforeDue, err)
	}
	retried, err := integrationRunRepository.ClaimPendingTerminalEvents(
		ctx, "terminal-owner-b", retryAt, 10*time.Second, 1,
	)
	if err != nil || len(retried) != 1 || retried[0].AttemptCount != 2 {
		t.Fatalf("claim due terminal retry=%+v err=%v", retried, err)
	}
	if err := integrationRunRepository.AcknowledgeTerminalEvent(
		ctx, retried[0].EventID, "terminal-owner-a", retryAt,
	); !errors.Is(err, runruntime.ErrTerminalEventClaimLost) {
		t.Fatalf("wrong terminal owner checkpoint error=%v, want claim lost", err)
	}
	expiredAt := retryAt.Add(10 * time.Second)
	if err := integrationRunRepository.ScheduleTerminalEventRetry(
		ctx, retried[0].EventID, "terminal-owner-b", expiredAt,
		expiredAt.Add(time.Second), "expired_owner",
	); !errors.Is(err, runruntime.ErrTerminalEventClaimLost) {
		t.Fatalf("expired terminal owner retry error=%v, want claim lost", err)
	}
	if err := integrationRunRepository.AcknowledgeTerminalEvent(
		ctx, retried[0].EventID, "terminal-owner-b", expiredAt,
	); !errors.Is(err, runruntime.ErrTerminalEventClaimLost) {
		t.Fatalf("expired terminal owner checkpoint error=%v, want claim lost", err)
	}
	takeover, err := integrationRunRepository.ClaimPendingTerminalEvents(
		ctx, "terminal-owner-c", expiredAt, time.Minute, 1,
	)
	if err != nil || len(takeover) != 1 || takeover[0].AttemptCount != 3 {
		t.Fatalf("expired terminal lease takeover=%+v err=%v", takeover, err)
	}
	resumeAt := time.Now().UTC()
	if err := integrationRunRepository.ScheduleTerminalEventRetry(
		ctx, takeover[0].EventID, "terminal-owner-c", resumeAt, resumeAt, "test_resume",
	); err != nil {
		t.Fatalf("release terminal retry to production relay: %v", err)
	}
	preRelayFacts, err := integrationMongoDB.Collection("assistant_learning_facts").
		CountDocuments(ctx, bson.M{"eventId": "turn:" + run.RunID + ":completion"})
	if err != nil || preRelayFacts != 0 {
		t.Fatalf("learning fact must only be appended by relay: count=%d err=%v", preRelayFacts, err)
	}
	relay := integrationRunTerminalRelay("scorecard-terminal-relay")
	processed, err := relay.FlushOnce(ctx)
	if err != nil || processed != 1 {
		t.Fatalf("relay terminal scorecard: processed=%d err=%v", processed, err)
	}
	stream := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/runs/"+run.RunID+"/events", "user-score", nil)
	if stream.Code != http.StatusOK {
		t.Fatalf("stream status=%d", stream.Code)
	}
	awaitAssistantRunScorecard(t, ctx, run.RunID)

	// 重复完成（终态重放）不产生第二条 scorecard。
	replayStream := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/runs/"+run.RunID+"/events", "user-score", nil)
	if replayStream.Code != http.StatusOK {
		t.Fatalf("replay stream status=%d", replayStream.Code)
	}
	processed, err = relay.FlushOnce(ctx)
	if err != nil || processed != 0 {
		t.Fatalf("processed terminal outbox must not replay: processed=%d err=%v", processed, err)
	}
	count, err := integrationMongoDB.Collection("assistant_learning_facts").
		CountDocuments(ctx, bson.M{
			"eventId":  "turn:" + run.RunID + ":completion",
			"factType": "service_scorecard",
		})
	if err != nil || count != 1 {
		t.Fatalf("scorecard must dedupe on replay: count=%d err=%v", count, err)
	}
}

// TestSkillSubscriptionCreateIdempotent 验证订阅一次创建的唯一约束幂等。
func TestSkillSubscriptionCreateIdempotent(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	handler := assistantHTTPHandlerWithTurnView(newIntegrationAssistantService())

	body := map[string]any{
		"skillId":  "news_briefing",
		"domainId": "news",
		"trigger": map[string]any{
			"type":     "cron",
			"cron":     "30 8 * * *",
			"timezone": "UTC",
		},
		"clientRequestId": "sub-req-1",
	}
	first := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/skill-subscriptions", "user-sub-1", body)
	if first.Code != http.StatusCreated && first.Code != http.StatusOK {
		t.Fatalf("create subscription status=%d body=%s", first.Code, first.Body.String())
	}
	var created skillmodel.SkillSubscription
	if err := json.Unmarshal(first.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode subscription: %v", err)
	}
	replay := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/skill-subscriptions", "user-sub-1", body)
	var replayed skillmodel.SkillSubscription
	if err := json.Unmarshal(replay.Body.Bytes(), &replayed); err != nil {
		t.Fatalf("decode replayed subscription: %v", err)
	}
	if replayed.SubscriptionID != created.SubscriptionID {
		t.Fatalf("idempotent replay must return first subscription: first=%s replay=%s",
			created.SubscriptionID, replayed.SubscriptionID)
	}
	count, err := integrationMongoDB.Collection("skill_subscriptions").
		CountDocuments(ctx, bson.M{"owner.ownerId": "user-sub-1"})
	if err != nil || count != 1 {
		t.Fatalf("subscription count=%d err=%v", count, err)
	}
}

// TestSkillSubscriptionStatusServerOwnedCas 验证状态 set 的服务端收敛语义：
// 目标状态已满足时 no-op 返回存量、不推进 updatedAt。
func TestSkillSubscriptionStatusServerOwnedCas(t *testing.T) {
	resetIntegrationState(t)
	handler := assistantHTTPHandlerWithTurnView(newIntegrationAssistantService())

	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/skill-subscriptions",
		"user-sub-cas", map[string]any{
			"skillId":  "stock_sentinel",
			"domainId": "finance",
			"trigger": map[string]any{
				"type":     "cron",
				"cron":     "0 9 * * *",
				"timezone": "UTC",
			},
			"clientRequestId": "sub-cas-create",
		})
	var created skillmodel.SkillSubscription
	if err := json.Unmarshal(create.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode subscription: %v", err)
	}
	statusPath := "/assistant/skill-subscriptions/" + created.SubscriptionID + "/status"
	paused := assistantAPIRequest(t, handler, http.MethodPatch, statusPath, "user-sub-cas",
		map[string]any{"status": "paused", "clientRequestId": "sub-cas-pause"})
	var pausedSub skillmodel.SkillSubscription
	if err := json.Unmarshal(paused.Body.Bytes(), &pausedSub); err != nil {
		t.Fatalf("decode paused: %v", err)
	}
	if pausedSub.Status != "paused" {
		t.Fatalf("status transition failed: %+v", pausedSub)
	}
	noop := assistantAPIRequest(t, handler, http.MethodPatch, statusPath, "user-sub-cas",
		map[string]any{"status": "paused", "clientRequestId": "sub-cas-pause"})
	var noopSub skillmodel.SkillSubscription
	if err := json.Unmarshal(noop.Body.Bytes(), &noopSub); err != nil {
		t.Fatalf("decode noop: %v", err)
	}
	if !noopSub.UpdatedAt.Equal(pausedSub.UpdatedAt) {
		t.Fatalf("no-op set must not advance updatedAt: first=%v noop=%v",
			pausedSub.UpdatedAt, noopSub.UpdatedAt)
	}
}

// TestSkillSubscriptionOwnerIsolation 验证订阅防枚举。
func TestSkillSubscriptionOwnerIsolation(t *testing.T) {
	resetIntegrationState(t)
	handler := assistantHTTPHandlerWithTurnView(newIntegrationAssistantService())

	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/skill-subscriptions",
		"owner-sub", map[string]any{
			"skillId":  "daily_assistant",
			"domainId": "general",
			"trigger": map[string]any{
				"type":     "cron",
				"cron":     "0 8 * * *",
				"timezone": "UTC",
			},
			"clientRequestId": "owner-sub-create",
		})
	var created skillmodel.SkillSubscription
	if err := json.Unmarshal(create.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode subscription: %v", err)
	}
	foreign := assistantAPIRequest(t, handler, http.MethodGet,
		"/assistant/skill-subscriptions/"+created.SubscriptionID, "intruder", nil)
	if foreign.Code == http.StatusOK {
		t.Fatalf("foreign subscription read must fail: status=%d", foreign.Code)
	}
}

// TestSkillConsentRevokeImmediateEnforcement 验证已知敏感 Skill 的 canonical
// AssistantRun 启动策略在撤权后立即失败关闭；不得落入第二条 Session 执行路径。
func TestSkillConsentRevokeImmediateEnforcement(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	commands := consentapplication.NewCommandFacade(integrationConsentStore, nil)

	if _, err := commands.Grant(
		ctx, "enforce-grant", "enforce-user", "travel_companion",
		[]string{"assistant.learning.feedback_context.read"},
	); err != nil {
		t.Fatalf("grant consent: %v", err)
	}
	granted, err := integrationRunCommands.Start(ctx, runruntime.StartCommand{
		UserID:            "enforce-user",
		PersonaID:         "enforce-user:persona",
		SessionID:         "consent-gate-session",
		ClientRequestID:   "consent-gate-run",
		IntentKind:        "answer",
		InputText:         "看看我当前的行程",
		RequestedSkillID:  "travel_companion",
		RequestedDomainID: "travel",
	})
	if err != nil || granted.RunID == "" {
		t.Fatalf("granted sensitive run start: run=%#v err=%v", granted, err)
	}

	if _, err := commands.Revoke(
		ctx, "enforce-revoke", "enforce-user", "travel_companion",
	); err != nil {
		t.Fatalf("revoke consent: %v", err)
	}
	_, err = integrationRunCommands.Start(ctx, runruntime.StartCommand{
		UserID:            "enforce-user",
		PersonaID:         "enforce-user:persona",
		SessionID:         "consent-gate-session",
		ClientRequestID:   "consent-gate-run-revoked",
		IntentKind:        "answer",
		InputText:         "再看一次",
		RequestedSkillID:  "travel_companion",
		RequestedDomainID: "travel",
	})
	if err == nil || !strings.Contains(err.Error(), "ASSISTANT.USER.skill_consent_required") {
		t.Fatalf("revoked consent must deny canonical run start: %v", err)
	}
	count, countErr := integrationMongoDB.Collection("assistant_runs").CountDocuments(
		ctx,
		bson.M{"userId": "enforce-user"},
	)
	if countErr != nil || count != 1 {
		t.Fatalf("revoked start must not persist a second run: count=%d err=%v", count, countErr)
	}
}

type integrationServiceCredentials string

func (credential integrationServiceCredentials) AuthorizationHeader(
	context.Context,
) (string, error) {
	return "Bearer " + string(credential), nil
}

func integrationNotificationCommandWriter(
	t *testing.T,
) ports.NotificationAppMessageCommandWriter {
	t.Helper()
	baseURL := strings.TrimSpace(os.Getenv("QWQ_TEST_NOTIFICATION_BASE_URL"))
	token := strings.TrimSpace(os.Getenv("QWQ_TEST_SERVICE_AUTH_TOKEN"))
	if baseURL == "" || token == "" {
		// 未预置真实 notification-service 时，以本地 HTTP 端点承接协作者边界
		// （与本文件族 chat 协作者的 httptest 先例一致）：assistant 侧仍走真实
		// notificationclient 代码路径（鉴权头、Idempotency-Key、契约 decode），
		// 被测系统（Redis 租约去重）不因协作者缺位而空转或跳过。
		token = "integration-notification-token"
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodPost {
				http.NotFound(w, r)
				return
			}
			if r.Header.Get("Authorization") != "Bearer "+token {
				http.Error(w, "missing service authorization", http.StatusUnauthorized)
				return
			}
			if strings.TrimSpace(r.Header.Get("Idempotency-Key")) == "" {
				http.Error(w, "missing idempotency key", http.StatusBadRequest)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"messageId": "msg-" + strings.TrimSpace(r.Header.Get("Idempotency-Key")),
			})
		}))
		t.Cleanup(server.Close)
		baseURL = server.URL
	}
	client, err := notificationclient.NewClient(
		http.DefaultClient,
		baseURL,
		integrationServiceCredentials(token),
	)
	if err != nil {
		t.Fatalf("create notification integration client: %v", err)
	}
	return client
}

func integrationDeliveryPolicyReader(
	t *testing.T,
) ports.AssistantDeliveryPolicyReader {
	t.Helper()
	const userID = "lease-user"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet ||
			r.URL.Path != serviceclients.UserResolveAssistantDeliveryPolicyPath(userID) {
			http.NotFound(w, r)
			return
		}
		if r.Header.Get("Authorization") != "Bearer integration-user-policy-token" {
			http.Error(w, "missing service authorization", http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"userId":           userID,
			"assistantEnabled": true,
			"version":          1,
			"updatedAt":        "2026-07-19T08:00:00Z",
		})
	}))
	t.Cleanup(server.Close)
	client, err := sessionorchestration.NewUserDeliveryPolicyClient(
		server.URL,
		integrationServiceCredentials("integration-user-policy-token"),
		server.Client(),
	)
	if err != nil {
		t.Fatalf("create user delivery policy integration client: %v", err)
	}
	return client
}

type integrationProactiveFinalModel struct{}

func (integrationProactiveFinalModel) ModelExecutionCapabilities() runorchestration.ModelExecutionCapabilities {
	return runorchestration.ModelExecutionCapabilities{
		ToolCalling:     true,
		ParallelTools:   true,
		ReasoningEffort: true,
	}
}

func (integrationProactiveFinalModel) Complete(
	context.Context,
	runorchestration.ModelRequest,
) (runorchestration.ModelResponse, error) {
	return runorchestration.ModelResponse{Text: "旅行主动 Skill 已生成本期安排"}, nil
}

// TestSkillSubscriptionCronLeaseNoDuplicate 验证同一 tick 窗口的 Redis 租约：
// 两次 tick 并发（同窗口）只投递一次；lease key 带 TTL。
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-context-proactive-runtime/spec.md#gwt-001
func TestSkillSubscriptionCronLeaseNoDuplicate(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	loop := runorchestration.NewAgentLoop(
		integrationChatMentionSkillRuntime{},
		runorchestration.ReactRuntime{
			Model: integrationProactiveFinalModel{},
		},
		nil,
	)
	loop.Catalog = skillfixture.StaticLoader{Manifests: []skillpkg.Manifest{{
		SkillID:     "news_briefing",
		DomainID:    "assistant",
		DisplayName: "资讯简报",
		Activation:  skillpkg.ActivationProactive,
	}}}
	runCommands := runruntime.NewCommandService(
		integrationRunRepository,
		runruntime.SessionResolverFunc(func(
			context.Context,
			string,
			string,
		) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		time.Now,
		nil,
		runruntime.WithPolicyResolver(integrationRunPolicyResolver()),
	)
	runWorker := runruntime.NewDurableWorker(
		integrationRunRepository,
		integrationRunRepository,
		runorchestration.NewDurableRunExecutor(loop),
		"api-integration-proactive-worker",
	)
	workerContext, cancelWorker := context.WithTimeout(ctx, 15*time.Second)
	defer cancelWorker()
	go runWorker.Run(workerContext)
	service := newIntegrationAssistantService(
		sessionorchestration.WithNotificationAppMessageCommandWriter(
			integrationNotificationCommandWriter(t),
		),
		sessionorchestration.WithAssistantDeliveryPolicyReader(
			integrationDeliveryPolicyReader(t),
		),
		sessionorchestration.WithSkillCatalog(loop.Catalog),
		sessionorchestration.WithRunCommandService(runCommands),
	)
	handler := assistantHTTPHandlerWithTurnView(service)

	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/skill-subscriptions",
		"lease-user", map[string]any{
			"skillId":  "news_briefing",
			"domainId": "assistant",
			"trigger": map[string]any{
				"type":     "cron",
				"cron":     "30 8 * * *",
				"timezone": "UTC",
			},
			"clientRequestId": "lease-subscription-create",
			"searchQueryPlan": map[string]any{
				"rawText": "请基于已授权上下文生成本期旅行资讯简报",
				"queries": []string{},
			},
		})
	if create.Code != http.StatusCreated && create.Code != http.StatusOK {
		t.Fatalf("create subscription status=%d body=%s", create.Code, create.Body.String())
	}
	var created skillmodel.SkillSubscription
	if err := json.Unmarshal(create.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode lease subscription: %v", err)
	}
	if created.DeliveryState.NextAttemptAt == nil {
		t.Fatalf("created subscription has no nextAttemptAt: %+v", created)
	}
	tickAt := created.DeliveryState.NextAttemptAt.UTC().Format(time.RFC3339)
	first, err := service.TickSkillSubscriptionCron(
		ctx,
		skillmodel.SkillSubscriptionCronTickInput{Now: tickAt},
	)
	if err != nil {
		t.Fatalf("first tick: %v", err)
	}
	if first.ProcessedCount != 1 {
		var proactiveRun runruntime.Run
		_ = integrationMongoDB.Collection("assistant_runs").FindOne(
			ctx,
			bson.M{"requestedSkillId": "news_briefing"},
		).Decode(&proactiveRun)
		t.Fatalf(
			"first tick must process one subscription: result=%+v runState=%s terminalReason=%q snapshot=%+v",
			first,
			proactiveRun.State.WireName(),
			proactiveRun.TerminalReason,
			proactiveRun.TerminalSnapshot,
		)
	}
	second, err := service.TickSkillSubscriptionCron(
		ctx,
		skillmodel.SkillSubscriptionCronTickInput{Now: tickAt},
	)
	if err != nil {
		t.Fatalf("second tick: %v", err)
	}
	if second.ProcessedCount != 0 {
		t.Fatalf("same-window tick must be deduplicated by redis lease: %+v", second)
	}
	deliveryID := "assistant-proactive-" + created.SubscriptionID + "-" +
		created.DeliveryState.NextAttemptAt.UTC().Format("200601021504")
	runCount, err := integrationMongoDB.Collection("assistant_runs").CountDocuments(
		ctx,
		bson.M{"clientRequestId": deliveryID + ":run"},
	)
	if err != nil {
		t.Fatalf("count proactive AssistantRun: %v", err)
	}
	if runCount != 1 {
		t.Fatalf("proactive ticks created %d canonical runs; want exactly one", runCount)
	}
}

// TestAssistantSessionLifecycleQueryAndCancel 验证会话生命周期查询面与
// 取消命令在真实 Mongo 上的行为：List 分页、终态过滤、cancel CAS 与幂等、
// 新 handler 实例（模拟重启）仍可读取 cancelled 终态。
func TestAssistantSessionLifecycleQueryAndCancel(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	handler := assistantHTTPHandlerWithTurnView(newIntegrationAssistantService())
	userID := "user-lifecycle-1"

	// 造 3 个会话
	sessionIDs := []string{}
	for _, requestID := range []string{"lc-conv-1", "lc-conv-2", "lc-conv-3"} {
		created := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/sessions", userID,
			map[string]any{"summary": "生命周期验证", "clientRequestId": requestID})
		if created.Code != http.StatusCreated {
			t.Fatalf("create session status=%d body=%s", created.Code, created.Body.String())
		}
		var session assistant.AssistantSession
		if err := json.Unmarshal(created.Body.Bytes(), &session); err != nil {
			t.Fatalf("decode session: %v", err)
		}
		sessionIDs = append(sessionIDs, session.SessionID)
	}

	// List 分页：limit=2 → 第一页 2 条 + cursor；第二页 1 条无 cursor
	page1Resp := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/sessions?limit=2", userID, nil)
	if page1Resp.Code != http.StatusOK {
		t.Fatalf("list sessions status=%d body=%s", page1Resp.Code, page1Resp.Body.String())
	}
	var page1 assistant.AssistantSessionListView
	if err := json.Unmarshal(page1Resp.Body.Bytes(), &page1); err != nil {
		t.Fatalf("decode sessions page1: %v", err)
	}
	if len(page1.Items) != 2 || page1.NextCursor == "" {
		t.Fatalf("page1 must have 2 items + cursor, got %d items cursor=%q", len(page1.Items), page1.NextCursor)
	}
	page2Resp := assistantAPIRequest(t, handler, http.MethodGet,
		"/assistant/sessions?limit=2&cursor="+page1.NextCursor, userID, nil)
	var page2 assistant.AssistantSessionListView
	if err := json.Unmarshal(page2Resp.Body.Bytes(), &page2); err != nil {
		t.Fatalf("decode sessions page2: %v", err)
	}
	if len(page2.Items) != 1 || page2.NextCursor != "" {
		t.Fatalf("page2 must be terminal single item, got %d items cursor=%q", len(page2.Items), page2.NextCursor)
	}

	// 其他用户看不到
	otherResp := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/sessions", "user-other", nil)
	var otherPage assistant.AssistantSessionListView
	if err := json.Unmarshal(otherResp.Body.Bytes(), &otherPage); err != nil {
		t.Fatalf("decode other user page: %v", err)
	}
	if len(otherPage.Items) != 0 {
		t.Fatalf("owner isolation violated: %#v", otherPage.Items)
	}

	// 启动 run 并取消：accepted → cancelled（worker 尚未领取 run，直接验证
	// AssistantRun aggregate 的 cancel CAS 与幂等终态）。
	target := sessionIDs[0]
	startResp := assistantAPIRequest(t, handler, http.MethodPost,
		"/assistant/sessions/"+target+"/runs", userID,
		map[string]any{
			"intent": map[string]any{
				"kind": "answer", "answer": map[string]any{"text": "帮我查一下天气"},
			},
			"clientRequestId": "lc-run-1",
		})
	if startResp.Code != http.StatusCreated {
		t.Fatalf("start run status=%d body=%s", startResp.Code, startResp.Body.String())
	}
	var startedTurn assistantRunEnvelope
	if err := json.Unmarshal(startResp.Body.Bytes(), &startedTurn); err != nil {
		t.Fatalf("decode started turn: %v", err)
	}
	if startedTurn.Status != "accepted" {
		t.Fatalf("started run must be accepted before worker claim, got %s", startedTurn.Status)
	}

	cancelResp := assistantAPIInjectedRunCommand(
		t,
		handler,
		"/assistant/runs/"+startedTurn.RunID+"/cancel",
		userID,
		"lc-cancel-1",
	)
	if cancelResp.Code != http.StatusOK {
		t.Fatalf("cancel run status=%d body=%s", cancelResp.Code, cancelResp.Body.String())
	}
	var cancelledTurn assistantRunEnvelope
	if err := json.Unmarshal(cancelResp.Body.Bytes(), &cancelledTurn); err != nil {
		t.Fatalf("decode cancelled turn: %v", err)
	}
	if cancelledTurn.Status != "cancelled" ||
		cancelledTurn.CompletedAt == "" ||
		cancelledTurn.TerminalSnapshot == nil {
		t.Fatalf("cancel must transition to cancelled terminal, got %#v", cancelledTurn)
	}

	// 幂等：重复 cancel 返回 cancelled 200
	cancelAgain := assistantAPIInjectedRunCommand(
		t,
		handler,
		"/assistant/runs/"+startedTurn.RunID+"/cancel",
		userID,
		"lc-cancel-1",
	)
	if cancelAgain.Code != http.StatusOK {
		t.Fatalf("repeated cancel status=%d body=%s", cancelAgain.Code, cancelAgain.Body.String())
	}
	var replayedCancellation assistantRunEnvelope
	if err := json.Unmarshal(cancelAgain.Body.Bytes(), &replayedCancellation); err != nil {
		t.Fatalf("decode repeated cancellation: %v", err)
	}
	if replayedCancellation.CompletedAt == "" ||
		replayedCancellation.CompletedAt != cancelledTurn.CompletedAt ||
		replayedCancellation.TerminalSnapshot == nil {
		t.Fatalf(
			"repeated cancel must preserve first terminal snapshot and timestamp: %#v",
			replayedCancellation,
		)
	}

	// Mongo 落盘核验 + 新 handler（模拟重启）读取终态与轮次列表
	storedStatus, err := integrationRunRepository.Load(ctx, startedTurn.RunID)
	if err != nil {
		t.Fatalf("read cancelled run from mongo: %v", err)
	}
	if storedStatus.State.WireName() != "cancelled" ||
		storedStatus.CompletedAt == nil ||
		storedStatus.TerminalSnapshot == nil {
		t.Fatalf("mongo run must retain cancelled terminal snapshot: %#v", storedStatus)
	}

	restartedHandler := assistantHTTPHandlerWithTurnView(newIntegrationAssistantService())
	turnsResp := assistantAPIRequest(t, restartedHandler, http.MethodGet,
		"/assistant/sessions/"+target+"/turns", userID, nil)
	if turnsResp.Code != http.StatusOK {
		t.Fatalf("list turns status=%d body=%s", turnsResp.Code, turnsResp.Body.String())
	}
	var turnsView turnviewmodel.AssistantTurnListView
	if err := json.Unmarshal(turnsResp.Body.Bytes(), &turnsView); err != nil {
		t.Fatalf("decode turns view: %v", err)
	}
	if len(turnsView.Items) != 1 || turnsView.Items[0].Status != "cancelled" ||
		turnsView.Items[0].InputText != "帮我查一下天气" ||
		turnsView.Items[0].TerminalSnapshot == nil {
		t.Fatalf("turns view must expose cancelled turn summary after restart, got %#v", turnsView.Items)
	}

	cancelledStream := assistantAPIRequest(t, restartedHandler, http.MethodGet,
		"/assistant/runs/"+startedTurn.RunID+"/events", userID, nil)
	if cancelledStream.Code != http.StatusOK {
		t.Fatalf(
			"cancelled terminal stream status=%d body=%s",
			cancelledStream.Code,
			cancelledStream.Body.String(),
		)
	}
	cancelledFrames := parseAssistantSSEEventFrames(t, cancelledStream.Body.String())
	if cancelledFrames[len(cancelledFrames)-1].eventType != "cancelled" {
		t.Fatalf("cancelled stream must replay terminal event: %#v", cancelledFrames)
	}

	// 非 owner 轮次查询防枚举
	foreignTurns := assistantAPIRequest(t, restartedHandler, http.MethodGet,
		"/assistant/sessions/"+target+"/turns", "user-other", nil)
	if foreignTurns.Code != http.StatusNotFound {
		t.Fatalf("non-owner turns must 404, got %d body=%s", foreignTurns.Code, foreignTurns.Body.String())
	}
}
