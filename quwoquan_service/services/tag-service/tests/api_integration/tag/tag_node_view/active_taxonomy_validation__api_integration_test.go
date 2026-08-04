package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/application/taxonomyrelease"
	releasemodel "quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/domain/taxonomyrelease/model"
)

func TestValidateTagRefsRejectsParentInactiveAndOldSnapshots(t *testing.T) {
	cleanCollections(t)
	ctx := context.Background()
	current := []*tagNodeFixture{
		{tagRef: "Topic", label: "主题"},
		{tagRef: "Topic/parent", label: "父标签"},
		{tagRef: "Topic/parent/leaf", label: "叶子"},
		{tagRef: "Topic/inactive", label: "已停用", lifecycleStatus: "deprecated"},
	}
	insertSnapshotFixtures(t, ctx, "release-current", current)
	insertSnapshotFixtures(t, ctx, "release-old", []*tagNodeFixture{
		{tagRef: "Topic/old-only", label: "旧快照标签"},
	})
	activateReleaseForSeed(t, "release-current", len(current))
	stageReleaseForTest(t, "release-old", 1)

	view := validateTagRefsRequest(t, "release-current", []string{
		" Topic/parent/leaf ",
		"Topic/parent",
		"Topic/inactive",
		"Topic/old-only",
		"Topic/missing",
		"Topic/parent/leaf",
	})
	if want := []string{"Topic/parent/leaf", "Topic/parent/leaf"}; !reflect.DeepEqual(view.Valid, want) {
		t.Fatalf("valid = %#v, want %#v", view.Valid, want)
	}
	if want := []string{"Topic/parent", "Topic/inactive", "Topic/old-only", "Topic/missing"}; !reflect.DeepEqual(view.Invalid, want) {
		t.Fatalf("invalid = %#v, want %#v", view.Invalid, want)
	}

	mismatch := validateTagRefsRequest(t, "release-old", []string{"Topic/parent/leaf"})
	if len(mismatch.Valid) != 0 || !reflect.DeepEqual(mismatch.Invalid, []string{"Topic/parent/leaf"}) {
		t.Fatalf("old expected release must fail closed, got %#v", mismatch)
	}
	if mismatch.TaxonomyReleaseID != "release-current" {
		t.Fatalf(
			"mismatched request must expose active release identity, got %q",
			mismatch.TaxonomyReleaseID,
		)
	}
}

func TestValidateTagRefsFailsClosedWithoutActiveRelease(t *testing.T) {
	cleanCollections(t)
	insertSnapshotFixtures(t, context.Background(), "release-staged", []*tagNodeFixture{
		{tagRef: "Topic/only-staged", label: "未激活"},
	})

	view := validateTagRefsRequest(t, "release-staged", []string{"Topic/only-staged"})
	if len(view.Valid) != 0 || !reflect.DeepEqual(view.Invalid, []string{"Topic/only-staged"}) {
		t.Fatalf("no active release must return invalid, got %#v", view)
	}
	if view.TaxonomyReleaseID != "" {
		t.Fatalf("no active release must not claim a snapshot, got %q", view.TaxonomyReleaseID)
	}
}

func TestSnapshotActivationPreventsStagedAndOldLeaks(t *testing.T) {
	cleanCollections(t)
	ctx := context.Background()
	insertSnapshotFixtures(t, ctx, "release-one", []*tagNodeFixture{
		{tagRef: "Topic/old-leaf", label: "旧叶子"},
	})
	activateReleaseForSeed(t, "release-one", 1)
	if view := validateTagRefsRequest(t, "release-one", []string{"Topic/old-leaf"}); !reflect.DeepEqual(view.Valid, []string{"Topic/old-leaf"}) {
		t.Fatalf("active first snapshot must validate its leaf, got %#v", view)
	}

	insertSnapshotFixtures(t, ctx, "release-two", []*tagNodeFixture{
		{tagRef: "Topic/new-leaf", label: "新叶子"},
	})
	stageReleaseForTest(t, "release-two", 1)
	if view := validateTagRefsRequest(t, "release-two", []string{"Topic/new-leaf"}); len(view.Valid) != 0 {
		t.Fatalf("staged snapshot leaked into validation: %#v", view)
	}
	if view := validateTagRefsRequest(t, "release-one", []string{"Topic/old-leaf"}); !reflect.DeepEqual(view.Valid, []string{"Topic/old-leaf"}) {
		t.Fatalf("staged import changed active snapshot: %#v", view)
	}

	facade, err := taxonomyrelease.NewFacade(releaseStore, tagNodeStore)
	if err != nil {
		t.Fatalf("new release facade: %v", err)
	}
	if _, err := facade.Activate(ctx, "release-two"); err != nil {
		t.Fatalf("activate second release: %v", err)
	}
	if view := validateTagRefsRequest(t, "release-two", []string{"Topic/new-leaf"}); !reflect.DeepEqual(view.Valid, []string{"Topic/new-leaf"}) {
		t.Fatalf("new active snapshot must validate its leaf: %#v", view)
	}
	if view := validateTagRefsRequest(t, "release-one", []string{"Topic/old-leaf"}); len(view.Valid) != 0 {
		t.Fatalf("retired snapshot leaked into validation: %#v", view)
	}
}

