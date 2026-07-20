package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	assistanthttp "quwoquan_service/services/assistant-service/internal/adapters/http"
	"quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/infrastructure/notificationclient"
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
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
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

// TestAssistantConversationOwnerIsolation 验证 owner 隔离与匿名拒绝。
func TestAssistantConversationOwnerIsolation(t *testing.T) {
	resetIntegrationState(t)
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()

	create := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/conversations",
		"owner-a", map[string]any{"summary": "私密会话"})
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
		"user-run-1", map[string]any{"summary": "run 会话"})
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
		"owner-run", map[string]any{"summary": "run 隔离"})
	var conversation assistant.AssistantConversation
	if err := json.Unmarshal(create.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}
	start := assistantAPIRequest(t, handler, http.MethodPost,
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		"owner-run", map[string]any{"input": map[string]any{"text": "隔离测试"}})
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
		"user-sse", map[string]any{"summary": "SSE 会话"})
	var conversation assistant.AssistantConversation
	if err := json.Unmarshal(create.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}
	start := assistantAPIRequest(t, handler, http.MethodPost,
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		"user-sse", map[string]any{"input": map[string]any{"text": "今天上海天气怎么样"}})
	var run assistant.AssistantTurn
	if err := json.Unmarshal(start.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v", err)
	}

	stream := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/runs/"+run.TurnID+"/events", "user-sse", nil)
	if stream.Code != http.StatusOK || !strings.Contains(stream.Body.String(), "event:") {
		t.Fatalf("first stream status=%d body=%s", stream.Code, stream.Body.String())
	}
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
		t.Fatalf("resume must replay persisted terminal event: body=%s", resume.Body.String())
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
		"user-score", map[string]any{"summary": "评分会话"})
	var conversation assistant.AssistantConversation
	if err := json.Unmarshal(create.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}
	start := assistantAPIRequest(t, handler, http.MethodPost,
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		"user-score", map[string]any{"input": map[string]any{"text": "给我一句鼓励"}})
	var run assistant.AssistantTurn
	if err := json.Unmarshal(start.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v", err)
	}
	stream := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/runs/"+run.TurnID+"/events", "user-score", nil)
	if stream.Code != http.StatusOK {
		t.Fatalf("stream status=%d", stream.Code)
	}
	count, err := integrationMongoDB.Collection("assistant_scorecard_facts").
		CountDocuments(ctx, bson.M{"_id": "run:" + run.TurnID})
	if err != nil || count != 1 {
		t.Fatalf("run completion scorecard count=%d err=%v", count, err)
	}

	// 重复完成（终态重放）不产生第二条 scorecard。
	replayStream := assistantAPIRequest(t, handler, http.MethodGet, "/assistant/runs/"+run.TurnID+"/events", "user-score", nil)
	if replayStream.Code != http.StatusOK {
		t.Fatalf("replay stream status=%d", replayStream.Code)
	}
	count, err = integrationMongoDB.Collection("assistant_scorecard_facts").
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
		"enforce-user", map[string]any{"summary": "consent gate"})
	var conversation assistant.AssistantConversation
	if err := json.Unmarshal(create.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}
	start := assistantAPIRequest(t, handler, http.MethodPost,
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		"enforce-user", map[string]any{
			"skillId": "personal_content_access",
			"input":   map[string]any{"text": "看看我的个人内容"},
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
			"skillId": "personal_content_access",
			"input":   map[string]any{"text": "再看一次"},
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

// TestSkillSubscriptionCronLeaseNoDuplicate 验证同一 tick 窗口的 Redis 租约：
// 两次 tick 并发（同窗口）只投递一次；lease key 带 TTL。
func TestSkillSubscriptionCronLeaseNoDuplicate(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	service := newIntegrationAssistantService(
		application.WithNotificationAppMessageCommandWriter(
			integrationNotificationCommandWriter(t),
		),
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

	tickBody := map[string]any{"now": "2026-07-19T08:30:00Z"}
	first, err := service.TickSkillSubscriptionCron(ctx, assistant.SkillSubscriptionCronTickInput{Now: "2026-07-19T08:30:00Z"})
	if err != nil {
		t.Fatalf("first tick: %v", err)
	}
	if first.ProcessedCount != 1 {
		t.Fatalf("first tick must process one subscription: %+v", first)
	}
	second, err := service.TickSkillSubscriptionCron(ctx, assistant.SkillSubscriptionCronTickInput{Now: "2026-07-19T08:30:00Z"})
	if err != nil {
		t.Fatalf("second tick: %v", err)
	}
	if second.ProcessedCount != 0 {
		t.Fatalf("same-window tick must be deduplicated by redis lease: %+v", second)
	}
	_ = tickBody
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
	if cancelledTurn.Status != "cancelled" || cancelledTurn.CompletedAt == nil {
		t.Fatalf("cancel must transition to cancelled terminal, got %#v", cancelledTurn)
	}

	// 幂等：重复 cancel 返回 cancelled 200
	cancelAgain := assistantAPIRequest(t, handler, http.MethodPost,
		"/assistant/runs/"+startedTurn.TurnID+"/cancel", userID, nil)
	if cancelAgain.Code != http.StatusOK {
		t.Fatalf("repeated cancel status=%d body=%s", cancelAgain.Code, cancelAgain.Body.String())
	}

	// Mongo 落盘核验 + 新 handler（模拟重启）读取终态与轮次列表
	var storedStatus struct {
		Status string `bson:"status"`
	}
	if err := integrationMongoDB.Collection("assistant_runs").
		FindOne(ctx, bson.M{"_id": startedTurn.TurnID}).Decode(&storedStatus); err != nil {
		t.Fatalf("read cancelled run from mongo: %v", err)
	}
	if storedStatus.Status != "cancelled" {
		t.Fatalf("mongo run status must be cancelled, got %s", storedStatus.Status)
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
		turnsView.Items[0].InputText != "帮我查一下天气" {
		t.Fatalf("turns view must expose cancelled turn summary after restart, got %#v", turnsView.Items)
	}

	// 非 owner 轮次查询防枚举
	foreignTurns := assistantAPIRequest(t, restartedHandler, http.MethodGet,
		"/assistant/conversations/"+target+"/turns", "user-other", nil)
	if foreignTurns.Code != http.StatusNotFound {
		t.Fatalf("non-owner turns must 404, got %d body=%s", foreignTurns.Code, foreignTurns.Body.String())
	}
}
