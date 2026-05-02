package http

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
)

func TestHandleReportInteractionEvent_BatchWrapperAndHeaders(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
	)
	handler := NewHandler(service).Routes()

	body := map[string]any{
		"events": []map[string]any{
			{
				"eventId":  "evt_1",
				"runId":    "run_1",
				"pageType": "assistant_dialog",
			},
		},
	}
	payload, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/v1/assistant/learning/events", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "user_1")
	req.Header.Set("X-Client-Session-Id", "session_1")
	req.Header.Set("X-Trace-Id", "trace_1")
	req.Header.Set("X-Client-Page-Id", "assistant.reportInteractionEvent")
	req.Header.Set("X-Client-Surface-Id", "assistant_dialog")
	req.Header.Set("X-Client-Route-Id", "assistant-dialog-route")
	req.Header.Set("X-Client-Operation-Id", "ReportInteractionEvent")
	req.Header.Set("X-Client-Experiment-Bucket", "control")
	req.Header.Set("X-Client-Sent-At", "2026-04-01T10:00:00Z")
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response error: %v", err)
	}
	if resp["resource"] != "interaction_event_batch" {
		t.Fatalf("resource=%v, want interaction_event_batch", resp["resource"])
	}
	items, err := service.ListAssistantMemories(context.Background(), "user_1", 10)
	if err != nil {
		t.Fatalf("ListAssistantMemories error: %v", err)
	}
	if len(items.Items) != 1 {
		t.Fatalf("memories=%d, want 1", len(items.Items))
	}
}

func TestHandleReportScorecard_BatchWrapper(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
	)
	handler := NewHandler(service).Routes()

	body := map[string]any{
		"scorecards": []map[string]any{
			{
				"scoreId":     "score_1",
				"eventId":     "evt_1",
				"userId":      "user_1",
				"metricId":    "answer_relevance",
				"scoreValue":  4.2,
				"scoreSource": "implicit",
			},
		},
	}
	payload, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/v1/assistant/learning/scorecards", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response error: %v", err)
	}
	if resp["resource"] != "scorecard_batch" {
		t.Fatalf("resource=%v, want scorecard_batch", resp["resource"])
	}
	if resp["acceptedCount"] != float64(1) {
		t.Fatalf("acceptedCount=%v, want 1", resp["acceptedCount"])
	}
}

func TestHandleGetLearningOpsSummary(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
	)
	_, err := service.ReportInteractionEvents(context.Background(), []assistant.InteractionEvent{{
		EventID:       "evt_ops_http_1",
		RunID:         "run_ops_http_1",
		UserID:        "user_http_1",
		SessionID:     "session_http_1",
		PageType:      "assistant_dialog",
		DomainID:      "assistant",
		ExplicitThumb: "down",
	}})
	if err != nil {
		t.Fatalf("ReportInteractionEvents error: %v", err)
	}
	handler := NewHandler(service).Routes()
	req := httptest.NewRequest(http.MethodGet, "/v1/assistant/ops/learning-summary", nil)
	req.Header.Set("X-Client-User-Id", "user_http_1")
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response error: %v", err)
	}
	if resp["userId"] != "user_http_1" {
		t.Fatalf("userId=%v", resp["userId"])
	}
}

