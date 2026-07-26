// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-004
package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

func TestSearchSignalConsumerProjectsThroughRealRedisAndMongo(t *testing.T) {
	ctx := context.Background()
	redis := requireTestRouter(t).Scene("general")
	if err := redis.Del(
		ctx,
		recinfra.SearchRecommendationSignalStream,
		recinfra.SearchRecommendationSignalDLQ,
	); err != nil {
		t.Fatalf("clear search signal streams: %v", err)
	}
	if _, err := mongoDB.Collection("rm_search_intent").DeleteMany(
		ctx,
		bson.M{},
	); err != nil {
		t.Fatalf("clear search intent: %v", err)
	}
	projector := recinfra.NewRecommendFeatureProjector(mongoDB)
	if err := projector.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure recommendation indexes: %v", err)
	}
	consumer := recinfra.NewSearchSignalConsumer(
		redis,
		projector,
		"api-integration-search-signal",
		nil,
	)
	if _, err := redis.XAdd(
		ctx,
		recinfra.SearchRecommendationSignalStream,
		map[string]string{
			"signalId":         "query:real-redis-request",
			"signalType":       "query",
			"searchRequestId":  "real-redis-request",
			"userId":           "persona-real-redis",
			"sessionId":        "session-real-redis",
			"normalizedQuery":  "成都 火锅",
			"relatedTerms":     `["成都","火锅"]`,
			"engagedObjectIds": `[]`,
			"resultCount":      "8",
			"createdAt":        time.Now().UTC().Format(time.RFC3339Nano),
		},
	); err != nil {
		t.Fatalf("append real Redis signal: %v", err)
	}

	processed, err := consumer.ProcessOnce(ctx)
	if err != nil {
		t.Fatalf("consume real Redis signal: %v", err)
	}
	if processed != 1 {
		t.Fatalf("processed=%d want=1", processed)
	}
	var intent struct {
		Terms     []string  `bson:"terms"`
		ExpiresAt time.Time `bson:"expiresAt"`
	}
	if err := mongoDB.Collection("rm_search_intent").FindOne(
		ctx,
		bson.M{"_id": "persona-real-redis"},
	).Decode(&intent); err != nil {
		t.Fatalf("read projected search intent: %v", err)
	}
	if len(intent.Terms) != 3 ||
		intent.Terms[0] != "成都 火锅" ||
		intent.Terms[1] != "成都" ||
		intent.Terms[2] != "火锅" ||
		intent.ExpiresAt.Before(time.Now().UTC().Add(23*time.Hour)) {
		t.Fatalf("projected search intent=%+v", intent)
	}
	pending, err := redis.XPendingCount(
		ctx,
		recinfra.SearchRecommendationSignalStream,
		recinfra.SearchSignalConsumerGroup,
	)
	if err != nil || pending != 0 {
		t.Fatalf("pending=%d want=0 err=%v", pending, err)
	}
}
