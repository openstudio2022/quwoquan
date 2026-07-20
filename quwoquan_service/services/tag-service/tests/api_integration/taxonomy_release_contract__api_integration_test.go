package api_integration

import (
	"context"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/tag-service/internal/application/taxonomyrelease"
	releasemodel "quwoquan_service/services/tag-service/internal/domain/taxonomyrelease/model"
	"quwoquan_service/services/tag-service/internal/infrastructure/taxonomyreleasestore"
)

func newReleaseFacade(t *testing.T) *taxonomyrelease.Facade {
	t.Helper()
	store := taxonomyreleasestore.NewStore(mongoDB)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure release indexes: %v", err)
	}
	facade, err := taxonomyrelease.NewFacade(store)
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

	// 同 digest 重复 Stage（即使换 releaseId）：幂等返回首次记录，不落第二条。
	replayed, err := facade.Stage(ctx, taxonomyrelease.StageCommand{
		ReleaseID: "rel-other", SourceOwner: "qwq_data",
		CanonicalDigest: "digest-aaa", NodeCount: 42,
	})
	if err != nil {
		t.Fatalf("replay stage: %v", err)
	}
	if replayed.ReleaseID != "rel-1" {
		t.Fatalf("same digest must reuse the first release: %+v", replayed)
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