func TestHandleAppMessageLifecycle(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		application.WithAppMessageStore(persistence.NewMemoryAppMessageStore()),
	)
	handler := NewHandler(service).Routes()
	payload, _ := json.Marshal(map[string]any{
		"messageType": "assistant",
		"source":      "assistant_turn",
		"sourceId":    "atn_http_1",
		"title":       "小趣提醒",
		"summary":     "你关注的主题有新进展。",
		"target": map[string]any{
			"targetType": "assistant_turn",
			"targetId":   "atn_http_1",
		},
	})
	createReq := httptest.NewRequest(http.MethodPost, "/v1/app-messages", bytes.NewReader(payload))
	createReq.Header.Set("Content-Type", "application/json")
	createReq.Header.Set("X-Client-User-Id", "user_msg_1")
	createResp := httptest.NewRecorder()
	handler.ServeHTTP(createResp, createReq)
	if createResp.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", createResp.Code, createResp.Body.String())
	}
	var created map[string]any
	if err := json.Unmarshal(createResp.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode create response: %v", err)
	}
	messageID, _ := created["messageId"].(string)
	if messageID == "" {
		t.Fatal("messageId should be returned")
	}

	listReq := httptest.NewRequest(http.MethodGet, "/v1/app-messages", nil)
	listReq.Header.Set("X-Client-User-Id", "user_msg_1")
	listResp := httptest.NewRecorder()
	handler.ServeHTTP(listResp, listReq)
	if listResp.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", listResp.Code, listResp.Body.String())
	}
	var list map[string][]map[string]any
	if err := json.Unmarshal(listResp.Body.Bytes(), &list); err != nil {
		t.Fatalf("decode list response: %v", err)
	}
	if len(list["items"]) != 1 {
		t.Fatalf("items=%d, want 1", len(list["items"]))
	}

	ackReq := httptest.NewRequest(http.MethodPost, "/v1/app-messages/"+messageID+"/ack", nil)
	ackReq.Header.Set("X-Client-User-Id", "user_msg_1")
	ackResp := httptest.NewRecorder()
	handler.ServeHTTP(ackResp, ackReq)
	if ackResp.Code != http.StatusOK {
		t.Fatalf("ack status=%d body=%s", ackResp.Code, ackResp.Body.String())
	}

	readReq := httptest.NewRequest(http.MethodPost, "/v1/app-messages/"+messageID+"/read", nil)
	readReq.Header.Set("X-Client-User-Id", "user_msg_1")
	readResp := httptest.NewRecorder()
	handler.ServeHTTP(readResp, readReq)
	if readResp.Code != http.StatusOK {
		t.Fatalf("read status=%d body=%s", readResp.Code, readResp.Body.String())
	}

	countReq := httptest.NewRequest(http.MethodGet, "/v1/app-messages/unread-count", nil)
	countReq.Header.Set("X-Client-User-Id", "user_msg_1")
	countResp := httptest.NewRecorder()
	handler.ServeHTTP(countResp, countReq)
	if countResp.Code != http.StatusOK {
		t.Fatalf("count status=%d body=%s", countResp.Code, countResp.Body.String())
	}
	var count map[string]float64
	if err := json.Unmarshal(countResp.Body.Bytes(), &count); err != nil {
		t.Fatalf("decode count response: %v", err)
	}
	if count["unreadCount"] != 0 {
		t.Fatalf("unreadCount=%v, want 0", count["unreadCount"])
	}
}

func TestHandleAppMessageStream(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		application.WithAppMessageStore(persistence.NewMemoryAppMessageStore()),
	)
	handler := NewHandler(service).Routes()
	payload, _ := json.Marshal(map[string]any{
		"messageType": "assistant",
		"source":      "assistant_turn",
		"sourceId":    "atn_stream_1",
		"title":       "小趣提醒",
		"summary":     "stream smoke",
		"target": map[string]any{
			"targetType": "assistant_turn",
			"targetId":   "atn_stream_1",
		},
	})
	createReq := httptest.NewRequest(http.MethodPost, "/v1/app-messages", bytes.NewReader(payload))
	createReq.Header.Set("Content-Type", "application/json")
	createReq.Header.Set("X-Client-User-Id", "user_stream_1")
	handler.ServeHTTP(httptest.NewRecorder(), createReq)

	streamReq := httptest.NewRequest(http.MethodGet, "/v1/app-messages/stream", nil)
	streamReq.Header.Set("X-Client-User-Id", "user_stream_1")
	streamResp := httptest.NewRecorder()
	handler.ServeHTTP(streamResp, streamReq)
	if streamResp.Code != http.StatusOK {
		t.Fatalf("stream status=%d body=%s", streamResp.Code, streamResp.Body.String())
	}
	body := streamResp.Body.String()
	if !bytes.Contains([]byte(body), []byte("event: app_message.stream.ready")) {
		t.Fatalf("stream missing ready event: %s", body)
	}
	if !bytes.Contains([]byte(body), []byte(`"seq":1`)) || !bytes.Contains([]byte(body), []byte(`"seq":2`)) {
		t.Fatalf("stream missing seq envelope: %s", body)
	}
}

