// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-006
package api_integration

import (
	"context"
	"errors"
	"fmt"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	nodemodel "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/model"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/application/taxonomyrelease"
	releasemodel "quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/domain/taxonomyrelease/model"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/taxonomyreleasestore"
)

func newReleaseFacade(t *testing.T) *taxonomyrelease.Facade {
	t.Helper()
	store := taxonomyreleasestore.NewStore(mongoDB)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure release indexes: %v", err)
	}
	facade, err := taxonomyrelease.NewFacade(store, tagNodeStore)
	if err != nil {
		t.Fatalf("new release facade: %v", err)
	}
	return facade
}

func cleanReleases(t *testing.T) {
	t.Helper()
	if _, err := mongoDB.Collection("tag_taxonomy_releases").DeleteMany(context.Background(), bson.M{}); err != nil {
		t.Fatalf("clean releases: %v", err)
	}
	if _, err := mongoDB.Collection("tag_nodes").DeleteMany(context.Background(), bson.M{}); err != nil {
		t.Fatalf("clean tag snapshots: %v", err)
	}
}

func seedSnapshot(t *testing.T, releaseID string, nodeCount int) {
	t.Helper()
	for i := 0; i < nodeCount; i++ {
		if _, err := tagNodeStore.Create(context.Background(), &nodemodel.TagNode{
			TagRef:          fmt.Sprintf("Topic/%s/%d", releaseID, i),
			Group:           "Topic",
			Label:           "tag",
			DisplayLabel:    "tag",
			Depth:           2,
			ReleaseID:       releaseID,
			LifecycleStatus: "active",
		}); err != nil {
			t.Fatalf("seed snapshot %s/%d: %v", releaseID, i, err)
		}
	}
}

func TestTaxonomyReleaseStageDigestIdempotent(t *testing.T) {
	cleanReleases(t)
	facade := newReleaseFacade(t)
	ctx := context.Background()

	first, err := facade.Stage(ctx, taxonomyrelease.StageCommand{
		ReleaseID: "rel-1", SourceOwner: "qwq_data",
		CanonicalDigest: "digest-aaa", NodeCount: 42,
	})
	if err != nil {
		t.Fatalf("first stage: %v", err)
	}
	if first.Status != releasemodel.StatusStaged || first.Version != 1 {
		t.Fatalf("unexpected staged release: %+v", first)
	}

	// 完全相同的导入意图才可幂等重放。
	replayed, err := facade.Stage(ctx, taxonomyrelease.StageCommand{
		ReleaseID: "rel-1", SourceOwner: "qwq_data",
		CanonicalDigest: "digest-aaa", NodeCount: 42,
	})
	if err != nil {
		t.Fatalf("replay stage: %v", err)
	}
	if replayed.ReleaseID != "rel-1" {
		t.Fatalf("identical stage must reuse the first release: %+v", replayed)
	}
	for _, conflicting := range []taxonomyrelease.StageCommand{
		{
			ReleaseID: "rel-other", SourceOwner: "qwq_data",
			CanonicalDigest: "digest-aaa", NodeCount: 42,
		},
		{
			ReleaseID: "rel-1", SourceOwner: "another_owner",
			CanonicalDigest: "digest-aaa", NodeCount: 42,
		},
		{
			ReleaseID: "rel-1", SourceOwner: "qwq_data",
			CanonicalDigest: "digest-aaa", NodeCount: 43,
		},
		{
			ReleaseID: "rel-1", SourceOwner: "qwq_data",
			CanonicalDigest: "digest-other", NodeCount: 42,
		},
	} {
		if _, err := facade.Stage(ctx, conflicting); !errors.Is(err, releasemodel.ErrDigestConflict) {
			t.Fatalf("conflicting stage error = %v, want digest conflict", err)
		}
	}
	count, err := mongoDB.Collection("tag_taxonomy_releases").CountDocuments(ctx, bson.M{})
	if err != nil || count != 1 {
		t.Fatalf("release docs=%d err=%v", count, err)
	}

	// 无效参数 fail-fast。
	if _, err := facade.Stage(ctx, taxonomyrelease.StageCommand{
		ReleaseID: "", CanonicalDigest: "x", SourceOwner: "o", NodeCount: 1,
	}); err == nil {
		t.Fatal("empty releaseId must be rejected")
	}
}

