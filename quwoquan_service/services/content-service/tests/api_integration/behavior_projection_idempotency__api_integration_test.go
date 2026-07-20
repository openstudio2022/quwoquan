package api_integration

import (
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
)

// TestBehaviorProjectionReplayDoesNotDoubleIncrement 以真实 Mongo 验证行为 relay
// 的 at-least-once 语义：不同事实各应用一次，同一事实重放或旧事实晚到均不得重复 $inc。
func TestBehaviorProjectionReplayDoesNotDoubleIncrement(t *testing.T) {
	ctx := t.Context()
	db := requireMongoDB(t)
	const (
		userID  = "behavior_projection_idempotency_user"
		content = "behavior_projection_idempotency_post"
		tag     = "Topic/幂等投影"
	)
	features := db.Collection("rm_recommend_feature")
	feed := db.Collection("rm_discovery_feed")
	_, _ = features.DeleteMany(ctx, bson.M{"userId": userID})
	_, _ = feed.DeleteMany(ctx, bson.M{"postId": content})
	t.Cleanup(func() {
		_, _ = features.DeleteMany(ctx, bson.M{"userId": userID})
		_, _ = feed.DeleteMany(ctx, bson.M{"postId": content})
	})
	if _, err := feed.InsertOne(ctx, bson.M{
		"postId":    content,
		"viewCount": int64(0),
	}); err != nil {
		t.Fatalf("seed DiscoveryFeed row: %v", err)
	}

	recommendProjector := recinfra.NewRecommendFeatureProjector(db)
	if err := recommendProjector.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure RecommendFeature indexes: %v", err)
	}
	discoveryProjector := recinfra.NewDiscoveryFeedProjector(db)

	firstID := bson.NewObjectID().Hex()
	secondID := bson.NewObjectID().Hex()
	event := func(id string) recinfra.ProjectorEvent {
		return recinfra.ProjectorEvent{
			ID:            id,
			Type:          "BehaviorBatchReported",
			AggregateType: "BehaviorBatch",
			AggregateID:   userID,
			Payload: map[string]any{
				"userId": userID,
				"events": []map[string]any{{
					"contentId":       content,
					"action":          "impression",
					"state":           "impressed",
					"contentType":     "article",
					"tagRefs":         []string{tag},
					"engagementDepth": 1,
				}},
			},
		}
	}

	for _, projected := range []recinfra.ProjectorEvent{
		event(firstID),
		event(firstID),  // checkpoint 重放
		event(secondID), // 新事实
		event(firstID),  // 旧事实晚到
	} {
		if err := recommendProjector.Project(ctx, projected); err != nil {
			t.Fatalf("project RecommendFeature event %s: %v", projected.ID, err)
		}
		if err := discoveryProjector.Project(ctx, projected); err != nil {
			t.Fatalf("project DiscoveryFeed event %s: %v", projected.ID, err)
		}
	}

	var featureRow struct {
		LastID       string `bson:"behaviorProjectionLastId"`
		UserFeatures struct {
			TagInteraction map[string]int `bson:"tagInteraction"`
			TotalEvents    int            `bson:"totalEvents"`
		} `bson:"userFeatures"`
	}
	if err := features.FindOne(ctx, bson.M{"userId": userID}).Decode(&featureRow); err != nil {
		t.Fatalf("read RecommendFeature row: %v", err)
	}
	if got := featureRow.UserFeatures.TagInteraction[tag]; got != 2 {
		t.Fatalf("tagInteraction=%d, want two distinct facts only", got)
	}
	if got := featureRow.UserFeatures.TotalEvents; got != 2 {
		t.Fatalf("totalEvents=%d, want two distinct facts only", got)
	}
	if featureRow.LastID != secondID {
		t.Fatalf("RecommendFeature watermark=%q, want %q", featureRow.LastID, secondID)
	}

	var feedRow struct {
		ViewCount int64  `bson:"viewCount"`
		LastID    string `bson:"behaviorProjectionLastId"`
	}
	if err := feed.FindOne(ctx, bson.M{"postId": content}).Decode(&feedRow); err != nil {
		t.Fatalf("read DiscoveryFeed row: %v", err)
	}
	if feedRow.ViewCount != 2 {
		t.Fatalf("viewCount=%d, want two distinct facts only", feedRow.ViewCount)
	}
	if feedRow.LastID != secondID {
		t.Fatalf("DiscoveryFeed watermark=%q, want %q", feedRow.LastID, secondID)
	}
}