func TestHandleSkillSubscriptionLifecycleAndCronTick(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		application.WithSkillSubscriptionStore(persistence.NewMemorySkillSubscriptionStore()),
		application.WithAppMessageStore(persistence.NewMemoryAppMessageStore()),
	)
	handler := NewHandler(service).Routes()

	payload, _ := json.Marshal(map[string]any{
		"skillId":  "news_briefing",
		"domainId": "content",
		"searchQueryPlan": map[string]any{
			"rawText": "每天早上 8 点给我科技新闻摘要",
			"queries": []string{"科技新闻"},
		},
		"trigger": map[string]any{
			"type": "cron",
			"cron": "0 8 * * *",
		},
	})
	createReq := httptest.NewRequest(http.MethodPost, "/v1/assistant/skill-subscriptions", bytes.NewReader(payload))
	createReq.Header.Set("Content-Type", "application/json")
	createReq.Header.Set("X-Client-User-Id", "user_sub_1")
	createResp := httptest.NewRecorder()
	handler.ServeHTTP(createResp, createReq)
	if createResp.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", createResp.Code, createResp.Body.String())
	}
	var created map[string]any
	if err := json.Unmarshal(createResp.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode create response: %v", err)
	}
	subscriptionID, _ := created["subscriptionId"].(string)
	if subscriptionID == "" {
		t.Fatal("subscriptionId should be returned")
	}

	statusPayload, _ := json.Marshal(map[string]any{"status": "paused"})
	statusReq := httptest.NewRequest(http.MethodPatch, "/v1/assistant/skill-subscriptions/"+subscriptionID+"/status", bytes.NewReader(statusPayload))
	statusReq.Header.Set("Content-Type", "application/json")
	statusReq.Header.Set("X-Client-User-Id", "user_sub_1")
	statusResp := httptest.NewRecorder()
	handler.ServeHTTP(statusResp, statusReq)
	if statusResp.Code != http.StatusOK {
		t.Fatalf("status update=%d body=%s", statusResp.Code, statusResp.Body.String())
	}

	resumePayload, _ := json.Marshal(map[string]any{"status": "active"})
	resumeReq := httptest.NewRequest(http.MethodPatch, "/v1/assistant/skill-subscriptions/"+subscriptionID+"/status", bytes.NewReader(resumePayload))
	resumeReq.Header.Set("Content-Type", "application/json")
	resumeReq.Header.Set("X-Client-User-Id", "user_sub_1")
	handler.ServeHTTP(httptest.NewRecorder(), resumeReq)

	tickPayload, _ := json.Marshal(map[string]any{"now": "2026-04-29T08:00:00Z"})
	tickReq := httptest.NewRequest(http.MethodPost, "/v1/assistant/skill-subscriptions/cron/tick", bytes.NewReader(tickPayload))
	tickReq.Header.Set("Content-Type", "application/json")
	tickReq.Header.Set("X-Client-User-Id", "user_sub_1")
	tickResp := httptest.NewRecorder()
	handler.ServeHTTP(tickResp, tickReq)
	if tickResp.Code != http.StatusOK {
		t.Fatalf("tick status=%d body=%s", tickResp.Code, tickResp.Body.String())
	}
	var tick map[string]any
	if err := json.Unmarshal(tickResp.Body.Bytes(), &tick); err != nil {
		t.Fatalf("decode tick response: %v", err)
	}
	if tick["processedCount"] != float64(1) {
		t.Fatalf("processedCount=%v, want 1", tick["processedCount"])
	}
}