func TestTaxonomyReleaseActivateSingleActive(t *testing.T) {
	cleanReleases(t)
	facade := newReleaseFacade(t)
	ctx := context.Background()

	if _, err := facade.Stage(ctx, taxonomyrelease.StageCommand{
		ReleaseID: "rel-a", SourceOwner: "qwq_data",
		CanonicalDigest: "digest-a", NodeCount: 10,
	}); err != nil {
		t.Fatalf("stage a: %v", err)
	}
	if _, err := facade.Activate(ctx, "rel-a"); !errors.Is(err, releasemodel.ErrSnapshotIncomplete) {
		t.Fatalf("incomplete staged snapshot activate error = %v, want snapshot incomplete", err)
	}
	seedSnapshot(t, "rel-a", 10)
	activatedA, err := facade.Activate(ctx, "rel-a")
	if err != nil || activatedA.Status != releasemodel.StatusActive {
		t.Fatalf("activate a: %+v err=%v", activatedA, err)
	}

	// 重复激活：no-op 重放安全（版本不变）。
	replay, err := facade.Activate(ctx, "rel-a")
	if err != nil || replay.Version != activatedA.Version {
		t.Fatalf("re-activate must be noop: %+v err=%v", replay, err)
	}

	// 激活第二个 release：旧 active 让位，同一时刻只有一个 active。
	if _, err := facade.Stage(ctx, taxonomyrelease.StageCommand{
		ReleaseID: "rel-b", SourceOwner: "qwq_data",
		CanonicalDigest: "digest-b", NodeCount: 11,
	}); err != nil {
		t.Fatalf("stage b: %v", err)
	}
	seedSnapshot(t, "rel-b", 11)
	activatedB, err := facade.Activate(ctx, "rel-b")
	if err != nil || activatedB.Status != releasemodel.StatusActive {
		t.Fatalf("activate b: %+v err=%v", activatedB, err)
	}
	activeCount, err := mongoDB.Collection("tag_taxonomy_releases").CountDocuments(ctx, bson.M{"status": "active"})
	if err != nil || activeCount != 1 {
		t.Fatalf("active releases=%d err=%v", activeCount, err)
	}
	var retired releasemodel.Release
	if err := mongoDB.Collection("tag_taxonomy_releases").FindOne(ctx, bson.M{"_id": "rel-a"}).Decode(&retired); err != nil {
		t.Fatalf("load retired: %v", err)
	}
	if retired.Status != releasemodel.StatusRetired {
		t.Fatalf("previous active must retire: %+v", retired)
	}

	// 未知 releaseId 与非法状态。
	if _, err := facade.Activate(ctx, "rel-missing"); err == nil {
		t.Fatal("unknown release must fail")
	}
	if _, err := facade.Activate(ctx, "rel-a"); err == nil {
		t.Fatal("retired release must not re-activate")
	}
}

func TestTaxonomyReleaseSingleActiveIndexAndDriftDetection(t *testing.T) {
	cleanReleases(t)
	ctx := context.Background()
	store := taxonomyreleasestore.NewStore(mongoDB)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure release indexes: %v", err)
	}
	activeOne := releasemodel.Release{ReleaseID: "active-one", CanonicalDigest: "active-one-digest", Status: releasemodel.StatusActive}
	activeTwo := releasemodel.Release{ReleaseID: "active-two", CanonicalDigest: "active-two-digest", Status: releasemodel.StatusActive}
	if _, err := mongoDB.Collection("tag_taxonomy_releases").InsertOne(ctx, activeOne); err != nil {
		t.Fatalf("insert first active release: %v", err)
	}
	if _, err := mongoDB.Collection("tag_taxonomy_releases").InsertOne(ctx, activeTwo); err == nil {
		t.Fatal("partial unique index must reject a second active release")
	}

	if err := mongoDB.Collection("tag_taxonomy_releases").Indexes().DropOne(ctx, "uq_tag_taxonomy_release_single_active"); err != nil {
		t.Fatalf("drop single-active index for drift test: %v", err)
	}
	if _, err := mongoDB.Collection("tag_taxonomy_releases").InsertOne(ctx, activeTwo); err != nil {
		t.Fatalf("insert drifted active release: %v", err)
	}
	if _, _, err := store.FindActive(ctx); !errors.Is(err, releasemodel.ErrActiveReleaseDrift) {
		t.Fatalf("FindActive() error = %v, want active-state drift", err)
	}

	cleanReleases(t)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("restore release indexes: %v", err)
	}
}
