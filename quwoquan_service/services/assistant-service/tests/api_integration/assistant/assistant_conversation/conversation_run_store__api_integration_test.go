// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/spec.md#sit-001
// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-sync-contract/spec.md#gwt-001
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/generated/serviceclients"
	"quwoquan_service/runtime/streaming"
	assistanthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/notificationclient"
)

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

func assertAssistantTurnEnvelopePublicKeys(
	t *testing.T,
	response map[string]any,
) {
	t.Helper()
	allowed := map[string]bool{
		"turnId":           true,
		"conversationId":   true,
		"turnType":         true,
		"status":           true,
		"skillId":          true,
		"domainId":         true,
		"input":            true,
		"trigger":          true,
		"streamState":      true,
		"terminalSnapshot": true,
		"traceId":          true,
		"createdAt":        true,
		"completedAt":      true,
	}
	for key := range response {
		if !allowed[key] {
			t.Fatalf("AssistantTurn response leaked non-contract field %q: %#v", key, response)
		}
	}
	for _, required := range []string{
		"turnId",
		"conversationId",
		"status",
		"input",
		"trigger",
		"streamState",
		"traceId",
		"createdAt",
	} {
		if _, found := response[required]; !found {
			t.Fatalf("AssistantTurn response is missing declared field %q: %#v", required, response)
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

func TestAssistantRunEventStoreRejectsSequenceCorruption(t *testing.T) {
	ctx := context.Background()
	const runID = "run-event-sequence-api"
	first := assistantPersistedRunEvent(runID, 1, "first")

	if err := integrationConversationRunStore.AppendRunEvent(ctx, runID, first); err != nil {
		t.Fatalf("append first Mongo run event: %v", err)
	}
	if err := integrationConversationRunStore.AppendRunEvent(ctx, runID, first); err != nil {
		t.Fatalf("replay identical Mongo run event: %v", err)
	}
	if err := integrationConversationRunStore.AppendRunEvent(
		ctx,
		runID,
		assistantPersistedRunEvent(runID, 1, "divergent"),
	); err == nil {
		t.Fatal("Mongo store accepted a divergent replay")
	}
	if err := integrationConversationRunStore.AppendRunEvent(
		ctx,
		runID,
		assistantPersistedRunEvent(runID, 3, "gap"),
	); err == nil {
		t.Fatal("Mongo store accepted a sequence gap")
	}
	if err := integrationConversationRunStore.AppendRunEvent(
		ctx,
		runID,
		assistantPersistedRunEvent(runID, 2, "second"),
	); err != nil {
		t.Fatalf("append contiguous Mongo run event: %v", err)
	}

	events, err := integrationConversationRunStore.ListRunEvents(ctx, runID, 0, 10)
	if err != nil {
		t.Fatalf("list Mongo run events: %v", err)
	}
	if len(events) != 2 || events[0].Seq != 1 || events[1].Seq != 2 {
		t.Fatalf("Mongo event sequence = %#v, want seq [1, 2]", events)
	}
}

func assistantPersistedRunEvent(
	runID string,
	seq uint64,
	text string,
) streaming.Envelope {
	const eventType = "process_append"
	return streaming.Envelope{
		EventID:   fmt.Sprintf("%s:%d", runID, seq),
		StreamID:  runID,
		Event:     eventType,
		EventType: eventType,
		Seq:       seq,
		Payload:   map[string]any{"text": text},
		CreatedAt: time.Date(2026, 7, 24, 0, 0, int(seq), 0, time.UTC),
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
		count, err := integrationMongoDB.Collection("assistant_scorecard_facts").
			CountDocuments(waitCtx, bson.M{"_id": "run:" + turnID})
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

// TestAssistantConversationCreatePersistedAndIdempotent 验证一次创建：
// 会话持久化到 assistant_conversations，相同 clientRequestId 重放返回首个会话，
// 新服务实例（模拟重启）仍可读。
func TestAssistantConversationCreatePersistedAndIdempotent(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()

	create := map[string]any{
		"summary":         "商用闭环验证会话",
		"clientRequestId": "conv-req-1",
	}
	first := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/conversations", "user-conv-1", create)
	if first.Code != http.StatusCreated {
		t.Fatalf("create conversation status=%d body=%s", first.Code, first.Body.String())
	}
	var created assistant.AssistantConversation
	if err := json.Unmarshal(first.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}
	replay := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/conversations", "user-conv-1", create)
	var replayed assistant.AssistantConversation
	if err := json.Unmarshal(replay.Body.Bytes(), &replayed); err != nil {
		t.Fatalf("decode replayed conversation: %v", err)
	}
	if replayed.ConversationID != created.ConversationID {
		t.Fatalf("idempotent replay must return first conversation: first=%s replay=%s",
			created.ConversationID, replayed.ConversationID)
	}
	count, err := integrationMongoDB.Collection("assistant_conversations").
		CountDocuments(ctx, bson.M{"userId": "user-conv-1"})
	if err != nil || count != 1 {
		t.Fatalf("persisted conversation count=%d err=%v", count, err)
	}

	// 模拟重启：全新 service 实例（无进程内状态）仍能读到会话。
	restarted := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()
	get := assistantAPIRequest(t, restarted, http.MethodGet,
		"/assistant/conversations/"+created.ConversationID, "user-conv-1", nil)
	if get.Code != http.StatusOK {
		t.Fatalf("conversation must survive restart: status=%d body=%s", get.Code, get.Body.String())
	}
}

// TestAssistantCommandIdentityRequiresMatchedHeaderAndBody ensures the
// metadata-required replay identity cannot split between HTTP transport and
// persisted aggregate identity.
func TestAssistantCommandIdentityRequiresMatchedHeaderAndBody(t *testing.T) {
	resetIntegrationState(t)
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()

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
				"/assistant/conversations",
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
		"/assistant/conversations",
		"identity-user",
		map[string]any{"clientRequestId": "identity-conversation"},
	)
	if create.Code != http.StatusCreated {
		t.Fatalf("create identity conversation: status=%d body=%s", create.Code, create.Body.String())
	}
	var conversation assistant.AssistantConversation
	if err := json.Unmarshal(create.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode identity conversation: %v", err)
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
				"/assistant/conversations/"+conversation.ConversationID+"/runs",
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
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()
	const (
		userID      = "run-context-owner"
		sessionID   = "session-run-context"
		pageID      = "assistant_dialog"
		surfaceID   = "personal_assistant_dialog_surface"
		routeID     = "/assistant"
		operationID = "StartAssistantRun"
		traceID     = "trace-run-context"
	)

	create := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/conversations",
		userID,
		map[string]any{"clientRequestId": "run-context-conversation"},
	)
	if create.Code != http.StatusCreated {
		t.Fatalf("create context conversation: status=%d body=%s", create.Code, create.Body.String())
	}
	var conversation assistant.AssistantConversation
	if err := json.Unmarshal(create.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode context conversation: %v", err)
	}

	untrusted := httptest.NewRequest(
		http.MethodPost,
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		strings.NewReader(
			`{"input":{"text":"context"},"clientRequestId":"run-context-untrusted","requestContext":{"traceId":"forged"}}`,
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
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		strings.NewReader(
			`{"input":{"text":"context"},"clientRequestId":"run-context-command"}`,
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
	request.Header.Set("X-Trace-Id", traceID)
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
	assertAssistantTurnEnvelopePublicKeys(t, response)
	turnID, _ := response["turnId"].(string)
	if turnID == "" || response["traceId"] != traceID {
		t.Fatalf("run response=%#v, want turnId and traceId=%q", response, traceID)
	}

	stored, found, err := integrationConversationRunStore.GetTurn(
		context.Background(),
		turnID,
	)
	if err != nil || !found {
		t.Fatalf("load persisted context run: found=%v err=%v", found, err)
	}
	if stored.UserID != userID || stored.TraceID != traceID {
		t.Fatalf("stored run user/trace=%q/%q", stored.UserID, stored.TraceID)
	}
	wantContext := assistant.AssistantRunRequestContext{
		SessionID:   sessionID,
		PageID:      pageID,
		SurfaceID:   surfaceID,
		RouteID:     routeID,
		OperationID: operationID,
		TraceID:     traceID,
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
		"/assistant/runs/"+turnID,
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
	assertAssistantTurnEnvelopePublicKeys(t, getResponse)
}

// TestAssistantConversationOwnerIsolation 验证 owner 隔离与匿名拒绝。
func TestAssistantConversationOwnerIsolation(t *testing.T) {
	resetIntegrationState(t)
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()

	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/conversations",
		"owner-a", map[string]any{
			"summary": "私密会话", "clientRequestId": "owner-isolation-conversation",
		})
	var created assistant.AssistantConversation
	if err := json.Unmarshal(create.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}

	foreign := assistantAPIRequest(t, handler, http.MethodGet,
		"/assistant/conversations/"+created.ConversationID, "intruder-b", nil)
	if foreign.Code != http.StatusNotFound {
		t.Fatalf("foreign read must be not_found: status=%d body=%s", foreign.Code, foreign.Body.String())
	}
	anonymous := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/conversations",
		"", map[string]any{"summary": "匿名"})
	if anonymous.Code != http.StatusUnauthorized {
		t.Fatalf("anonymous create must be 401: status=%d body=%s", anonymous.Code, anonymous.Body.String())
	}
}

// TestAssistantRunStartPersistedAndIdempotent 验证 run 一次创建、幂等重放与重启后可读。
func TestAssistantRunStartPersistedAndIdempotent(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()

	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/conversations",
		"user-run-1", map[string]any{
			"summary": "run 会话", "clientRequestId": "run-persistence-conversation",
		})
	var conversation assistant.AssistantConversation
	if err := json.Unmarshal(create.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}
	startBody := map[string]any{
		"input":           map[string]any{"text": "帮我看看今天的天气"},
		"clientRequestId": "run-req-1",
	}
	runPath := "/assistant/conversations/" + conversation.ConversationID + "/runs"
	first := assistantAPIRequest(t, handler, http.MethodPost, runPath, "user-run-1", startBody)
	if first.Code != http.StatusCreated {
		t.Fatalf("start run status=%d body=%s", first.Code, first.Body.String())
	}
	var run assistant.AssistantTurn
	if err := json.Unmarshal(first.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v", err)
	}
	replay := assistantAPIRequest(t, handler, http.MethodPost, runPath, "user-run-1", startBody)
	var replayedRun assistant.AssistantTurn
	if err := json.Unmarshal(replay.Body.Bytes(), &replayedRun); err != nil {
		t.Fatalf("decode replayed run: %v", err)
	}
	if replayedRun.TurnID != run.TurnID {
		t.Fatalf("idempotent replay must return first run: first=%s replay=%s", run.TurnID, replayedRun.TurnID)
	}
	count, err := integrationMongoDB.Collection("assistant_runs").
		CountDocuments(ctx, bson.M{"conversationId": conversation.ConversationID})
	if err != nil || count != 1 {
		t.Fatalf("persisted run count=%d err=%v", count, err)
	}

	restarted := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()
	get := assistantAPIRequest(t, restarted, http.MethodGet, "/assistant/runs/"+run.TurnID, "user-run-1", nil)
	if get.Code != http.StatusOK {
		t.Fatalf("run must survive restart: status=%d body=%s", get.Code, get.Body.String())
	}
}

// TestAssistantRunOwnerIsolation 验证 run 的 owner 隔离与匿名拒绝。
func TestAssistantRunOwnerIsolation(t *testing.T) {
	resetIntegrationState(t)
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()

	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/conversations",
		"owner-run", map[string]any{
			"summary": "run 隔离", "clientRequestId": "run-owner-isolation-conversation",
		})
	var conversation assistant.AssistantConversation
	if err := json.Unmarshal(create.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}
	start := assistantAPIRequest(t, handler, http.MethodPost,
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		"owner-run", map[string]any{
			"input": map[string]any{"text": "隔离测试"}, "clientRequestId": "run-owner-isolation",
		})
	var run assistant.AssistantTurn
	if err := json.Unmarshal(start.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v", err)
	}

	foreign := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/runs/"+run.TurnID, "intruder", nil)
	if foreign.Code != http.StatusNotFound {
		t.Fatalf("foreign run read must be not_found: status=%d", foreign.Code)
	}
	anonymous := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/runs/"+run.TurnID, "", nil)
	if anonymous.Code != http.StatusUnauthorized {
		t.Fatalf("anonymous run read must be 401: status=%d", anonymous.Code)
	}
}

// TestAssistantRunStreamResumeSemantics 验证 SSE：首跑落终态；
// 重启后重放 SSE 返回持久化终态事件而非 404。
func TestAssistantRunStreamResumeSemantics(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()

	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/conversations",
		"user-sse", map[string]any{
			"summary": "SSE 会话", "clientRequestId": "stream-resume-conversation",
		})
	var conversation assistant.AssistantConversation
	if err := json.Unmarshal(create.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}
	start := assistantAPIRequest(t, handler, http.MethodPost,
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		"user-sse", map[string]any{
			"input": map[string]any{"text": "今天上海天气怎么样"}, "clientRequestId": "stream-resume-run",
		})
	var run assistant.AssistantTurn
	if err := json.Unmarshal(start.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v", err)
	}

	stream := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/runs/"+run.TurnID+"/events", "user-sse", nil)
	if stream.Code != http.StatusOK || !strings.Contains(stream.Body.String(), "event:") {
		t.Fatalf("first stream status=%d body=%s", stream.Code, stream.Body.String())
	}
	initialEvents := parseAssistantSSEEventFrames(t, stream.Body.String())
	var stored assistant.AssistantTurn
	if err := integrationMongoDB.Collection("assistant_runs").
		FindOne(ctx, bson.M{"_id": run.TurnID}).Decode(&stored); err != nil {
		t.Fatalf("load stored run: %v", err)
	}
	if stored.Status == "running" || stored.StreamState.ResumeToken == "" {
		t.Fatalf("run must reach terminal state with resume token: %+v", stored.StreamState)
	}

	restarted := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()
	resume := assistantAPIRequest(t, restarted, http.MethodGet, "/assistant/runs/"+run.TurnID+"/events", "user-sse", nil)
	if resume.Code != http.StatusOK {
		t.Fatalf("resume after restart status=%d", resume.Code)
	}
	if !strings.Contains(resume.Body.String(), stored.StreamState.ResumeToken) &&
		!strings.Contains(resume.Body.String(), run.TurnID) {
		t.Fatalf("terminal replay must include its persisted identity: body=%s", resume.Body.String())
	}

	// 使用服务端签发的首个 event id 重新建连。该请求必须只返回严格更大的
	// 序号，证明 Mongo event journal、HTTP Last-Event-ID 和单次 run 的
	// SSE transport 共同满足断点续传语义。
	resumeRequest := httptest.NewRequest(
		http.MethodGet,
		"/assistant/runs/"+run.TurnID+"/events",
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
	var storedFailure *assistant.AssistantRunTerminalFailure
	if stored.TerminalSnapshot == nil {
		t.Fatalf("terminal run is missing durable terminalSnapshot: %#v", stored)
	}
	storedAnswerText = stored.TerminalSnapshot.AnswerText
	storedFailure = stored.TerminalSnapshot.Failure
	if stored.Status == "completed" && strings.TrimSpace(storedAnswerText) == "" {
		t.Fatalf("completed run is missing durable answer text: %#v", stored)
	}
	if stored.Status == "failed" && storedFailure == nil {
		t.Fatalf("failed run is missing durable canonical failure: %#v", stored)
	}
	if _, err := integrationMongoDB.Collection("assistant_run_events").DeleteMany(
		ctx,
		bson.M{"runId": run.TurnID},
	); err != nil {
		t.Fatalf("simulate run event journal expiry: %v", err)
	}
	getAfterExpiry := assistantAPIRequest(
		t,
		restarted,
		http.MethodGet,
		"/assistant/runs/"+run.TurnID,
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
	assertAssistantTurnEnvelopePublicKeys(t, terminalResponse)
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
	if terminalResponse["status"] != stored.Status {
		t.Fatalf(
			"terminal status after journal expiry=%q want=%q",
			terminalResponse["status"],
			stored.Status,
		)
	}
	if storedFailure != nil && terminalSnapshot["failure"] == nil {
		t.Fatalf(
			"terminal failure after journal expiry is absent: %#v",
			terminalResponse,
		)
	}

	streamAfterExpiry := assistantAPIRequest(
		t,
		restarted,
		http.MethodGet,
		"/assistant/runs/"+run.TurnID+"/events",
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
		"conversationId": true,
		"turnId":         true,
		"status":         true,
		"resumeToken":    true,
		"processes":      true,
		"finalAnswer":    true,
	})
	if terminalReplay.eventType != stored.Status {
		t.Fatalf(
			"terminal replay after journal expiry=%#v want status=%q",
			terminalReplay,
			stored.Status,
		)
	}
	if stored.Status == "completed" &&
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
		"/assistant/conversations/"+conversation.ConversationID+"/turns",
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
	var historyView assistant.AssistantTurnListView
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
		"/assistant/runs/" + run.TurnID,
		"/assistant/runs/" + run.TurnID + "/events",
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
// scorecard 落 assistant_scorecard_facts 且 scoreId dedupe。
func TestAssistantRunWritesScorecardOnCompletion(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	service := newIntegrationAssistantService()
	handler := assistanthttp.NewHandler(service).Routes()

	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/conversations",
		"user-score", map[string]any{
			"summary": "评分会话", "clientRequestId": "scorecard-conversation",
		})
	var conversation assistant.AssistantConversation
	if err := json.Unmarshal(create.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}
	start := assistantAPIRequest(t, handler, http.MethodPost,
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		"user-score", map[string]any{
			"input": map[string]any{"text": "给我一句鼓励"}, "clientRequestId": "scorecard-run",
		})
	var run assistant.AssistantTurn
	if err := json.Unmarshal(start.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v", err)
	}
	stream := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/runs/"+run.TurnID+"/events", "user-score", nil)
	if stream.Code != http.StatusOK {
		t.Fatalf("stream status=%d", stream.Code)
	}
	awaitAssistantRunScorecard(t, ctx, run.TurnID)

	// 重复完成（终态重放）不产生第二条 scorecard。
	replayStream := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/runs/"+run.TurnID+"/events", "user-score", nil)
	if replayStream.Code != http.StatusOK {
		t.Fatalf("replay stream status=%d", replayStream.Code)
	}
	count, err := integrationMongoDB.Collection("assistant_scorecard_facts").
		CountDocuments(ctx, bson.M{"_id": "run:" + run.TurnID})
	if err != nil || count != 1 {
		t.Fatalf("scorecard must dedupe on replay: count=%d err=%v", count, err)
	}
}

// TestSkillSubscriptionCreateIdempotent 验证订阅一次创建的唯一约束幂等。
func TestSkillSubscriptionCreateIdempotent(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()

	body := map[string]any{
		"skillId":         "news_briefing",
		"trigger":         map[string]any{"type": "cron", "cron": "30 8 * * *"},
		"clientRequestId": "sub-req-1",
	}
	first := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/skill-subscriptions", "user-sub-1", body)
	if first.Code != http.StatusCreated && first.Code != http.StatusOK {
		t.Fatalf("create subscription status=%d body=%s", first.Code, first.Body.String())
	}
	var created assistant.SkillSubscription
	if err := json.Unmarshal(first.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode subscription: %v", err)
	}
	replay := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/skill-subscriptions", "user-sub-1", body)
	var replayed assistant.SkillSubscription
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
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()

	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/skill-subscriptions",
		"user-sub-cas", map[string]any{
			"skillId": "stock_sentinel",
			"trigger": map[string]any{"type": "cron", "cron": "0 9 * * *"},
		})
	var created assistant.SkillSubscription
	if err := json.Unmarshal(create.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode subscription: %v", err)
	}
	statusPath := "/assistant/skill-subscriptions/" + created.SubscriptionID + "/status"
	paused := assistantAPIRequest(t, handler, http.MethodPatch, statusPath, "user-sub-cas",
		map[string]any{"status": "paused"})
	var pausedSub assistant.SkillSubscription
	if err := json.Unmarshal(paused.Body.Bytes(), &pausedSub); err != nil {
		t.Fatalf("decode paused: %v", err)
	}
	if pausedSub.Status != "paused" {
		t.Fatalf("status transition failed: %+v", pausedSub)
	}
	noop := assistantAPIRequest(t, handler, http.MethodPatch, statusPath, "user-sub-cas",
		map[string]any{"status": "paused"})
	var noopSub assistant.SkillSubscription
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
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()

	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/skill-subscriptions",
		"owner-sub", map[string]any{
			"skillId": "daily_assistant",
			"trigger": map[string]any{"type": "cron", "cron": "0 8 * * *"},
		})
	var created assistant.SkillSubscription
	if err := json.Unmarshal(create.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode subscription: %v", err)
	}
	foreign := assistantAPIRequest(t, handler, http.MethodGet,
		"/assistant/skill-subscriptions/"+created.SubscriptionID, "intruder", nil)
	if foreign.Code == http.StatusOK {
		t.Fatalf("foreign subscription read must fail: status=%d", foreign.Code)
	}
}

// TestSkillConsentGrantVersionedFact 验证 consent 版本化流水：
// 重复授权幂等；grant→revoke→grant 保留全部历史行且最多一条 active。
func TestSkillConsentGrantVersionedFact(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	service := newIntegrationAssistantService()

	first, err := service.GrantSkillConsent(ctx, "consent-user", "personal_content_access", "personal_content_access")
	if err != nil {
		t.Fatalf("grant consent: %v", err)
	}
	replayed, err := service.GrantSkillConsent(ctx, "consent-user", "personal_content_access", "personal_content_access")
	if err != nil {
		t.Fatalf("replay grant: %v", err)
	}
	if replayed.ID != first.ID || !replayed.GrantedAt.Equal(first.GrantedAt) {
		t.Fatalf("duplicate grant must return existing active fact: first=%+v replay=%+v", first, replayed)
	}
	if err := service.RevokeSkillConsent(ctx, "consent-user", "personal_content_access"); err != nil {
		t.Fatalf("revoke consent: %v", err)
	}
	second, err := service.GrantSkillConsent(ctx, "consent-user", "personal_content_access", "personal_content_access")
	if err != nil {
		t.Fatalf("re-grant consent: %v", err)
	}
	if second.ID == first.ID {
		t.Fatalf("re-grant after revoke must create a new versioned fact: %+v", second)
	}
	var total, active int
	if err := integrationPostgresPool.QueryRow(ctx,
		`SELECT COUNT(*), COUNT(*) FILTER (WHERE revoked_at IS NULL) FROM skill_consents WHERE user_id=$1 AND skill_id=$2`,
		"consent-user", "personal_content_access").Scan(&total, &active); err != nil {
		t.Fatalf("count consent facts: %v", err)
	}
	if total != 2 || active != 1 {
		t.Fatalf("versioned audit trail mismatch: total=%d active=%d", total, active)
	}
}

// TestSkillConsentRevokeImmediateEnforcement 验证撤权后敏感技能执行点立即拒绝。
func TestSkillConsentRevokeImmediateEnforcement(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	service := newIntegrationAssistantService()
	handler := assistanthttp.NewHandler(service).Routes()

	if _, err := service.GrantSkillConsent(ctx, "enforce-user", "personal_content_access", "personal_content_access"); err != nil {
		t.Fatalf("grant consent: %v", err)
	}
	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/conversations",
		"enforce-user", map[string]any{
			"summary": "consent gate", "clientRequestId": "consent-gate-conversation",
		})
	var conversation assistant.AssistantConversation
	if err := json.Unmarshal(create.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}
	start := assistantAPIRequest(t, handler, http.MethodPost,
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		"enforce-user", map[string]any{
			"skillId":         "personal_content_access",
			"input":           map[string]any{"text": "看看我的个人内容"},
			"clientRequestId": "consent-gate-run",
		})
	var run assistant.AssistantTurn
	if err := json.Unmarshal(start.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v", err)
	}
	granted := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/runs/"+run.TurnID+"/events", "enforce-user", nil)
	if granted.Code != http.StatusOK {
		t.Fatalf("granted stream status=%d", granted.Code)
	}

	if err := service.RevokeSkillConsent(ctx, "enforce-user", "personal_content_access"); err != nil {
		t.Fatalf("revoke consent: %v", err)
	}
	// 撤权后创建点即拒绝（403 + skill_consent_required）。
	startDenied := assistantAPIRequest(t, handler, http.MethodPost,
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		"enforce-user", map[string]any{
			"skillId":         "personal_content_access",
			"input":           map[string]any{"text": "再看一次"},
			"clientRequestId": "consent-gate-run-revoked",
		})
	if startDenied.Code != http.StatusForbidden ||
		!strings.Contains(startDenied.Body.String(), "skill_consent_required") {
		t.Fatalf("revoked consent must deny run creation: status=%d body=%s",
			startDenied.Code, startDenied.Body.String())
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
) application.NotificationAppMessageCommandWriter {
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
) application.AssistantDeliveryPolicyReader {
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
	client, err := application.NewUserDeliveryPolicyClient(
		server.URL,
		integrationServiceCredentials("integration-user-policy-token"),
		server.Client(),
	)
	if err != nil {
		t.Fatalf("create user delivery policy integration client: %v", err)
	}
	return client
}

// TestSkillSubscriptionCronLeaseNoDuplicate 验证同一 tick 窗口的 Redis 租约：
// 两次 tick 并发（同窗口）只投递一次；lease key 带 TTL。
func TestSkillSubscriptionCronLeaseNoDuplicate(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	service := newIntegrationAssistantService(
		application.WithNotificationAppMessageCommandWriter(
			integrationNotificationCommandWriter(t),
		),
		application.WithAssistantDeliveryPolicyReader(
			integrationDeliveryPolicyReader(t),
		),
		application.WithAgentLoop(application.NewAgentLoop(
			integrationChatMentionSkillRuntime{},
			application.ReactRuntime{
				Model: application.DeterministicModelProvider{},
			},
			nil,
		)),
	)
	handler := assistanthttp.NewHandler(service).Routes()

	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/skill-subscriptions",
		"lease-user", map[string]any{
			"skillId": "news_briefing",
			"trigger": map[string]any{"type": "cron", "cron": "30 8 * * *"},
		})
	if create.Code != http.StatusCreated && create.Code != http.StatusOK {
		t.Fatalf("create subscription status=%d body=%s", create.Code, create.Body.String())
	}
	var created assistant.SkillSubscription
	if err := json.Unmarshal(create.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode lease subscription: %v", err)
	}
	if created.DeliveryState.NextAttemptAt == nil {
		t.Fatalf("created subscription has no nextAttemptAt: %+v", created)
	}
	tickAt := created.DeliveryState.NextAttemptAt.UTC().Format(time.RFC3339)
	first, err := service.TickSkillSubscriptionCron(
		ctx,
		assistant.SkillSubscriptionCronTickInput{Now: tickAt},
	)
	if err != nil {
		t.Fatalf("first tick: %v", err)
	}
	if first.ProcessedCount != 1 {
		t.Fatalf("first tick must process one subscription: %+v", first)
	}
	second, err := service.TickSkillSubscriptionCron(
		ctx,
		assistant.SkillSubscriptionCronTickInput{Now: tickAt},
	)
	if err != nil {
		t.Fatalf("second tick: %v", err)
	}
	if second.ProcessedCount != 0 {
		t.Fatalf("same-window tick must be deduplicated by redis lease: %+v", second)
	}
}

// TestAssistantConversationLifecycleQueryAndCancel 验证会话生命周期查询面与
// 取消命令在真实 Mongo 上的行为：List 分页、终态过滤、cancel CAS 与幂等、
// 新 handler 实例（模拟重启）仍可读取 cancelled 终态。
func TestAssistantConversationLifecycleQueryAndCancel(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()
	userID := "user-lifecycle-1"

	// 造 3 个会话
	conversationIDs := []string{}
	for _, requestID := range []string{"lc-conv-1", "lc-conv-2", "lc-conv-3"} {
		created := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/conversations", userID,
			map[string]any{"summary": "生命周期验证", "clientRequestId": requestID})
		if created.Code != http.StatusCreated {
			t.Fatalf("create conversation status=%d body=%s", created.Code, created.Body.String())
		}
		var conversation assistant.AssistantConversation
		if err := json.Unmarshal(created.Body.Bytes(), &conversation); err != nil {
			t.Fatalf("decode conversation: %v", err)
		}
		conversationIDs = append(conversationIDs, conversation.ConversationID)
	}

	// List 分页：limit=2 → 第一页 2 条 + cursor；第二页 1 条无 cursor
	page1Resp := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/conversations?limit=2", userID, nil)
	if page1Resp.Code != http.StatusOK {
		t.Fatalf("list conversations status=%d body=%s", page1Resp.Code, page1Resp.Body.String())
	}
	var page1 assistant.AssistantConversationListView
	if err := json.Unmarshal(page1Resp.Body.Bytes(), &page1); err != nil {
		t.Fatalf("decode conversations page1: %v", err)
	}
	if len(page1.Items) != 2 || page1.NextCursor == "" {
		t.Fatalf("page1 must have 2 items + cursor, got %d items cursor=%q", len(page1.Items), page1.NextCursor)
	}
	page2Resp := assistantAPIRequest(t, handler, http.MethodGet,
		"/assistant/conversations?limit=2&cursor="+page1.NextCursor, userID, nil)
	var page2 assistant.AssistantConversationListView
	if err := json.Unmarshal(page2Resp.Body.Bytes(), &page2); err != nil {
		t.Fatalf("decode conversations page2: %v", err)
	}
	if len(page2.Items) != 1 || page2.NextCursor != "" {
		t.Fatalf("page2 must be terminal single item, got %d items cursor=%q", len(page2.Items), page2.NextCursor)
	}

	// 其他用户看不到
	otherResp := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/conversations", "user-other", nil)
	var otherPage assistant.AssistantConversationListView
	if err := json.Unmarshal(otherResp.Body.Bytes(), &otherPage); err != nil {
		t.Fatalf("decode other user page: %v", err)
	}
	if len(otherPage.Items) != 0 {
		t.Fatalf("owner isolation violated: %#v", otherPage.Items)
	}

	// 启动 run 并取消：running → cancelled（deterministic provider 下 run 由
	// SSE 消费驱动，这里直接对 running turn 发 cancel 命令验证 CAS）
	target := conversationIDs[0]
	startResp := assistantAPIRequest(t, handler, http.MethodPost,
		"/assistant/conversations/"+target+"/runs", userID,
		map[string]any{
			"input":           map[string]any{"text": "帮我查一下天气"},
			"clientRequestId": "lc-run-1",
		})
	if startResp.Code != http.StatusCreated {
		t.Fatalf("start run status=%d body=%s", startResp.Code, startResp.Body.String())
	}
	var startedTurn assistant.AssistantTurn
	if err := json.Unmarshal(startResp.Body.Bytes(), &startedTurn); err != nil {
		t.Fatalf("decode started turn: %v", err)
	}
	if startedTurn.Status != "running" {
		t.Fatalf("started turn must be running, got %s", startedTurn.Status)
	}

	cancelResp := assistantAPIRequest(t, handler, http.MethodPost,
		"/assistant/runs/"+startedTurn.TurnID+"/cancel", userID, nil)
	if cancelResp.Code != http.StatusOK {
		t.Fatalf("cancel run status=%d body=%s", cancelResp.Code, cancelResp.Body.String())
	}
	var cancelledTurn assistant.AssistantTurn
	if err := json.Unmarshal(cancelResp.Body.Bytes(), &cancelledTurn); err != nil {
		t.Fatalf("decode cancelled turn: %v", err)
	}
	if cancelledTurn.Status != "cancelled" ||
		cancelledTurn.CompletedAt == nil ||
		cancelledTurn.TerminalSnapshot == nil {
		t.Fatalf("cancel must transition to cancelled terminal, got %#v", cancelledTurn)
	}

	// 幂等：重复 cancel 返回 cancelled 200
	cancelAgain := assistantAPIRequest(t, handler, http.MethodPost,
		"/assistant/runs/"+startedTurn.TurnID+"/cancel", userID, nil)
	if cancelAgain.Code != http.StatusOK {
		t.Fatalf("repeated cancel status=%d body=%s", cancelAgain.Code, cancelAgain.Body.String())
	}
	var replayedCancellation assistant.AssistantTurn
	if err := json.Unmarshal(cancelAgain.Body.Bytes(), &replayedCancellation); err != nil {
		t.Fatalf("decode repeated cancellation: %v", err)
	}
	if replayedCancellation.CompletedAt == nil ||
		!replayedCancellation.CompletedAt.Equal(*cancelledTurn.CompletedAt) ||
		replayedCancellation.TerminalSnapshot == nil {
		t.Fatalf(
			"repeated cancel must preserve first terminal snapshot and timestamp: %#v",
			replayedCancellation,
		)
	}

	// Mongo 落盘核验 + 新 handler（模拟重启）读取终态与轮次列表
	var storedStatus struct {
		Status           string                                  `bson:"status"`
		CompletedAt      *time.Time                              `bson:"completedAt"`
		TerminalSnapshot *assistant.AssistantRunTerminalSnapshot `bson:"terminalSnapshot"`
	}
	if err := integrationMongoDB.Collection("assistant_runs").
		FindOne(ctx, bson.M{"_id": startedTurn.TurnID}).Decode(&storedStatus); err != nil {
		t.Fatalf("read cancelled run from mongo: %v", err)
	}
	if storedStatus.Status != "cancelled" ||
		storedStatus.CompletedAt == nil ||
		storedStatus.TerminalSnapshot == nil {
		t.Fatalf("mongo run must retain cancelled terminal snapshot: %#v", storedStatus)
	}

	restartedHandler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()
	turnsResp := assistantAPIRequest(t, restartedHandler, http.MethodGet,
		"/assistant/conversations/"+target+"/turns", userID, nil)
	if turnsResp.Code != http.StatusOK {
		t.Fatalf("list turns status=%d body=%s", turnsResp.Code, turnsResp.Body.String())
	}
	var turnsView assistant.AssistantTurnListView
	if err := json.Unmarshal(turnsResp.Body.Bytes(), &turnsView); err != nil {
		t.Fatalf("decode turns view: %v", err)
	}
	if len(turnsView.Items) != 1 || turnsView.Items[0].Status != "cancelled" ||
		turnsView.Items[0].InputText != "帮我查一下天气" ||
		turnsView.Items[0].TerminalSnapshot == nil {
		t.Fatalf("turns view must expose cancelled turn summary after restart, got %#v", turnsView.Items)
	}

	cancelledStream := assistantAPIRequest(t, restartedHandler, http.MethodGet,
		"/assistant/runs/"+startedTurn.TurnID+"/events", userID, nil)
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
		"/assistant/conversations/"+target+"/turns", "user-other", nil)
	if foreignTurns.Code != http.StatusNotFound {
		t.Fatalf("non-owner turns must 404, got %d body=%s", foreignTurns.Code, foreignTurns.Body.String())
	}
}