func TestHandleConversationTurnStream(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
	)
	handler := NewHandler(service).Routes()

	conversationPayload, _ := json.Marshal(map[string]any{"summary": "M4 smoke"})
	conversationReq := httptest.NewRequest(http.MethodPost, "/v1/assistant/conversations", bytes.NewReader(conversationPayload))
	conversationReq.Header.Set("Content-Type", "application/json")
	conversationReq.Header.Set("X-Client-User-Id", "user_m4_1")
	conversationResp := httptest.NewRecorder()
	handler.ServeHTTP(conversationResp, conversationReq)
	if conversationResp.Code != http.StatusCreated {
		t.Fatalf("conversation status=%d body=%s", conversationResp.Code, conversationResp.Body.String())
	}
	var conversation map[string]any
	if err := json.Unmarshal(conversationResp.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}
	conversationID, _ := conversation["conversationId"].(string)
	if conversationID == "" || !bytes.HasPrefix([]byte(conversationID), []byte("acv_")) {
		t.Fatalf("conversationId=%q", conversationID)
	}

	turnPayload, _ := json.Marshal(map[string]any{
		"input": map[string]any{"text": "今天帮我整理日程"},
	})
	turnReq := httptest.NewRequest(http.MethodPost, "/v1/assistant/conversations/"+conversationID+"/turns", bytes.NewReader(turnPayload))
	turnReq.Header.Set("Content-Type", "application/json")
	turnReq.Header.Set("X-Client-User-Id", "user_m4_1")
	turnResp := httptest.NewRecorder()
	handler.ServeHTTP(turnResp, turnReq)
	if turnResp.Code != http.StatusCreated {
		t.Fatalf("turn status=%d body=%s", turnResp.Code, turnResp.Body.String())
	}
	var turn map[string]any
	if err := json.Unmarshal(turnResp.Body.Bytes(), &turn); err != nil {
		t.Fatalf("decode turn: %v", err)
	}
	turnID, _ := turn["turnId"].(string)
	if turnID == "" || !bytes.HasPrefix([]byte(turnID), []byte("atn_")) {
		t.Fatalf("turnId=%q", turnID)
	}

	streamReq := httptest.NewRequest(http.MethodPost, "/v1/assistant/turns/"+turnID+"/stream", nil)
	streamReq.Header.Set("X-Client-User-Id", "user_m4_1")
	streamResp := httptest.NewRecorder()
	handler.ServeHTTP(streamResp, streamReq)
	if streamResp.Code != http.StatusOK {
		t.Fatalf("turn stream status=%d body=%s", streamResp.Code, streamResp.Body.String())
	}
	body := streamResp.Body.String()
	if !bytes.Contains([]byte(body), []byte("event: assistant.turn.started")) {
		t.Fatalf("stream missing turn started: %s", body)
	}
	if !bytes.Contains([]byte(body), []byte("event: assistant.answer.final")) {
		t.Fatalf("stream missing final answer: %s", body)
	}
	if !bytes.Contains([]byte(body), []byte(`"seq":4`)) {
		t.Fatalf("stream missing monotonically increasing seq: %s", body)
	}
	if !bytes.Contains([]byte(body), []byte(`"conversationId":"`+conversationID+`"`)) {
		t.Fatalf("stream missing conversationId linkage: %s", body)
	}
}

