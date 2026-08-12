//go:build mongo_integration

package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func TestMongoImportMigratesLegacyPostRefIDToStableContentID(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	posts := db.Collection("posts")
	contentID := "qwq_data_stable_content_001"
	legacyRef := "posts/article/攻略/测试景区攻略/3"
	nextRef := "posts/article/攻略/测试景区攻略/4"
	legacyID := LegacyRuntimePostID(legacyRef)

	if _, err := posts.InsertOne(ctx, bson.M{
		"_id": legacyID, "postId": legacyID, "postRef": legacyRef,
		"contentId": contentID, "sourceOwner": "qwq_data",
	}); err != nil {
		t.Fatalf("seed legacy imported Post: %v", err)
	}
	post := PostDoc{
		PostRef: nextRef, ContentID: contentID, ContentVersion: 4,
		ContentType: "article", ContentIdentity: "work", Title: "测试景区攻略",
		AuthorID: "builtin_travel_blogger", CreatedAt: time.Now().UTC(),
		UpdatedAt: time.Now().UTC(), PublishedAt: time.Now().UTC(),
	}
	if _, err := UpsertPostsWithOptions(ctx, posts, []PostDoc{post}, time.Now().UTC(), ImportOptions{
		SourceOwner: "qwq_data", ReleaseID: "research-release-4",
	}); err != nil {
		t.Fatalf("migrate stable content identity: %v", err)
	}

	stableID := RuntimePostID(contentID, nextRef)
	if count, err := posts.CountDocuments(ctx, bson.M{}); err != nil || count != 1 {
		t.Fatalf("rewrite must update one logical Post: count=%d err=%v", count, err)
	}
	var got struct {
		ID      string `bson:"_id"`
		PostRef string `bson:"postRef"`
	}
	if err := posts.FindOne(ctx, bson.M{"_id": stableID}).Decode(&got); err != nil {
		t.Fatalf("read stable imported Post: %v", err)
	}
	if got.ID != stableID || got.PostRef != nextRef {
		t.Fatalf("stable content identity migration drift: %+v", got)
	}

	feed := db.Collection("rm_discovery_feed")
	if _, err := feed.InsertOne(ctx, bson.M{
		"postId": LegacyRuntimePostID(legacyRef), "postRef": legacyRef,
		"contentId": contentID, "sourceOwner": "qwq_data",
	}); err != nil {
		t.Fatalf("seed legacy discovery identity: %v", err)
	}
	if _, err := UpsertDiscoveryFeedWithOptions(
		ctx, feed, []PostDoc{post}, nil, time.Now().UTC(),
		ImportOptions{SourceOwner: "qwq_data", ReleaseID: "research-release-4"},
	); err != nil {
		t.Fatalf("migrate discovery stable identity: %v", err)
	}
	if count, err := feed.CountDocuments(ctx, bson.M{}); err != nil || count != 1 {
		t.Fatalf("rewrite must keep one discovery item: count=%d err=%v", count, err)
	}
	if err := feed.FindOne(ctx, bson.M{"postId": stableID, "postRef": nextRef}).Err(); err != nil {
		t.Fatalf("read stable discovery identity: %v", err)
	}
}
