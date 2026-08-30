// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-006
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-006.t8
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-object-taxonomy-and-provider-registry/spec.md#gwt-001
// readiness_case: stage-tag-taxonomy-release-api
// readiness_case: activate-tag-taxonomy-release-api
package api_integration

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	nodemodel "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/model"
	releasehttp "quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/adapters/inbound/http"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/application/taxonomyrelease"
	releasemodel "quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/domain/taxonomyrelease/model"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/taxonomyreleasestore"
)

func TestTaxonomyReleaseHTTPStageAndActivateUseRealMongo(t *testing.T) {
	cleanReleases(t)
	mux := http.NewServeMux()
	releasehttp.NewTaxonomyReleaseHandler(newReleaseFacade(t)).Register(mux)

	stage := httptest.NewRequest(
		http.MethodPost,
		"/internal/tag/taxonomy-releases",
		strings.NewReader(`{"releaseId":"release-http","sourceOwner":"quwoquan_data","canonicalDigest":"sha256:147820eae7ea9ec513a8c59a80a935d4d47aad522aad5584ad654b37d0f65a0c","releaseKind":"content","nodeCount":1}`),
	)
	stageResponse := httptest.NewRecorder()
	mux.ServeHTTP(stageResponse, stage)
	if stageResponse.Code != http.StatusOK {
		t.Fatalf("stage status=%d body=%s", stageResponse.Code, stageResponse.Body.String())
	}
	seedSnapshot(t, "release-http", 1)
	activate := httptest.NewRequest(
		http.MethodPost,
		"/internal/tag/taxonomy-releases/release-http:activate",
		nil,
	)
	activateResponse := httptest.NewRecorder()
	mux.ServeHTTP(activateResponse, activate)
	if activateResponse.Code != http.StatusOK {
		t.Fatalf("activate status=%d body=%s", activateResponse.Code, activateResponse.Body.String())
	}
}

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

func TestTaxonomyReleaseStageIsIdempotentByFullReleaseIntent(t *testing.T) {
	cleanReleases(t)
	ctx := context.Background()
	collection := mongoDB.Collection("tag_taxonomy_releases")
	if err := collection.Indexes().DropOne(ctx, "idx_tag_taxonomy_release_digest"); err != nil {
		t.Fatalf("drop current digest index: %v", err)
	}
	if _, err := collection.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "canonicalDigest", Value: 1}},
		Options: options.Index().SetName("idx_tag_taxonomy_release_digest").SetUnique(true),
	}); err != nil {
		t.Fatalf("create former unique digest index: %v", err)
	}
	facade := newReleaseFacade(t)
	assertTaxonomyReleaseDigestIndexIsNonUnique(t, ctx)

	first, err := facade.Stage(ctx, taxonomyrelease.StageCommand{
		ReleaseID: "rel-1", SourceOwner: "qwq_data",
		CanonicalDigest: "digest-aaa", ReleaseKind: releasemodel.ReleaseKindContent, NodeCount: 42,
	})
	if err != nil {
		t.Fatalf("first stage: %v", err)
	}
	if first.Status != releasemodel.StatusStaged || first.Version != 1 {
		t.Fatalf("unexpected staged release: %+v", first)
	}

	// 同 releaseId 的完整导入意图相同才可幂等重放。
	replayed, err := facade.Stage(ctx, taxonomyrelease.StageCommand{
		ReleaseID: "rel-1", SourceOwner: "qwq_data",
		CanonicalDigest: "digest-aaa", ReleaseKind: releasemodel.ReleaseKindContent, NodeCount: 42,
	})
	if err != nil {
		t.Fatalf("replay stage: %v", err)
	}
	if replayed.ReleaseID != "rel-1" || replayed.Version != first.Version || replayed.Status != first.Status {
		t.Fatalf("identical stage must reuse the first release: first=%+v replayed=%+v", first, replayed)
	}

	// canonicalDigest 是快照校验值，不是跨 release 唯一身份。
	second, err := facade.Stage(ctx, taxonomyrelease.StageCommand{
		ReleaseID: "rel-2", SourceOwner: "qwq_data",
		CanonicalDigest: "digest-aaa", ReleaseKind: releasemodel.ReleaseKindContent, NodeCount: 42,
	})
	if err != nil {
		t.Fatalf("stage second release with shared digest: %v", err)
	}
	if second.ReleaseID != "rel-2" {
		t.Fatalf("shared digest must preserve second release identity: %+v", second)
	}

	for _, conflicting := range []taxonomyrelease.StageCommand{
		{
			ReleaseID: "rel-1", SourceOwner: "another_owner",
			CanonicalDigest: "digest-aaa", ReleaseKind: releasemodel.ReleaseKindContent, NodeCount: 42,
		},
		{
			ReleaseID: "rel-1", SourceOwner: "qwq_data",
			CanonicalDigest: "digest-aaa", ReleaseKind: releasemodel.ReleaseKindContent, NodeCount: 43,
		},
		{
			ReleaseID: "rel-1", SourceOwner: "qwq_data",
			CanonicalDigest: "digest-other", ReleaseKind: releasemodel.ReleaseKindContent, NodeCount: 42,
		},
		{
			ReleaseID: "rel-1", SourceOwner: "qwq_data",
			CanonicalDigest: "digest-aaa", ReleaseKind: releasemodel.ReleaseKindEmptyBaseline, NodeCount: 0,
		},
	} {
		if _, err := facade.Stage(ctx, conflicting); !errors.Is(err, releasemodel.ErrDigestConflict) {
			t.Fatalf("same-release drift error = %v, want idempotency conflict", err)
		}
	}
	count, err := mongoDB.Collection("tag_taxonomy_releases").CountDocuments(ctx, bson.M{})
	if err != nil || count != 2 {
		t.Fatalf("release docs=%d err=%v", count, err)
	}

	// 无效参数 fail-fast。
	if _, err := facade.Stage(ctx, taxonomyrelease.StageCommand{
		ReleaseID: "", CanonicalDigest: "x", SourceOwner: "o",
		ReleaseKind: releasemodel.ReleaseKindContent, NodeCount: 1,
	}); err == nil {
		t.Fatal("empty releaseId must be rejected")
	}
}

