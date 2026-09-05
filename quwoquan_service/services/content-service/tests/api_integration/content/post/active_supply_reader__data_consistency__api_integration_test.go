// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/feed-fallback-degrade/spec.md#gwt-001
package api_integration

import (
	"context"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
)

func TestMongoActiveSupplyReaderUsesEnvironmentScopedActiveRelease(t *testing.T) {
	ctx := context.Background()
	db := requireMongoDB(t)
	const environment = "api-integration-active-supply"
	const releaseID = "rel_api_integration_active_supply"
	const contentID = "active_supply_video_001"
	const manifestDigest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	collection := db.Collection("data_release_state")
	posts := db.Collection("posts")
	if _, err := collection.DeleteMany(ctx, bson.M{"environment": environment}); err != nil {
		t.Fatalf("delete release state: %v", err)
	}
	t.Cleanup(func() {
		_, _ = collection.DeleteMany(context.Background(), bson.M{"environment": environment})
		_, _ = posts.DeleteMany(context.Background(), bson.M{"_id": contentID})
	})

	reader := persistence.NewMongoActiveSupplyReader(db, environment)
	snapshot, err := reader.ActiveSupplySnapshot(ctx)
	if err != nil {
		t.Fatalf("ActiveSupplySnapshot missing: %v", err)
	}
	if snapshot.Ready() {
		t.Fatal("environment without data_release_state must not report active supply")
	}

	if _, err := collection.InsertMany(ctx, []any{
		bson.M{
			"environment": environment, "sourceOwner": "other_owner",
			"kind": "candidate", "status": "active", "activeReleaseId": "rel_wrong_owner",
			"manifestDigest": manifestDigest, "releaseClass": "commercial",
		},
		bson.M{
			"environment": environment, "sourceOwner": "qwq_data",
			"kind": "active_pointer", "status": "active", "activeReleaseId": "rel_empty",
			"manifestDigest": manifestDigest, "releaseClass": "commercial",
		},
	}); err != nil {
		t.Fatalf("insert release states: %v", err)
	}

	snapshot, err = reader.ActiveSupplySnapshot(ctx)
	if err != nil {
		t.Fatalf("ActiveSupplySnapshot empty release: %v", err)
	}
	if snapshot.Ready() {
		t.Fatalf("zero-count release must not report ready supply: %+v", snapshot)
	}

	if _, err := collection.UpdateOne(ctx,
		bson.M{"environment": environment, "sourceOwner": "qwq_data"},
		bson.M{"$set": bson.M{
			"activeReleaseId": releaseID,
			"manifestDigest":  manifestDigest,
			"counts":          bson.M{"postsUpserted": 120, "feedUpserted": 120},
		}},
	); err != nil {
		t.Fatalf("activate non-empty release: %v", err)
	}
	if _, err := posts.InsertOne(ctx, bson.M{
		"_id": contentID, "sourceOwner": "qwq_data", "releaseId": releaseID,
		"manifestDigest":  manifestDigest,
		"lifecycleStatus": "active", "status": "published", "visibility": "public",
		"moderationStatus": "approved", "contentIdentity": "work", "contentType": "video",
		"videoUrl": "https://media.example.test/video.mp4", "durationMs": int64(1000),
	}); err != nil {
		t.Fatalf("seed active release post: %v", err)
	}
	snapshot, err = reader.ActiveSupplySnapshot(ctx)
	if err != nil {
		t.Fatalf("ActiveSupplySnapshot active: %v", err)
	}
	if !snapshot.Ready() {
		t.Fatalf("environment-scoped release-bound snapshot must be ready: %+v", snapshot)
	}
	if snapshot.ActiveReleaseID != releaseID || snapshot.SourceOwner != "qwq_data" ||
		snapshot.Status != "active" || snapshot.ManifestDigest != manifestDigest ||
		snapshot.ReleaseClass != "commercial" || snapshot.ReadbackStatus != "passed" ||
		snapshot.Posts != 1 || snapshot.PlayableVideos != 1 {
		t.Fatalf("active supply snapshot mismatch: %+v", snapshot)
	}

	// 同一 release identity 修复 releaseClass 时必须立即切换缓存身份；旧
	// commercial snapshot 不得在 TTL 内继续放行匿名 research feed。
	if _, err := collection.UpdateOne(ctx,
		bson.M{"environment": environment, "sourceOwner": "qwq_data"},
		bson.M{"$set": bson.M{"releaseClass": "research"}},
	); err != nil {
		t.Fatalf("switch active release class: %v", err)
	}
	snapshot, err = reader.ActiveSupplySnapshot(ctx)
	if err != nil {
		t.Fatalf("ActiveSupplySnapshot research class: %v", err)
	}
	if snapshot.ReleaseClass != "research" || !snapshot.IsResearchRelease() {
		t.Fatalf("releaseClass cache identity drifted: %+v", snapshot)
	}
}

