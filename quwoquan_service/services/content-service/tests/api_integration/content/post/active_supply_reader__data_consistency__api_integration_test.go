// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/feed-fallback-degrade/spec.md#gwt-001
package api_integration

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

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
			"status": "active", "activeReleaseId": "rel_wrong_owner",
			"manifestDigest": manifestDigest, "releaseClass": "commercial",
			"revision": int64(1), "sourceVersion": int64(1),
			"activatedAt": time.Now().UTC(),
		},
		bson.M{
			"environment": environment, "sourceOwner": "qwq_data",
			"status": "active", "activeReleaseId": "rel_empty",
			"manifestDigest": manifestDigest, "releaseClass": "commercial",
			"revision": int64(1), "sourceVersion": int64(1),
			"activatedAt": time.Now().UTC(),
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

func TestMongoActiveSupplyReaderRejectsMissingRevisionAndDuplicateAuthority(t *testing.T) {
	ctx := context.Background()
	db := requireMongoDB(t)
	const environment = "api-integration-active-supply-corruption"
	collection := db.Collection("data_release_state")
	if _, err := collection.DeleteMany(ctx, bson.M{"environment": environment}); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_, _ = collection.DeleteMany(context.Background(), bson.M{"environment": environment})
	})
	if _, err := collection.InsertOne(ctx, bson.M{
		"environment": environment, "sourceOwner": "qwq_data", "status": "active",
		"activeReleaseId": "rel_missing_revision",
		"manifestDigest":  "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
	}); err != nil {
		t.Fatal(err)
	}
	reader := persistence.NewMongoActiveSupplyReader(db, environment)
	if _, err := reader.ActiveSupplySnapshot(ctx); err == nil ||
		!strings.Contains(err.Error(), "revision/sourceVersion") {
		t.Fatalf("missing revision did not fail closed: %v", err)
	}
	if _, err := collection.DeleteMany(ctx, bson.M{"environment": environment}); err != nil {
		t.Fatal(err)
	}
	for index := 0; index < 2; index++ {
		status := "active"
		activeReleaseID := fmt.Sprintf("rel_duplicate_%d", index)
		if index == 1 {
			status = "superseded"
			activeReleaseID = ""
		}
		if _, err := collection.InsertOne(ctx, bson.M{
			"environment": environment, "sourceOwner": "qwq_data", "status": status,
			"activeReleaseId": activeReleaseID,
			"manifestDigest":  "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
			"revision":        int64(index + 1), "sourceVersion": int64(index + 1),
			"activatedAt": time.Now().UTC(),
		}); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := reader.ActiveSupplySnapshot(ctx); err == nil ||
		!strings.Contains(err.Error(), "ACTIVE_POINTER_DUPLICATE") {
		t.Fatalf("duplicate active pointer did not fail closed: %v", err)
	}
}
