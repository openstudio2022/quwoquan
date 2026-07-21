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

	rtauth "quwoquan_service/runtime/auth"
	rtoperation "quwoquan_service/runtime/operation"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/application/tool"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/environmentseed"
	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
)

type httpNotificationCommandWriter struct{}

func (httpNotificationCommandWriter) CreateAppMessage(
	_ context.Context,
	_ application.NotificationAppMessageCommand,
) (application.NotificationAppMessageReceipt, error) {
	return application.NotificationAppMessageReceipt{MessageID: "notification-http-test"}, nil
}

func TestConsentRoutesRequireVerifiedAccountAndIgnoreForgedHeader(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		application.WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
	)
	handler := NewHandler(service).Routes()

	forged := httptest.NewRequest(
		http.MethodPost,
		"/assistant/skills/personal_content_access/consent",
		strings.NewReader(`{"grantedScope":"read_own_content"}`),
	)
	forged.Header.Set("X-Client-User-Id", "forged-account")
	forgedRec := httptest.NewRecorder()
	handler.ServeHTTP(forgedRec, forged)
	if forgedRec.Code != http.StatusUnauthorized {
		t.Fatalf("forged status=%d body=%s", forgedRec.Code, forgedRec.Body.String())
	}

	verified := httptest.NewRequest(
		http.MethodPost,
		"/assistant/skills/personal_content_access/consent",
		strings.NewReader(`{"grantedScope":"read_own_content"}`),
	)
	verified.Header.Set("X-Client-User-Id", "forged-account")
	verified = verified.WithContext(rtauth.WithPrincipal(
		verified.Context(),
		rtauth.Principal{
			Claims: rtauth.Claims{Subject: "account-1"},
			Actor:  rtoperation.ActorContext{AccountID: "account-1"},
		},
	))
	verifiedRec := httptest.NewRecorder()
	handler.ServeHTTP(verifiedRec, verified)
	if verifiedRec.Code != http.StatusOK {
		t.Fatalf("verified status=%d body=%s", verifiedRec.Code, verifiedRec.Body.String())
	}

	items, err := service.ListConsents(context.Background(), "account-1")
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].UserID != "account-1" {
		t.Fatalf("trusted account consent=%+v", items)
	}
	forgedItems, err := service.ListConsents(context.Background(), "forged-account")
	if err != nil {
		t.Fatal(err)
	}
	if len(forgedItems) != 0 {
		t.Fatalf("forged account received consent=%+v", forgedItems)
	}
}

func TestHandleReportInteractionEvent_BatchWrapperAndHeaders(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		application.WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
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
	req := httptest.NewRequest(http.MethodPost, "/assistant/learning/events", bytes.NewReader(payload))
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
}

func TestHandleReportScorecard_BatchWrapper(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		application.WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
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
	req := httptest.NewRequest(http.MethodPost, "/internal/assistant/learning/scorecards", bytes.NewReader(payload))
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
		application.WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
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
	req := httptest.NewRequest(http.MethodGet, "/assistant/ops/learning-summary", nil)
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

func TestAssistantDoesNotExposeNotificationRoutes(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		application.WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
	)
	handler := NewHandler(service).Routes()
	for _, route := range []struct {
		method string
		path   string
	}{
		{http.MethodPost, "/app-messages"},
		{http.MethodGet, "/app-messages"},
		{http.MethodGet, "/app-messages/unread-count"},
		{http.MethodGet, "/app-messages/stream"},
		{http.MethodPost, "/app-messages/message-1/read"},
	} {
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, httptest.NewRequest(route.method, route.path, nil))
		if response.Code != http.StatusNotFound {
			t.Fatalf("assistant route %s %s status=%d, want 404", route.method, route.path, response.Code)
		}
	}
}

