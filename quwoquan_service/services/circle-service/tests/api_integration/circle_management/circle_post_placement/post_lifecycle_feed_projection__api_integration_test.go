// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-002
package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	ports "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/domain/ports"
	"quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/infrastructure/persistence"
	testsupport "quwoquan_service/services/circle-service/tests/support"
)

func TestPostLifecycleMaintainsOnlyTheLocalCircleFeedItemProjection(t *testing.T) {
	database := testsupport.StartRealMongo(t, "circle_post_feed_item_projection")
	ctx := context.Background()
	projection := persistence.NewMongoPostLifecycleProjection(database)
	if err := projection.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}

	createdAt := time.Date(2026, 8, 2, 8, 0, 0, 0, time.UTC)
	publishedAt := createdAt.Add(time.Hour)
	if err := projection.ApplyPostLifecycle(ctx, ports.PostLifecycleEvent{
		EventID: "post-circle:PostPublished:1", EventType: "PostPublished",
		PostID: "post-circle", PostVersion: 1, OwnerPersonaID: "persona-author",
		State: "published", Visibility: "public", Moderation: "approved",
		OccurredAt: publishedAt,
		FeedItem: &ports.PostFeedItemSnapshot{
			ContentType: "article", ContentIdentity: "work",
			Title: "Local projection", MediaURLs: []string{"https://media.example/post-circle.jpg"},
			CreatedAt: createdAt, UpdatedAt: publishedAt, PublishedAt: publishedAt,
		},
	}); err != nil {
		t.Fatal(err)
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

	if err := projection.ApplyPostLifecycle(ctx, ports.PostLifecycleEvent{
		EventID: "post-circle:PostSettingsUpdated:2", EventType: "PostSettingsUpdated",
		PostID: "post-circle", PostVersion: 2, OwnerPersonaID: "persona-author",
		State: "published", Visibility: "private", Moderation: "approved",
		OccurredAt: publishedAt.Add(time.Minute),
		FeedItem: &ports.PostFeedItemSnapshot{
			ContentType: "article", ContentIdentity: "work", Title: "Private",
			CreatedAt: createdAt, UpdatedAt: publishedAt.Add(time.Minute), PublishedAt: publishedAt,
		},
	}); err != nil {
		t.Fatal(err)
	}
	if count, err := database.Collection("circle_feed_items").CountDocuments(
		ctx,
		bson.M{"_id": "post-circle"},
	); err != nil || count != 0 {
		t.Fatalf("private Post must leave Circle feed projection count=%d err=%v", count, err)
	}
}