func TestHandleTurnStream_M5AgentLoopEndToEnd(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
	)
	handler := NewHandler(service).Routes()

	conversationPayload, _ := json.Marshal(map[string]any{"summary": "M5 e2e"})
	conversationReq := httptest.NewRequest(http.MethodPost, "/v1/assistant/conversations", bytes.NewReader(conversationPayload))
	conversationReq.Header.Set("Content-Type", "application/json")
	conversationReq.Header.Set("X-Client-User-Id", "user_m5_http")
	conversationResp := httptest.NewRecorder()
	handler.ServeHTTP(conversationResp, conversationReq)
	if conversationResp.Code != http.StatusCreated {
		t.Fatalf("conversation status=%d body=%s", conversationResp.Code, conversationResp.Body.String())
	}
	var conversation map[string]any
	if err := json.Unmarshal(conversationResp.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}
	conversationID, _ := conversation["conversationId"].(string)

	turnPayload, _ := json.Marshal(map[string]any{
		"input": map[string]any{"text": "帮我总结今天的安排"},
	})
	turnReq := httptest.NewRequest(http.MethodPost, "/v1/assistant/conversations/"+conversationID+"/turns", bytes.NewReader(turnPayload))
	turnReq.Header.Set("Content-Type", "application/json")
	turnReq.Header.Set("X-Client-User-Id", "user_m5_http")
	turnResp := httptest.NewRecorder()
	handler.ServeHTTP(turnResp, turnReq)
	if turnResp.Code != http.StatusCreated {
		t.Fatalf("turn status=%d body=%s", turnResp.Code, turnResp.Body.String())
	}
	var turn map[string]any
	if err := json.Unmarshal(turnResp.Body.Bytes(), &turn); err != nil {
		t.Fatalf("decode turn: %v", err)
	}
	turnID, _ := turn["turnId"].(string)

	streamReq := httptest.NewRequest(http.MethodPost, "/v1/assistant/turns/"+turnID+"/stream", nil)
	streamReq.Header.Set("X-Client-User-Id", "user_m5_http")
	streamResp := httptest.NewRecorder()
	handler.ServeHTTP(streamResp, streamReq)
	if streamResp.Code != http.StatusOK {
		t.Fatalf("stream status=%d body=%s", streamResp.Code, streamResp.Body.String())
	}
	body := streamResp.Body.String()
	for _, expected := range []string{
		"event: assistant.turn.started",
		"event: assistant.trace",
		"event: assistant.journey.updated",
		"event: assistant.process_timeline.updated",
		"event: assistant.skill.selected",
		"event: assistant.reasoning.started",
		"event: assistant.model.delta",
		"event: assistant.tool.requested",
		"event: assistant.tool.completed",
		"event: assistant.answer.delta",
		"event: assistant.answer.final",
		"event: assistant.turn.completed",
	} {
		if !bytes.Contains([]byte(body), []byte(expected)) {
			t.Fatalf("stream missing %s: %s", expected, body)
		}
	}
	for _, expected := range []string{
		"event: assistant.plan.updated",
		"event: assistant.search_query.generated",
		"event: assistant.observation.assessed",
		`"toolName":"app_search"`,
	} {
		if !bytes.Contains([]byte(body), []byte(expected)) {
			t.Fatalf("stream missing %s: %s", expected, body)
		}
	}
	if !bytes.Contains([]byte(body), []byte(`"text":"日程待办助手已生成会议与提醒方案`)) {
		t.Fatalf("stream missing final text payload: %s", body)
	}
	getTurnReq := httptest.NewRequest(http.MethodGet, "/v1/assistant/turns/"+turnID, nil)
	getTurnReq.Header.Set("X-Client-User-Id", "user_m5_http")
	getTurnResp := httptest.NewRecorder()
	handler.ServeHTTP(getTurnResp, getTurnReq)
	if getTurnResp.Code != http.StatusOK {
		t.Fatalf("get turn status=%d body=%s", getTurnResp.Code, getTurnResp.Body.String())
	}
	var completedTurn map[string]any
	if err := json.Unmarshal(getTurnResp.Body.Bytes(), &completedTurn); err != nil {
		t.Fatalf("decode completed turn: %v", err)
	}
	if completedTurn["status"] != "completed" {
		t.Fatalf("turn status=%v", completedTurn["status"])
	}
	streamState, _ := completedTurn["streamState"].(map[string]any)
	if streamState["completed"] != true {
		t.Fatalf("streamState=%v", streamState)
	}
}