func TestHandleSuggestCreationAssistance(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		application.WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		application.WithSkillSubscriptionStore(persistence.NewMemorySkillSubscriptionStore()),
		application.WithCreationSuggestGrounding(httpCreationGrounding{}),
	)
	if _, err := service.CreateSkillSubscription(context.Background(), "user_creation", assistant.CreateSkillSubscriptionInput{
		SkillID:  "creation_assistant",
		DomainID: "content_creation",
		Trigger:  assistant.SkillSubscriptionTrigger{Type: "cron", Cron: "0 8 * * *"},
	}); err != nil {
		t.Fatalf("CreateSkillSubscription error: %v", err)
	}
	handler := NewHandler(service).Routes()
	payload, _ := json.Marshal(map[string]any{
		"bodyDigest":        "峨眉山旅行路线和摄影点整理",
		"primaryHomepageId": "homepage_sight_emeishan",
	})
	req := httptest.NewRequest(http.MethodPost, "/assistant/skills/creation-suggest", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "user_creation")
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp["available"] != true {
		t.Fatalf("available=%v body=%s", resp["available"], w.Body.String())
	}
	tags, _ := resp["suggestedTagRefs"].([]any)
	if len(tags) == 0 {
		t.Fatalf("missing tag suggestions: %s", w.Body.String())
	}
}

type httpCreationGrounding struct{}

func (httpCreationGrounding) ResolveTagRefs(context.Context, []string) ([]string, error) {
	return []string{"Topic/旅行"}, nil
}

func (httpCreationGrounding) ResolveHomepages(
	_ context.Context,
	ids []string,
) ([]assistant.AssistantSuggestedHomepageView, error) {
	if len(ids) == 0 {
		return []assistant.AssistantSuggestedHomepageView{}, nil
	}
	return []assistant.AssistantSuggestedHomepageView{{
		ID:                ids[0],
		Type:              "sight",
		CanonicalEntityID: "entity_emeishan",
		DisplayName:       "峨眉山",
		Reason:            "已作为主关联主页",
	}}, nil
}

func TestHandleTickIntersectionReminders(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		application.WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		application.WithNotificationAppMessageCommandWriter(httpNotificationCommandWriter{}),
		application.WithIntersectionInboxReader(httpFakeIntersectionInboxReader{reasons: []application.IntersectionReminderReason{{
			ReasonID:    "reason_http_1",
			TargetID:    "user_2",
			TargetName:  "阿青",
			Dimension:   "content",
			PrimaryText: "共同讨论",
			IsFact:      true,
		}}}),
	)
	handler := NewHandler(service).Routes()
	payload, _ := json.Marshal(map[string]any{"userId": "user_http_intersection"})
	req := httptest.NewRequest(http.MethodPost, "/assistant/intersections/reminders/tick", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp["processedCount"] != float64(1) {
		t.Fatalf("response=%s", w.Body.String())
	}
}

type httpFakeIntersectionInboxReader struct {
	reasons []application.IntersectionReminderReason
}

func (r httpFakeIntersectionInboxReader) ListNewIntersectionReasons(context.Context, string, time.Time, int) ([]application.IntersectionReminderReason, error) {
	return r.reasons, nil
}

