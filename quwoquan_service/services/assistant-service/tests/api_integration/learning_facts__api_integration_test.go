package api_integration

import (
	"context"
	"net/http"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	assistanthttp "quwoquan_service/services/assistant-service/internal/adapters/http"
)

// TestInteractionEventHTTPContract 验证学习事件经 HTTP 写入真实 Mongo：
// 合法 payload 入库、非法 payload 结构化 400。
func TestInteractionEventHTTPContract(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()

	valid := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/learning/events",
		"learn-user", map[string]any{
			"events": []map[string]any{
				{
					"eventId":      "evt-http-1",
					"runId":        "run-http-1",
					"pageType":     "assistant_dialog",
					"feedbackType": "helpful",
				},
			},
		})
	if valid.Code != http.StatusOK {
		t.Fatalf("report event status=%d body=%s", valid.Code, valid.Body.String())
	}
	count, err := integrationMongoDB.Collection("assistant_interaction_events").
		CountDocuments(ctx, bson.M{"_id": "evt-http-1"})
	if err != nil || count != 1 {
		t.Fatalf("interaction event persisted count=%d err=%v", count, err)
	}

	invalid := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/learning/events",
		"learn-user", map[string]any{"events": []map[string]any{{"runId": ""}}})
	if invalid.Code < 400 || invalid.Code >= 500 {
		t.Fatalf("invalid payload must be 4xx: status=%d body=%s", invalid.Code, invalid.Body.String())
	}
}

// TestInteractionEventAppendDedupe 验证 eventId dedupe：重复上报幂等重放，
// 不产生第二条事实。
func TestInteractionEventAppendDedupe(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()

	body := map[string]any{
		"events": []map[string]any{
			{
				"eventId":      "evt-dedupe-1",
				"runId":        "run-dedupe-1",
				"pageType":     "assistant_dialog",
				"feedbackType": "helpful",
			},
		},
	}
	for i := 0; i < 2; i++ {
		response := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/learning/events", "dedupe-user", body)
		if response.Code != http.StatusOK {
			t.Fatalf("attempt %d status=%d body=%s", i, response.Code, response.Body.String())
		}
	}
	count, err := integrationMongoDB.Collection("assistant_interaction_events").
		CountDocuments(ctx, bson.M{"_id": "evt-dedupe-1"})
	if err != nil || count != 1 {
		t.Fatalf("dedupe must keep one fact: count=%d err=%v", count, err)
	}
}

// TestScorecardAppendDedupe 验证 scoreId dedupe（服务内部 append）。
func TestScorecardAppendDedupe(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()

	body := map[string]any{
		"scorecards": []map[string]any{
			{
				"scoreId":    "score-dedupe-1",
				"eventId":    "evt-score-1",
				"metricId":   "run_completion",
				"scoreValue": 1,
			},
		},
	}
	for i := 0; i < 2; i++ {
		response := assistantAPIRequest(t, handler, http.MethodPost,
			"/internal/assistant/learning/scorecards", "score-user", body)
		if response.Code != http.StatusOK {
			t.Fatalf("attempt %d status=%d body=%s", i, response.Code, response.Body.String())
		}
	}
	count, err := integrationMongoDB.Collection("assistant_scorecard_facts").
		CountDocuments(ctx, bson.M{"_id": "score-dedupe-1"})
	if err != nil || count != 1 {
		t.Fatalf("scorecard dedupe must keep one fact: count=%d err=%v", count, err)
	}
}
