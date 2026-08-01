package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	recommendation "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

func TestSearchIntentProjectionUsesPhysicalTTLAndRealClickOnly(t *testing.T) {
	db := requireMongoDB(t)
	ctx := context.Background()
	_, _ = db.Collection("rm_search_intent").DeleteMany(ctx, bson.M{})
	_, _ = db.Collection("rm_recommend_feature").DeleteMany(
		ctx,
		bson.M{"userId": "search-intent-user"},
	)
	if _, err := db.Collection("rm_recommend_feature").InsertOne(ctx, bson.M{
		"userId": "search-intent-user",
		"userFeatures": bson.M{
			"searchTermAffinity":      bson.M{"legacy": 9.0},
			"searchTermUpdatedAt":     time.Now().UTC(),
			"searchTopObjectAffinity": bson.M{"legacy-post": 9.0},
		},
	}); err != nil {
		t.Fatalf("seed legacy feature: %v", err)
	}

	projector := recommendation.NewRecommendFeatureProjector(db)
	if err := projector.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure indexes: %v", err)
	}
	occurredAt := time.Now().UTC()
	if err := projector.Project(ctx, recommendation.ProjectorEvent{
		ID:            "query:req-search-intent",
		Type:          "SearchRecommendationSignalPublished",
		AggregateType: "SearchRequestFact",
		AggregateID:   "req-search-intent",
		OccurredAt:    occurredAt,
		Payload: map[string]any{
			"signalType":      "query",
			"userId":          "search-intent-user",
			"normalizedQuery": "成都.火锅",
			"relatedTerms":    []string{"川菜"},
			"resultCount":     4,
		},
	}); err != nil {
		t.Fatalf("project query signal: %v", err)
	}

	var intent struct {
		Terms            []string  `bson:"terms"`
		EngagedObjectIDs []string  `bson:"engagedObjectIds"`
		ExpiresAt        time.Time `bson:"expiresAt"`
	}
	if err := db.Collection("rm_search_intent").FindOne(
		ctx,
		bson.M{"_id": "search-intent-user"},
	).Decode(&intent); err != nil {
		t.Fatalf("load search intent: %v", err)
	}
	if len(intent.Terms) != 2 || intent.Terms[0] != "成都.火锅" {
		t.Fatalf("query terms must remain values, got %#v", intent.Terms)
	}
	if len(intent.EngagedObjectIDs) != 0 {
		t.Fatalf("query exposure must not fabricate click affinity: %#v", intent.EngagedObjectIDs)
	}
	wantExpiresAt := occurredAt.Add(recommendation.SearchIntentTTL).Truncate(time.Millisecond)
	if !intent.ExpiresAt.Equal(wantExpiresAt) {
		t.Fatalf("expiresAt=%v want=%v", intent.ExpiresAt, wantExpiresAt)
	}

	if err := projector.Project(ctx, recommendation.ProjectorEvent{
		ID:            "feedback:click-1",
		Type:          "SearchRecommendationSignalPublished",
		AggregateType: "SearchRequestFact",
		AggregateID:   "req-search-intent",
		OccurredAt:    occurredAt.Add(time.Minute),
		Payload: map[string]any{
			"signalType":       "click",
			"userId":           "search-intent-user",
			"engagedObjectIds": []string{"post-clicked"},
		},
	}); err != nil {
		t.Fatalf("project click signal: %v", err)
	}
	store := recommendation.NewFeatureStore(db)
	features, err := store.GetUserFeatures(ctx, "search-intent-user")
	if err != nil {
		t.Fatalf("load user features: %v", err)
	}
	if features == nil ||
		features.SearchTermAffinities["成都.火锅"] == 0 ||
		features.SearchTopObjectAffinity["post-clicked"] == 0 {
		t.Fatalf("short-term search features not joined: %#v", features)
	}

	var legacy bson.M
	if err := db.Collection("rm_recommend_feature").FindOne(
		ctx,
		bson.M{"userId": "search-intent-user"},
	).Decode(&legacy); err != nil {
		t.Fatalf("load legacy feature: %v", err)
	}
	userFeatures, _ := legacy["userFeatures"].(bson.M)
	if _, exists := userFeatures["searchTermAffinity"]; exists {
		t.Fatalf("legacy embedded search terms were not physically removed: %#v", userFeatures)
	}
}