func TestHandleSkillSubscriptionLifecycleAndCronTick(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		application.WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		application.WithSkillSubscriptionStore(persistence.NewMemorySkillSubscriptionStore()),
		application.WithNotificationAppMessageCommandWriter(httpNotificationCommandWriter{}),
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
	createReq := httptest.NewRequest(http.MethodPost, "/assistant/skill-subscriptions", bytes.NewReader(payload))
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
	statusReq := httptest.NewRequest(http.MethodPatch, "/assistant/skill-subscriptions/"+subscriptionID+"/status", bytes.NewReader(statusPayload))
	statusReq.Header.Set("Content-Type", "application/json")
	statusReq.Header.Set("X-Client-User-Id", "user_sub_1")
	statusResp := httptest.NewRecorder()
	handler.ServeHTTP(statusResp, statusReq)
	if statusResp.Code != http.StatusOK {
		t.Fatalf("status update=%d body=%s", statusResp.Code, statusResp.Body.String())
	}

	resumePayload, _ := json.Marshal(map[string]any{"status": "active"})
	resumeReq := httptest.NewRequest(http.MethodPatch, "/assistant/skill-subscriptions/"+subscriptionID+"/status", bytes.NewReader(resumePayload))
	resumeReq.Header.Set("Content-Type", "application/json")
	resumeReq.Header.Set("X-Client-User-Id", "user_sub_1")
	handler.ServeHTTP(httptest.NewRecorder(), resumeReq)

	tickPayload, _ := json.Marshal(map[string]any{"now": "2026-04-29T08:00:00Z"})
	tickReq := httptest.NewRequest(http.MethodPost, "/internal/assistant/skill-subscriptions:tick", bytes.NewReader(tickPayload))
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
		application.WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		application.WithAgentLoop(newDeterministicHTTPTestAgentLoop()),
	)
	handler := NewHandler(service).Routes()

	conversationPayload, _ := json.Marshal(map[string]any{"summary": "M4 smoke"})
	conversationReq := httptest.NewRequest(http.MethodPost, "/assistant/conversations", bytes.NewReader(conversationPayload))
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
	turnReq := httptest.NewRequest(http.MethodPost, "/assistant/conversations/"+conversationID+"/runs", bytes.NewReader(turnPayload))
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

	streamReq := httptest.NewRequest(http.MethodGet, "/assistant/runs/"+turnID+"/events", nil)
	streamReq.Header.Set("X-Client-User-Id", "user_m4_1")
	streamResp := httptest.NewRecorder()
	handler.ServeHTTP(streamResp, streamReq)
	if streamResp.Code != http.StatusOK {
		t.Fatalf("turn stream status=%d body=%s", streamResp.Code, streamResp.Body.String())
	}
	body := streamResp.Body.String()
	if !bytes.Contains([]byte(body), []byte("event: run_started")) {
		t.Fatalf("stream missing turn started: %s", body)
	}
	if !bytes.Contains([]byte(body), []byte("event: completed")) {
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
		application.WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		application.WithAgentLoop(newDeterministicHTTPTestAgentLoop()),
	)
	handler := NewHandler(service).Routes()

	conversationPayload, _ := json.Marshal(map[string]any{"summary": "M5 e2e"})
	conversationReq := httptest.NewRequest(http.MethodPost, "/assistant/conversations", bytes.NewReader(conversationPayload))
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
	turnReq := httptest.NewRequest(http.MethodPost, "/assistant/conversations/"+conversationID+"/runs", bytes.NewReader(turnPayload))
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

	streamReq := httptest.NewRequest(http.MethodGet, "/assistant/runs/"+turnID+"/events", nil)
	streamReq.Header.Set("X-Client-User-Id", "user_m5_http")
	streamResp := httptest.NewRecorder()
	handler.ServeHTTP(streamResp, streamReq)
	if streamResp.Code != http.StatusOK {
		t.Fatalf("stream status=%d body=%s", streamResp.Code, streamResp.Body.String())
	}
	body := streamResp.Body.String()
	for _, expected := range []string{
		"event: run_started",
		"event: process_replace",
		"event: process_append",
		"event: process_commit",
		"event: answer_delta",
		"event: completed",
	} {
		if !bytes.Contains([]byte(body), []byte(expected)) {
			t.Fatalf("stream missing %s: %s", expected, body)
		}
	}
	for _, expected := range []string{
		`"toolName":"app_search"`,
	} {
		if !bytes.Contains([]byte(body), []byte(expected)) {
			t.Fatalf("stream missing %s: %s", expected, body)
		}
	}
	if !bytes.Contains([]byte(body), []byte(`"finalAnswer":"日程待办助手已生成会议与提醒方案`)) {
		t.Fatalf("stream missing final text payload: %s", body)
	}
	for _, forbidden := range []string{
		"assistant.model.interaction",
		"assistant.model.delta",
		"debugTrace",
		`"reasoning"`,
		"assistant.search_query.generated",
	} {
		if bytes.Contains([]byte(body), []byte(forbidden)) {
			t.Fatalf("stream leaked internal payload %q: %s", forbidden, body)
		}
	}
	getTurnReq := httptest.NewRequest(http.MethodGet, "/assistant/runs/"+turnID, nil)
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
		application.WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		application.WithAgentLoop(newDeterministicHTTPTestAgentLoop()),
	)
	handler := NewHandler(service).Routes()
	pack, err := environmentseed.LoadAssistantScenarioPack()
	if err != nil {
		t.Fatalf("LoadAssistantScenarioPack() error = %v", err)
	}
	cases := pack.AssistantTurnScenariosFor("beta")
	if len(cases) == 0 {
		t.Fatal("assistant scenarios should not be empty")
	}
	cases = deterministicHanScenarios(cases)
	if len(cases) == 0 {
		t.Fatal("assistant beta scenarios should include deterministic Han questions")
	}

	for _, tc := range cases {
		t.Run(tc.ID, func(t *testing.T) {
			body := createM11TurnAndStream(t, handler, tc.ID, tc.SkillID, tc.DomainID, tc.Question)
			wantBody := append([]string{"completed"}, tc.RemoteAnswerFragments()...)
			for _, want := range wantBody {
				if !strings.Contains(body, want) {
					t.Fatalf("stream body missing %q: %s", want, body)
				}
			}
			for _, eventType := range []string{
				"run_started",
				"process_replace",
				"process_append",
				"process_commit",
				"answer_delta",
				"completed",
			} {
				if !strings.Contains(body, eventType) {
					t.Fatalf("stream missing event %q: %s", eventType, body)
				}
			}
		})
	}
}