func TestMongoActiveSupplyReaderIgnoresNonPointerActiveDocuments(t *testing.T) {
	ctx := context.Background()
	db := requireMongoDB(t)
	const environment = "api-integration-pointer-only"
	state := db.Collection("data_release_state")
	posts := db.Collection("posts")
	t.Cleanup(func() {
		_, _ = state.DeleteMany(context.Background(), bson.M{"environment": environment})
		_, _ = posts.DeleteMany(context.Background(), bson.M{"_id": "pointer-only-post"})
	})
	if _, err := state.InsertMany(ctx, []any{
		bson.M{"kind": "active_pointer", "status": "active", "environment": environment, "sourceOwner": "qwq_data", "activeReleaseId": "pointer-current", "manifestDigest": "sha256:" + strings.Repeat("c", 64), "releaseClass": "commercial", "activatedAt": time.Now().Add(-time.Hour)},
		bson.M{"kind": "candidate", "status": "active", "environment": environment, "sourceOwner": "qwq_data", "activeReleaseId": "candidate-later", "manifestDigest": "sha256:" + strings.Repeat("d", 64), "releaseClass": "commercial", "activatedAt": time.Now()},
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := posts.InsertOne(ctx, bson.M{"_id": "pointer-only-post", "sourceOwner": "qwq_data", "releaseId": "pointer-current", "manifestDigest": "sha256:" + strings.Repeat("c", 64), "lifecycleStatus": "active", "status": "published", "visibility": "public", "moderationStatus": "approved", "contentType": "article"}); err != nil {
		t.Fatal(err)
	}
	snapshot, err := persistence.NewMongoActiveSupplyReader(db, environment).ActiveSupplySnapshot(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if snapshot.ActiveReleaseID != "pointer-current" || snapshot.Posts != 1 {
		t.Fatalf("reader selected non-pointer latest: %+v", snapshot)
	}
	if _, err := state.UpdateOne(ctx, bson.M{"kind": "active_pointer", "environment": environment}, bson.M{"$set": bson.M{"status": "verified"}}); err != nil {
		t.Fatal(err)
	}
	snapshot, err = persistence.NewMongoActiveSupplyReader(db, environment).ActiveSupplySnapshot(ctx)
	if err != nil || snapshot.Ready() {
		t.Fatalf("non-active pointer must be invisible snapshot=%+v err=%v", snapshot, err)
	}
}

func TestMongoPublicPostQueriesFenceDataOwnedPostsToExactActiveRelease(t *testing.T) {
	ctx := context.Background()
	db := requireMongoDB(t)
	posts := db.Collection("posts")
	const releaseID = "rel_public_query_fence_active"
	const manifestDigest = "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
	const staleReleaseID = "rel_public_query_fence_stale"
	const staleDigest = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
	ids := []string{"query-fence-active", "query-fence-stale", "query-fence-ugc"}
	t.Cleanup(func() {
		_, _ = posts.DeleteMany(context.Background(), bson.M{"_id": bson.M{"$in": ids}})
	})

	base := bson.M{
		"authorId": "persona-query-fence", "gatheringRef": "gathering-query-fence",
		"status": "published", "visibility": "public", "moderationStatus": "approved",
		"contentType": "article", "publishedAt": time.Now().UTC(), "createdAt": time.Now().UTC(), "updatedAt": time.Now().UTC(),
	}
	documents := []any{
		mergeQueryFenceDocument(base, bson.M{"_id": ids[0], "sourceOwner": "qwq_data", "releaseId": releaseID, "manifestDigest": manifestDigest, "lifecycleStatus": "active"}),
		mergeQueryFenceDocument(base, bson.M{"_id": ids[1], "sourceOwner": "qwq_data", "releaseId": staleReleaseID, "manifestDigest": staleDigest, "lifecycleStatus": "active"}),
		mergeQueryFenceDocument(base, bson.M{"_id": ids[2], "sourceOwner": "user"}),
	}
	if _, err := posts.InsertMany(ctx, documents); err != nil {
		t.Fatal(err)
	}

	reader := persistence.NewMongoPostQueryReader(posts)
	if _, found, err := reader.FindReleaseBoundPostDetail(ctx, postports.NewPostDetailReadRequest(postports.NewPostID(ids[0]), releaseID, manifestDigest)); err != nil || !found {
		t.Fatalf("active detail found=%v err=%v", found, err)
	}
	if _, found, err := reader.FindReleaseBoundPostDetail(ctx, postports.NewPostDetailReadRequest(postports.NewPostID(ids[1]), releaseID, manifestDigest)); err != nil || found {
		t.Fatalf("stale detail found=%v err=%v", found, err)
	}

	authorPage, err := reader.ListAuthorPosts(ctx, postports.NewAuthorPostReadRequest(
		"persona-query-fence", postports.AuthorPostAccessPublic, "", "", "",
		postports.AuthorPostCursor{}, 20, releaseID, manifestDigest,
	))
	if err != nil {
		t.Fatal(err)
	}
	assertExactPostIDs(t, authorPage.Items, ids[0], ids[2])

	gatheringPage, err := reader.ListGatheringPosts(ctx, postports.NewGatheringPostReadRequest(
		"gathering-query-fence", postports.AuthorPostCursor{}, 20, releaseID, manifestDigest,
	))
	if err != nil {
		t.Fatal(err)
	}
	assertExactPostIDs(t, gatheringPage.Items, ids[0], ids[2])

	sitemapIDs, err := reader.ListPublicPostIDs(ctx, 5000, releaseID, manifestDigest)
	if err != nil {
		t.Fatal(err)
	}
	seen := map[string]bool{}
	for _, id := range sitemapIDs {
		if id == ids[0] || id == ids[1] || id == ids[2] {
			seen[id] = true
		}
	}
	if !seen[ids[0]] || seen[ids[1]] || !seen[ids[2]] {
		t.Fatalf("sitemap release fence result=%v", seen)
	}
}

func mergeQueryFenceDocument(base bson.M, overlay bson.M) bson.M {
	document := bson.M{}
	for key, value := range base {
		document[key] = value
	}
	for key, value := range overlay {
		document[key] = value
	}
	return document
}

func assertExactPostIDs(t *testing.T, items []postports.AuthorPostItemSlice, want ...string) {
	t.Helper()
	seen := map[string]bool{}
	for _, item := range items {
		seen[string(item.PostID)] = true
	}
	if len(items) != len(want) {
		t.Fatalf("post ids=%v want=%v", seen, want)
	}
	for _, id := range want {
		if !seen[id] {
			t.Fatalf("post ids=%v missing=%s", seen, id)
		}
	}
}