func TestHandleTurnStream_M11LocalScenarios(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
	)
	handler := NewHandler(service).Routes()
	pack, err := application.LoadAssistantScenarioPack()
	if err != nil {
		t.Fatalf("LoadAssistantScenarioPack() error = %v", err)
	}
	cases := pack.AssistantTurnScenariosFor("beta")
	if len(cases) == 0 {
		t.Fatal("assistant scenarios should not be empty")
	}

	for _, tc := range cases {
		t.Run(tc.ID, func(t *testing.T) {
			if !containsHan(tc.Question) {
				t.Skip("非中文自由输入依赖模型语义改写，不由 HTTP deterministic 场景断言")
			}
			body := createM11TurnAndStream(t, handler, tc.ID, tc.SkillID, tc.DomainID, tc.Question)
			wantBody := append([]string{"final_answer"}, tc.RemoteAnswerFragments()...)
			for _, want := range wantBody {
				if !strings.Contains(body, want) {
					t.Fatalf("stream body missing %q: %s", want, body)
				}
			}
			for _, eventType := range tc.RemoteEventTypes() {
				if !strings.Contains(body, eventType) {
					t.Fatalf("stream missing event %q: %s", eventType, body)
				}
			}
		})
	}
}

func containsHan(text string) bool {
	for _, r := range text {
		if r >= '\u4e00' && r <= '\u9fff' {
			return true
		}
	}
	return false
}

func createM11TurnAndStream(t *testing.T, handler http.Handler, scenario, skillID, domainID, text string) string {
	t.Helper()
	userID := "user_m11_http_" + scenario
	conversationPayload, _ := json.Marshal(map[string]any{"summary": "M11 " + scenario})
	conversationReq := httptest.NewRequest(http.MethodPost, "/v1/assistant/conversations", bytes.NewReader(conversationPayload))
	conversationReq.Header.Set("Content-Type", "application/json")
	conversationReq.Header.Set("X-Client-User-Id", userID)
	conversationResp := httptest.NewRecorder()
	handler.ServeHTTP(conversationResp, conversationReq)
	if conversationResp.Code != http.StatusCreated {
		t.Fatalf("conversation status=%d body=%s", conversationResp.Code, conversationResp.Body.String())
	}
	var conversation map[string]any
	if err := json.Unmarshal(conversationResp.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}
	conversationID, _ := conversation["conversationId"].(string)
	if conversationID == "" {
		t.Fatalf("conversationId missing: %#v", conversation)
	}

	turnPayload, _ := json.Marshal(map[string]any{
		"turnType": "user",
		"skillId":  skillID,
		"domainId": domainID,
		"input":    map[string]any{"text": text},
		"trigger":  map[string]any{"type": "user_message"},
	})
	turnReq := httptest.NewRequest(http.MethodPost, "/v1/assistant/conversations/"+conversationID+"/turns", bytes.NewReader(turnPayload))
	turnReq.Header.Set("Content-Type", "application/json")
	turnReq.Header.Set("X-Client-User-Id", userID)
	turnResp := httptest.NewRecorder()
	handler.ServeHTTP(turnResp, turnReq)
	if turnResp.Code != http.StatusCreated {
		t.Fatalf("turn status=%d body=%s", turnResp.Code, turnResp.Body.String())
	}
	var turn map[string]any
	if err := json.Unmarshal(turnResp.Body.Bytes(), &turn); err != nil {
		t.Fatalf("decode turn: %v", err)
	}
	turnID, _ := turn["turnId"].(string)
	if turnID == "" {
		t.Fatalf("turnId missing: %#v", turn)
	}

	streamReq := httptest.NewRequest(http.MethodPost, "/v1/assistant/turns/"+turnID+"/stream", bytes.NewReader([]byte("{}")))
	streamReq.Header.Set("Content-Type", "application/json")
	streamReq.Header.Set("X-Client-User-Id", userID)
	streamResp := httptest.NewRecorder()
	handler.ServeHTTP(streamResp, streamReq)
	if streamResp.Code != http.StatusOK {
		t.Fatalf("stream status=%d body=%s", streamResp.Code, streamResp.Body.String())
	}
	return streamResp.Body.String()
}