func TestSnapshotIdentityMigrationDropsRetiredGlobalTagRefIndex(t *testing.T) {
	cleanCollections(t)
	ctx := context.Background()
	if _, err := mongoDB.Collection("tag_nodes").Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "tagRef", Value: 1}},
		Options: options.Index().SetName("idx_tag_ref").SetUnique(true),
	}); err != nil {
		t.Fatalf("create retired global index: %v", err)
	}
	if _, err := mongoDB.Collection("tag_nodes").InsertOne(ctx, bson.M{
		"tagRef": "Topic/historical-only",
		"label":  "historical snapshot without release identity",
	}); err != nil {
		t.Fatalf("insert unversioned historical tag: %v", err)
	}
	insertSnapshotFixtures(t, ctx, "release-one", []*tagNodeFixture{
		{tagRef: "Topic/shared", label: "旧快照"},
	})
	if err := tagNodeStore.MigrateSnapshotIdentity(ctx); err != nil {
		t.Fatalf("migrate snapshot identity: %v", err)
	}
	insertSnapshotFixtures(t, ctx, "release-two", []*tagNodeFixture{
		{tagRef: "Topic/shared", label: "新快照"},
	})
	count, err := mongoDB.Collection("tag_nodes").CountDocuments(ctx, bson.M{"tagRef": "Topic/shared"})
	if err != nil || count != 2 {
		t.Fatalf("migration must preserve both snapshots, count=%d err=%v", count, err)
	}
	retiredCount, err := mongoDB.Collection("tag_nodes").CountDocuments(ctx, bson.M{
		"tagRef":    "Topic/historical-only",
		"releaseId": bson.M{"$exists": false},
	})
	if err != nil || retiredCount != 1 {
		t.Fatalf("migration must preserve unversioned history, count=%d err=%v", retiredCount, err)
	}
}

type tagNodeFixture struct {
	tagRef          string
	label           string
	lifecycleStatus string
}

func insertSnapshotFixtures(t *testing.T, ctx context.Context, releaseID string, fixtures []*tagNodeFixture) {
	t.Helper()
	for _, fixture := range fixtures {
		node := tagNode(fixture.tagRef, fixture.label, "")
		node.ReleaseID = releaseID
		if fixture.lifecycleStatus != "" {
			node.LifecycleStatus = fixture.lifecycleStatus
		}
		if _, err := tagNodeStore.Create(ctx, node); err != nil {
			t.Fatalf("insert snapshot node %s/%s: %v", releaseID, fixture.tagRef, err)
		}
	}
}

func stageReleaseForTest(t *testing.T, releaseID string, nodeCount int) {
	t.Helper()
	facade, err := taxonomyrelease.NewFacade(releaseStore, tagNodeStore)
	if err != nil {
		t.Fatalf("new release facade: %v", err)
	}
	if _, err := facade.Stage(context.Background(), taxonomyrelease.StageCommand{
		ReleaseID:       releaseID,
		SourceOwner:     "test",
		CanonicalDigest: "seed-" + releaseID,
		ReleaseKind:     releasemodel.ReleaseKindContent,
		NodeCount:       nodeCount,
	}); err != nil {
		t.Fatalf("stage test release %s: %v", releaseID, err)
	}
}

func validateTagRefsRequest(t *testing.T, expectedReleaseID string, tagRefs []string) struct {
	TaxonomyReleaseID string   `json:"taxonomyReleaseId"`
	Valid             []string `json:"valid"`
	Invalid           []string `json:"invalid"`
} {
	t.Helper()
	body, err := json.Marshal(struct {
		ExpectedTaxonomyReleaseID string   `json:"expectedTaxonomyReleaseId"`
		TagRefs                   []string `json:"tagRefs"`
	}{ExpectedTaxonomyReleaseID: expectedReleaseID, TagRefs: tagRefs})
	if err != nil {
		t.Fatalf("encode validate request: %v", err)
	}
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/tag/validate", bytes.NewReader(body))
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("validate status=%d body=%s", rec.Code, rec.Body.String())
	}
	var view struct {
		TaxonomyReleaseID string   `json:"taxonomyReleaseId"`
		Valid             []string `json:"valid"`
		Invalid           []string `json:"invalid"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &view); err != nil {
		t.Fatalf("decode validate response: %v", err)
	}
	return view
}
