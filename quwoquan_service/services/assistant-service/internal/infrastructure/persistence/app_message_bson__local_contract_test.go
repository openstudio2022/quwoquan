package persistence

import (
	"context"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

// TestAppMessageBSONRoundTripPersonalization 锁定主动消费证据的落库 key 与
// content-flywheel 数据面校验脚本 (eval_content_flywheel_loop.py 读 app_messages)
// 期望的 key 逐一对齐：_id / userId / personalized / interestTags / matchedSegments /
// lifecycleStage。这是端云一致性的硬契约：落库 key 漂移会让飞轮闭环脚本静默漏判。
func TestAppMessageBSONRoundTripPersonalization(t *testing.T) {
	msg := assistant.AppMessage{
		MessageID:       "msg_1",
		UserID:          "user_1",
		MessageType:     "assistant",
		Title:           "标题",
		Summary:         "摘要",
		Personalized:    true,
		InterestTags:    []string{"Topic/coffee", "Topic/travel"},
		MatchedSegments: []string{"foodie"},
		LifecycleStage:  "active",
	}

	raw, err := bson.Marshal(msg)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var doc bson.M
	if err := bson.Unmarshal(raw, &doc); err != nil {
		t.Fatalf("unmarshal to map: %v", err)
	}

	if doc["_id"] != "msg_1" {
		t.Errorf("expected _id=msg_1, got %v", doc["_id"])
	}
	if doc["userId"] != "user_1" {
		t.Errorf("expected userId=user_1, got %v", doc["userId"])
	}
	if doc["personalized"] != true {
		t.Errorf("expected personalized=true, got %v", doc["personalized"])
	}
	tags, ok := doc["interestTags"].(bson.A)
	if !ok || len(tags) != 2 {
		t.Fatalf("expected interestTags array len 2, got %v", doc["interestTags"])
	}
	segs, ok := doc["matchedSegments"].(bson.A)
	if !ok || len(segs) != 1 {
		t.Fatalf("expected matchedSegments array len 1, got %v", doc["matchedSegments"])
	}
	if doc["lifecycleStage"] != "active" {
		t.Errorf("expected lifecycleStage=active, got %v", doc["lifecycleStage"])
	}

	var back assistant.AppMessage
	if err := bson.Unmarshal(raw, &back); err != nil {
		t.Fatalf("unmarshal to struct: %v", err)
	}
	if back.MessageID != "msg_1" || back.UserID != "user_1" {
		t.Errorf("id/user round-trip mismatch: %+v", back)
	}
	if !back.Personalized || len(back.InterestTags) != 2 || len(back.MatchedSegments) != 1 || back.LifecycleStage != "active" {
		t.Errorf("personalization round-trip mismatch: %+v", back)
	}
}

// TestAppMessageMemoryStorePersonalizationPersisted 验证 store 持久化路径不丢个性化归因，
// 与 MongoAppMessageStore 共享同一 AppMessageStore 契约（Memory 用于 CI 无 mongo 场景）。
func TestAppMessageMemoryStorePersonalizationPersisted(t *testing.T) {
	store := NewMemoryAppMessageStore()
	msg := assistant.AppMessage{
		MessageID:       "msg_2",
		UserID:          "user_2",
		Personalized:    true,
		InterestTags:    []string{"Topic/film"},
		MatchedSegments: []string{"cinephile"},
		LifecycleStage:  "dormant",
	}
	if _, err := store.CreateAppMessage(context.Background(), msg); err != nil {
		t.Fatalf("create: %v", err)
	}
	got, err := store.GetAppMessage(context.Background(), "user_2", "msg_2")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	if !got.Personalized || len(got.InterestTags) != 1 || len(got.MatchedSegments) != 1 || got.LifecycleStage != "dormant" {
		t.Errorf("personalization not persisted: %+v", got)
	}
}