func TestHandleTurnStreamRejectsResumeTokenFromAnotherRun(t *testing.T) {
	store := persistence.NewMemoryConversationRunStore()
	_, _, err := store.InsertTurn(t.Context(), assistant.AssistantTurn{
		TurnID:         "turn-resume-owner",
		ConversationID: "conv-resume-owner",
		UserID:         "user-resume-owner",
		Status:         "completed",
		AnswerText:     "done",
		StreamState: assistant.AssistantTurnStreamState{
			LastSeq:     3,
			Completed:   true,
			ResumeToken: streaming.NewResumeToken("turn-resume-owner", 3),
		},
		CreatedAt: time.Date(2026, 7, 20, 15, 0, 0, 0, time.UTC),
	})
	if err != nil {
		t.Fatalf("seed turn: %v", err)
	}
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		application.WithConversationRunStore(store),
	)
	request := httptest.NewRequest(http.MethodGet, "/assistant/runs/turn-resume-owner/events", nil)
	request.Header.Set("X-Client-User-Id", "user-resume-owner")
	request.Header.Set("Last-Event-ID", streaming.NewResumeToken("another-run", 1))
	response := httptest.NewRecorder()
	NewHandler(service).Routes().ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if !bytes.Contains(response.Body.Bytes(), []byte("ASSISTANT.USER.run_invalid_argument")) {
		t.Fatalf("body=%s", response.Body.String())
	}
}

func TestRunResumeAfterSeqAcceptsMetadataQueryToken(t *testing.T) {
	const runID = "turn-resume-query"
	request := httptest.NewRequest(
		http.MethodGet,
		"/assistant/runs/"+runID+"/events",
		nil,
	)
	query := request.URL.Query()
	query.Set("resumeToken", streaming.NewResumeToken(runID, 7))
	request.URL.RawQuery = query.Encode()

	afterSeq, err := runResumeAfterSeq(request, runID)
	if err != nil {
		t.Fatalf("runResumeAfterSeq() error = %v", err)
	}
	if afterSeq != 7 {
		t.Fatalf("afterSeq = %d, want 7", afterSeq)
	}
}