func TestHandleTurnStream_M5ToolFailureReturnsRuntimeFailure(t *testing.T) {
	now := func() time.Time { return time.Date(2026, 4, 29, 3, 20, 0, 0, time.UTC) }
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		application.WithAgentLoop(application.NewAgentLoop(
			application.DefaultSkillRuntime{},
			application.ReactRuntime{
				Model: application.DeterministicModelProvider{},
				Tools: application.DefaultToolCoordinator{
					Now:       now,
					ForceFail: true,
				},
			},
			now,
		)),
	)
	handler := NewHandler(service).Routes()
	conversationPayload, _ := json.Marshal(map[string]any{"summary": "M5 failure"})
	conversationReq := httptest.NewRequest(http.MethodPost, "/v1/assistant/conversations", bytes.NewReader(conversationPayload))
	conversationReq.Header.Set("Content-Type", "application/json")
	conversationReq.Header.Set("X-Client-User-Id", "user_m5_fail")
	conversationResp := httptest.NewRecorder()
	handler.ServeHTTP(conversationResp, conversationReq)
	var conversation map[string]any
	if err := json.Unmarshal(conversationResp.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}
	conversationID, _ := conversation["conversationId"].(string)
	turnPayload, _ := json.Marshal(map[string]any{"input": map[string]any{"text": "验证失败路径"}})
	turnReq := httptest.NewRequest(http.MethodPost, "/v1/assistant/conversations/"+conversationID+"/turns", bytes.NewReader(turnPayload))
	turnReq.Header.Set("Content-Type", "application/json")
	turnReq.Header.Set("X-Client-User-Id", "user_m5_fail")
	turnResp := httptest.NewRecorder()
	handler.ServeHTTP(turnResp, turnReq)
	var turn map[string]any
	if err := json.Unmarshal(turnResp.Body.Bytes(), &turn); err != nil {
		t.Fatalf("decode turn: %v", err)
	}
	turnID, _ := turn["turnId"].(string)

	streamReq := httptest.NewRequest(http.MethodPost, "/v1/assistant/turns/"+turnID+"/stream", nil)
	streamReq.Header.Set("X-Client-User-Id", "user_m5_fail")
	streamResp := httptest.NewRecorder()
	handler.ServeHTTP(streamResp, streamReq)
	if streamResp.Code != http.StatusOK {
		t.Fatalf("stream status=%d body=%s", streamResp.Code, streamResp.Body.String())
	}
	body := streamResp.Body.String()
	if !bytes.Contains([]byte(body), []byte("event: assistant.failure")) {
		t.Fatalf("stream missing assistant.failure: %s", body)
	}
	if !bytes.Contains([]byte(body), []byte("event: assistant.turn.failed")) {
		t.Fatalf("stream missing assistant.turn.failed: %s", body)
	}
	if !bytes.Contains([]byte(body), []byte(`"runtimeFailure"`)) {
		t.Fatalf("stream missing runtimeFailure: %s", body)
	}
	getTurnReq := httptest.NewRequest(http.MethodGet, "/v1/assistant/turns/"+turnID, nil)
	getTurnReq.Header.Set("X-Client-User-Id", "user_m5_fail")
	getTurnResp := httptest.NewRecorder()
	handler.ServeHTTP(getTurnResp, getTurnReq)
	var failedTurn map[string]any
	if err := json.Unmarshal(getTurnResp.Body.Bytes(), &failedTurn); err != nil {
		t.Fatalf("decode failed turn: %v", err)
	}
	if failedTurn["status"] != "failed" {
		t.Fatalf("turn status=%v", failedTurn["status"])
	}
	if _, ok := failedTurn["failure"].(map[string]any); !ok {
		t.Fatalf("turn missing failure=%v", failedTurn["failure"])
	}
}
