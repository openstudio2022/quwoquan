// spec_ref: specs/feature-tree/circle-community/spec.md#dom-001
// readiness_case: project-content-post-lifecycle-api
package api_integration

import (
	"context"
	"strconv"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	messaging "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/adapters/inbound/events"
	"quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/infrastructure/persistence"
	testsupport "quwoquan_service/services/circle-service/tests/support"
)

func TestPostLifecycleMaintainsOnlyTheLocalCircleFeedItemProjection(t *testing.T) {
	database := testsupport.StartRealMongo(t, "circle_post_feed_item_projection")
	ctx := context.Background()
	redisRuntime, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		t.Fatalf("start real Redis: %v", err)
	}
	t.Cleanup(func() {
		if err := redisRuntime.Close(context.Background()); err != nil {
			t.Errorf("close real Redis: %v", err)
		}
	})
	if err := redisRuntime.FlushDBs(ctx, 0); err != nil {
		t.Fatal(err)
	}
	router := platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode: "standalone", Addr: redisRuntime.Addr,
				Password: redisRuntime.Password, DB: 0, TLS: redisRuntime.TLS,
			},
		},
		DefaultScene: "general",
	})
	t.Cleanup(func() {
		if err := router.Close(); err != nil {
			t.Errorf("close Redis router: %v", err)
		}
	})
	redisClient := router.Scene("general")
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"circle-post-placement-api-integration",
		runtimemessaging.RedisMessageTransportAdapter,
		redisClient,
		redisClient,
	)
	if err != nil {
		t.Fatal(err)
	}
	projection := persistence.NewMongoPostLifecycleProjection(database)
	if err := projection.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	consumer := messaging.NewContentPostConsumer(
		transport, projection, projection, "circle-post-placement-api-integration", nil,
	)

	createdAt := time.Date(2026, 8, 2, 8, 0, 0, 0, time.UTC)
	publishedAt := createdAt.Add(time.Hour)
	if _, err := redisClient.XAdd(
		ctx,
		messaging.ContentPostLifecycleStream,
		postLifecycleAPIValues(
			"post-circle:PostPublished:1", "PostPublished", 1, "public",
			createdAt, publishedAt,
		),
	); err != nil {
		t.Fatal(err)
	}
	if count, err := consumer.ProcessOnce(ctx); err != nil || count != 1 {
		t.Fatalf("consume public lifecycle count=%d err=%v", count, err)
	}
	if count, err := database.Collection("circle_feed_items").CountDocuments(ctx, bson.M{
		"_id": "post-circle", "postVersion": int64(1), "authorId": "persona-author",
		"status": "published", "title": "Local projection",
	}); err != nil || count != 1 {
		t.Fatalf("CircleFeedItem projection count=%d err=%v", count, err)
	}
	if names, err := database.ListCollectionNames(ctx, bson.M{"name": "posts"}); err != nil {
		t.Fatal(err)
	} else if len(names) != 0 {
		t.Fatalf("Circle projection must not create or read Content posts: %v", names)
	}

	if _, err := redisClient.XAdd(
		ctx,
		messaging.ContentPostLifecycleStream,
		postLifecycleAPIValues(
			"post-circle:PostSettingsUpdated:2", "PostSettingsUpdated", 2, "private",
			createdAt, publishedAt.Add(time.Minute),
		),
	); err != nil {
		t.Fatal(err)
	}
	if count, err := consumer.ProcessOnce(ctx); err != nil || count != 1 {
		t.Fatalf("consume private lifecycle count=%d err=%v", count, err)
	}
	if count, err := database.Collection("circle_feed_items").CountDocuments(
		ctx,
		bson.M{"_id": "post-circle"},
	); err != nil || count != 0 {
		t.Fatalf("private Post must leave Circle feed projection count=%d err=%v", count, err)
	}
	testsupport.AssertCollectionCount(t, database, "circle_content_post_inbox", 2)
}

func postLifecycleAPIValues(
	eventID string,
	eventType string,
	version int64,
	visibility string,
	createdAt time.Time,
	updatedAt time.Time,
) map[string]string {
	return map[string]string{
		"eventId": eventID, "eventType": eventType, "aggregateType": "Post",
		"aggregateId": "post-circle", "aggregateVersion": strconv.FormatInt(version, 10),
		"payload": "{\"postId\":\"post-circle\",\"authorId\":\"persona-author\"," +
			"\"status\":\"published\",\"visibility\":\"" + visibility + "\",\"moderationStatus\":\"approved\"," +
			"\"contentType\":\"article\",\"contentIdentity\":\"work\",\"title\":\"Local projection\"," +
			"\"mediaUrls\":[\"https://media.example/post-circle.jpg\"]," +
			"\"createdAt\":\"" + createdAt.Format(time.RFC3339Nano) + "\",\"updatedAt\":\"" + updatedAt.Format(time.RFC3339Nano) + "\"," +
			"\"publishedAt\":\"" + createdAt.Add(time.Hour).Format(time.RFC3339Nano) + "\"}",
		"occurredAt": updatedAt.Format(time.RFC3339Nano),
	}
}
