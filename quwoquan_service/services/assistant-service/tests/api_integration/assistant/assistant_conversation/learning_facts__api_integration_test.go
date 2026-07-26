// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/learning-event-ingestion/spec.md#gwt-001
package api_integration

import (
	"context"
	"net/http"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	assistanthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
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
					"feedbackType": "useful",
					"queryText":    "包含敏感偏好的原始问题",
					"answerText":   "包含敏感偏好的原始回答",
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
	var profile assistant.AssistantLearningProfile
	if err := integrationMongoDB.Collection("rm_assistant_learning_profile").
		FindOne(ctx, bson.M{"userId": "learn-user"}).
		Decode(&profile); err != nil {
		t.Fatalf("load useful feedback learning profile: %v", err)
	}
	if profile.LastFeedbackType != "useful" ||
		profile.LastFeedbackScore != 1 ||
		profile.PositiveFeedbackCount != 1 ||
		profile.NegativeFeedbackCount != 0 ||
		profile.LastQueryTextDigest == "" ||
		profile.LastQueryTextDigest == "包含敏感偏好的原始问题" ||
		profile.LastAnswerTextDigest == "" ||
		profile.LastAnswerTextDigest == "包含敏感偏好的原始回答" {
		t.Fatalf("useful feedback profile=%#v", profile)
	}

	invalid := assistantAPIRequest(t, handler, http.MethodPost, "/assistant/learning/events",
		"learn-user", map[string]any{"events": []map[string]any{{"runId": ""}}})
	if invalid.Code < 400 || invalid.Code >= 500 {
		t.Fatalf("invalid payload must be 4xx: status=%d body=%s", invalid.Code, invalid.Body.String())
	}
	count, err = integrationMongoDB.Collection("assistant_interaction_events").
		CountDocuments(ctx, bson.M{})
	if err != nil || count != 1 {
		t.Fatalf("invalid event must not create a success fact: count=%d err=%v", count, err)
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
				"feedbackType": "irrelevant",
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
	var stored assistant.InteractionEvent
	if err := integrationMongoDB.Collection("assistant_interaction_events").
		FindOne(ctx, bson.M{"_id": "evt-dedupe-1"}).
		Decode(&stored); err != nil {
		t.Fatalf("load irrelevant feedback event: %v", err)
	}
	if stored.FeedbackType != "irrelevant" || stored.FeedbackScore != -1 {
		t.Fatalf("irrelevant feedback normalization=%#v", stored)
	}
	var profile assistant.AssistantLearningProfile
	if err := integrationMongoDB.Collection("rm_assistant_learning_profile").
		FindOne(ctx, bson.M{"userId": "dedupe-user"}).
		Decode(&profile); err != nil {
		t.Fatalf("load irrelevant feedback learning profile: %v", err)
	}
	if profile.NegativeFeedbackCount != 1 || profile.LastFeedbackType != "irrelevant" {
		t.Fatalf("irrelevant feedback profile=%#v", profile)
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