func deterministicHanScenarios(cases []environmentseed.AssistantScenarioFixture) []environmentseed.AssistantScenarioFixture {
	filtered := make([]environmentseed.AssistantScenarioFixture, 0, len(cases))
	for _, tc := range cases {
		if containsHan(tc.Question) {
			filtered = append(filtered, tc)
		}
	}
	return filtered
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
	conversationReq := httptest.NewRequest(http.MethodPost, "/assistant/conversations", bytes.NewReader(conversationPayload))
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
	turnReq := httptest.NewRequest(http.MethodPost, "/assistant/conversations/"+conversationID+"/runs", bytes.NewReader(turnPayload))
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

	streamReq := httptest.NewRequest(http.MethodGet, "/assistant/runs/"+turnID+"/events", nil)
	streamReq.Header.Set("Content-Type", "application/json")
	streamReq.Header.Set("X-Client-User-Id", userID)
	streamResp := httptest.NewRecorder()
	handler.ServeHTTP(streamResp, streamReq)
	if streamResp.Code != http.StatusOK {
		t.Fatalf("stream status=%d body=%s", streamResp.Code, streamResp.Body.String())
	}
	return streamResp.Body.String()
}

func newDeterministicHTTPTestAgentLoop() *application.AgentLoop {
	registry := tool.BaseRegistry()
	registry.Register(tool.AppSearchMetadata(), func(_ context.Context, _ tool.Request) (tool.Result, error) {
		return tool.Result{Output: map[string]any{
			"provider": "test_search_adapter",
			"summary":  "站内检索测试结果",
			"results": []map[string]any{{
				"target":   "article",
				"objectId": "post_test",
				"title":    "站内检索测试结果",
			}},
			"citations": []map[string]any{},
			"provenance": map[string]any{
				"provider":     "test_search_adapter",
				"indexVersion": "test",
			},
		}}, nil
	})
	registry.Register(tool.WebSearchMetadata(), func(_ context.Context, _ tool.Request) (tool.Result, error) {
		return tool.Result{Output: map[string]any{
			"provider":   "test_web_adapter",
			"summary":    "公开网络检索测试结果",
			"references": []map[string]any{},
		}}, nil
	})
	return application.NewAgentLoop(
		application.DefaultSkillRuntime{},
		application.ReactRuntime{
			Model: application.DeterministicModelProvider{},
			Tools: application.DefaultToolCoordinator{Registry: registry},
		},
		nil,
	)
}

func TestHandleTurnStream_M5ToolFailureReturnsRuntimeFailure(t *testing.T) {
	now := func() time.Time { return time.Date(2026, 4, 29, 3, 20, 0, 0, time.UTC) }
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		application.WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
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
	conversationReq := httptest.NewRequest(http.MethodPost, "/assistant/conversations", bytes.NewReader(conversationPayload))
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
	turnReq := httptest.NewRequest(http.MethodPost, "/assistant/conversations/"+conversationID+"/runs", bytes.NewReader(turnPayload))
	turnReq.Header.Set("Content-Type", "application/json")
	turnReq.Header.Set("X-Client-User-Id", "user_m5_fail")
	turnResp := httptest.NewRecorder()
	handler.ServeHTTP(turnResp, turnReq)
	var turn map[string]any
	if err := json.Unmarshal(turnResp.Body.Bytes(), &turn); err != nil {
		t.Fatalf("decode turn: %v", err)
	}
	turnID, _ := turn["turnId"].(string)

	streamReq := httptest.NewRequest(http.MethodGet, "/assistant/runs/"+turnID+"/events", nil)
	streamReq.Header.Set("X-Client-User-Id", "user_m5_fail")
	streamResp := httptest.NewRecorder()
	handler.ServeHTTP(streamResp, streamReq)
	if streamResp.Code != http.StatusOK {
		t.Fatalf("stream status=%d body=%s", streamResp.Code, streamResp.Body.String())
	}
	body := streamResp.Body.String()
	if !bytes.Contains([]byte(body), []byte("event: failed")) {
		t.Fatalf("stream missing failed terminal event: %s", body)
	}
	if !bytes.Contains([]byte(body), []byte(`"runtimeFailure"`)) {
		t.Fatalf("stream missing runtimeFailure: %s", body)
	}
	getTurnReq := httptest.NewRequest(http.MethodGet, "/assistant/runs/"+turnID, nil)
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