func assertTaxonomyReleaseDigestIndexIsNonUnique(t *testing.T, ctx context.Context) {
	t.Helper()
	indexes, err := mongoDB.Collection("tag_taxonomy_releases").Indexes().ListSpecifications(ctx)
	if err != nil {
		t.Fatalf("list release indexes: %v", err)
	}
	for _, index := range indexes {
		if index.Name != "idx_tag_taxonomy_release_digest" {
			continue
		}
		if index.Unique != nil && *index.Unique {
			t.Fatal("canonicalDigest index must be non-unique")
		}
		return
	}
	t.Fatal("canonicalDigest index is missing")
}

func TestTaxonomyReleaseActivateSingleActive(t *testing.T) {
	cleanReleases(t)
	facade := newReleaseFacade(t)
	ctx := context.Background()

	if _, err := facade.Stage(ctx, taxonomyrelease.StageCommand{
		ReleaseID: "rel-a", SourceOwner: "qwq_data",
		CanonicalDigest: "digest-a", ReleaseKind: releasemodel.ReleaseKindContent, NodeCount: 10,
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

	// 第二个 release 可复用相同快照 digest；激活仍严格按 releaseId 选择目标。
	if _, err := facade.Stage(ctx, taxonomyrelease.StageCommand{
		ReleaseID: "rel-b", SourceOwner: "qwq_data",
		CanonicalDigest: "digest-a", ReleaseKind: releasemodel.ReleaseKindContent, NodeCount: 11,
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
	var active releasemodel.Release
	if err := mongoDB.Collection("tag_taxonomy_releases").FindOne(ctx, bson.M{"status": "active"}).Decode(&active); err != nil {
		t.Fatalf("load active release: %v", err)
	}
	if active.ReleaseID != "rel-b" || active.CanonicalDigest != "digest-a" {
		t.Fatalf("activation must select rel-b by releaseId despite shared digest: %+v", active)
	}

	// retired immutable snapshot 可回放为 active，旧 active 仍只做状态切换而不物理删除。
	rolledBack, err := facade.Activate(ctx, "rel-a")
	if err != nil || rolledBack.Status != releasemodel.StatusActive {
		t.Fatalf("reactivate retired release: %+v err=%v", rolledBack, err)
	}
	if count, err := mongoDB.Collection("tag_nodes").CountDocuments(ctx, bson.M{
		"releaseId": "rel-a",
	}); err != nil || count != 10 {
		t.Fatalf("historical rel-a snapshot count=%d err=%v", count, err)
	}

	// release-bound empty baseline 是合法的零节点 snapshot，可激活也可被历史 snapshot 替换。
	if _, err := facade.Stage(ctx, taxonomyrelease.StageCommand{
		ReleaseID: "rel-empty", SourceOwner: "qwq_data",
		CanonicalDigest: "digest-empty",
		ReleaseKind:     releasemodel.ReleaseKindEmptyBaseline, NodeCount: 0,
	}); err != nil {
		t.Fatalf("stage empty baseline: %v", err)
	}
	empty, err := facade.Activate(ctx, "rel-empty")
	if err != nil || empty.Status != releasemodel.StatusActive || empty.NodeCount != 0 {
		t.Fatalf("activate empty baseline: %+v err=%v", empty, err)
	}
	replayedHistorical, err := facade.Activate(ctx, "rel-b")
	if err != nil || replayedHistorical.Status != releasemodel.StatusActive {
		t.Fatalf("replay historical rel-b: %+v err=%v", replayedHistorical, err)
	}
	if count, err := mongoDB.Collection("tag_taxonomy_releases").CountDocuments(ctx, bson.M{}); err != nil || count != 3 {
		t.Fatalf("immutable release history count=%d err=%v", count, err)
	}

	// 未知 releaseId 仍 fail-fast。
	if _, err := facade.Activate(ctx, "rel-missing"); err == nil {
		t.Fatal("unknown release must fail")
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
