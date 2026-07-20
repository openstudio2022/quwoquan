package api_integration

import (
	"log/slog"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	runtimelearning "quwoquan_service/runtime/learning"
	learninginfra "quwoquan_service/services/content-service/internal/infrastructure/learning"
)

// TestLearningEventDedupe 覆盖 recommendation/rec_model 契约
// （tests/contract.yaml#exposure_deterministic_event_id / feedback_request_correlation）：
// 确定性 eventId 作为 _id 提交，重放写入被唯一约束拒绝且按已存在处理，事实不重复。
func TestLearningEventDedupe(t *testing.T) {
	ctx := t.Context()
	db := requireMongoDB(t)
	coll := db.Collection("rec_learning_events")
	_, _ = coll.DeleteMany(ctx, bson.M{"context.feedRequestId": "frq_dedupe_case"})
	t.Cleanup(func() {
		_, _ = coll.DeleteMany(ctx, bson.M{"context.feedRequestId": "frq_dedupe_case"})
	})

	sink := learninginfra.NewMongoSink(db, slog.Default())
	exposure := runtimelearning.Event{
		EventID:    "rec_imp_dedupe_case_0001",
		EventType:  "rec_impression",
		Scenario:   "content_feed",
		OccurredAt: "2026-07-19T08:00:00Z",
		UserID:     "dedupe-user",
		TargetID:   "post_dedupe_1",
		Labels:     map[string]string{"sessionId": "s.dGVzdA.1"},
		Context: map[string]any{
			"feedRequestId": "frq_dedupe_case",
			"modelBucket":   "rule",
		},
	}
	feedback := exposure
	feedback.EventID = "rec_eng_dedupe_case_0001"
	feedback.EventType = "rec_engagement"
	feedback.Labels = map[string]string{"action": "like"}

	if err := sink.FlushEvents(ctx, []runtimelearning.Event{exposure, feedback}); err != nil {
		t.Fatalf("first flush: %v", err)
	}
	// 重放整批 + 追加一条新事实：重复被 _id 拒绝按已存在处理，新事实照常写入。
	fresh := exposure
	fresh.EventID = "rec_imp_dedupe_case_0002"
	fresh.TargetID = "post_dedupe_2"
	if err := sink.FlushEvents(ctx, []runtimelearning.Event{exposure, feedback, fresh}); err != nil {
		t.Fatalf("replayed flush must converge, got: %v", err)
	}

	count, err := coll.CountDocuments(ctx, bson.M{"context.feedRequestId": "frq_dedupe_case"})
	if err != nil {
		t.Fatalf("count learning events: %v", err)
	}
	if count != 3 {
		t.Fatalf("dedupe mismatch: want 3 unique facts, got %d", count)
	}
	var stored struct {
		ID          string `bson:"_id"`
		EventID     string `bson:"eventId"`
		ModelBucket string `bson:"-"`
	}
	if err := coll.FindOne(ctx, bson.M{"eventId": exposure.EventID}).Decode(&stored); err != nil {
		t.Fatalf("load exposure fact: %v", err)
	}
	if stored.ID != exposure.EventID {
		t.Fatalf("deterministic eventId must be the document _id: %q vs %q", stored.ID, exposure.EventID)
	}
}
