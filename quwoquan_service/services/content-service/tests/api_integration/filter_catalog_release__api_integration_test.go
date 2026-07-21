package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	filtercatalogmodel "quwoquan_service/services/content-service/internal/domain/content/filter_catalog_release/model"
)

type filterCatalogStageFixture struct {
	ReleaseID                    string                                        `json:"releaseId"`
	SourceOwner                  string                                        `json:"sourceOwner"`
	CanonicalDigest              string                                        `json:"canonicalDigest"`
	Categories                   []filtercatalogmodel.FilterCategoryDefinition `json:"categories"`
	Presets                      []filtercatalogmodel.FilterPresetDefinition   `json:"presets"`
	RecommendedFallbackPresetIDs []string                                      `json:"recommendedFallbackPresetIds"`
}

func TestFilterCatalogStageDigestIdempotent(t *testing.T) {
	handler, store := newFilterCatalogAPI(t)
	first := validFilterCatalogStageFixture(t, "filter-release-stage-a", 12)
	firstResponse := performFilterCatalogCommand(
		t,
		handler,
		"/internal/content/filter-catalog-releases",
		first,
		"filter-stage-first",
	)
	if firstResponse["releaseId"] != first.ReleaseID ||
		firstResponse["status"] != string(filtercatalogmodel.StatusStaged) {
		t.Fatalf("unexpected Stage response: %+v", firstResponse)
	}

	replayed := first
	replayed.ReleaseID = "filter-release-stage-b"
	replayedResponse := performFilterCatalogCommand(
		t,
		handler,
		"/internal/content/filter-catalog-releases",
		replayed,
		"filter-stage-same-digest",
	)
	if replayedResponse["releaseId"] != first.ReleaseID {
		t.Fatalf("same digest must return first release: %+v", replayedResponse)
	}
	if count := countFilterCatalogDocuments(t, bson.M{}); count != 1 {
		t.Fatalf("same digest created %d releases, want 1", count)
	}
	if receipts := countFilterCatalogReceipts(t); receipts != 2 {
		t.Fatalf("each idempotent Stage must persist a command receipt, got %d", receipts)
	}

	conflicting := validFilterCatalogStageFixture(t, "filter-release-stage-conflict", 20)
	response := performFilterCatalogRequest(
		t,
		handler,
		http.MethodPost,
		"/internal/content/filter-catalog-releases",
		conflicting,
		"filter-stage-first",
	)
	assertFilterCatalogRuntimeError(
		t,
		response,
		http.StatusConflict,
		"CONTENT.USER.filter_catalog_idempotency_conflict",
	)
	if _, found, err := store.Load(context.Background(), conflicting.ReleaseID); err != nil || found {
		t.Fatalf("conflicting receipt wrote a release: found=%v err=%v", found, err)
	}
}

func TestFilterCatalogStageRejectsInvalidPayloadAndDigest(t *testing.T) {
	handler, _ := newFilterCatalogAPI(t)
	missingAdjustment := filterCatalogFixtureMap(
		t,
		validFilterCatalogStageFixture(t, "filter-release-missing-adjustment", 12),
	)
	presets := missingAdjustment["presets"].([]any)
	delete(presets[0].(map[string]any)["adjustments"].(map[string]any), "fade")
	response := performFilterCatalogRequest(
		t,
		handler,
		http.MethodPost,
		"/internal/content/filter-catalog-releases",
		missingAdjustment,
		"filter-stage-missing-adjustment",
	)
	assertFilterCatalogRuntimeError(
		t,
		response,
		http.StatusBadRequest,
		"CONTENT.USER.filter_catalog_invalid_argument",
	)

	invalidReference := validFilterCatalogStageFixture(t, "filter-release-invalid-ref", 12)
	invalidReference.Presets[1].CategoryID = "missing-category"
	response = performFilterCatalogRequest(
		t,
		handler,
		http.MethodPost,
		"/internal/content/filter-catalog-releases",
		invalidReference,
		"filter-stage-invalid-ref",
	)
	assertFilterCatalogRuntimeError(
		t,
		response,
		http.StatusBadRequest,
		"CONTENT.USER.filter_catalog_invalid_argument",
	)

	duplicateCategorySort := validFilterCatalogStageFixture(
		t,
		"filter-release-duplicate-category-sort",
		12,
	)
	duplicateCategorySort.Categories[1].Sort =
		duplicateCategorySort.Categories[0].Sort
	response = performFilterCatalogRequest(
		t,
		handler,
		http.MethodPost,
		"/internal/content/filter-catalog-releases",
		duplicateCategorySort,
		"filter-stage-duplicate-category-sort",
	)
	assertFilterCatalogRuntimeError(
		t,
		response,
		http.StatusBadRequest,
		"CONTENT.USER.filter_catalog_invalid_argument",
	)

	digestMismatch := validFilterCatalogStageFixture(t, "filter-release-bad-digest", 12)
	digestMismatch.CanonicalDigest = strings.Repeat("0", 64)
	response = performFilterCatalogRequest(
		t,
		handler,
		http.MethodPost,
		"/internal/content/filter-catalog-releases",
		digestMismatch,
		"filter-stage-bad-digest",
	)
	assertFilterCatalogRuntimeError(
		t,
		response,
		http.StatusBadRequest,
		"CONTENT.USER.filter_catalog_digest_mismatch",
	)
	if count := countFilterCatalogDocuments(t, bson.M{}); count != 0 {
		t.Fatalf("invalid catalogs wrote %d releases", count)
	}
}

func filterCatalogFixtureMap(
	t *testing.T,
	fixture filterCatalogStageFixture,
) map[string]any {
	t.Helper()
	encoded, err := json.Marshal(fixture)
	if err != nil {
		t.Fatal(err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(encoded, &decoded); err != nil {
		t.Fatal(err)
	}
	return decoded
}

func TestFilterCatalogActivateSingleActive(t *testing.T) {
	handler, store := newFilterCatalogAPI(t)
	stageFilterCatalog(t, handler, "filter-release-active-a", 12, "stage-active-a")
	stageFilterCatalog(t, handler, "filter-release-active-b", 20, "stage-active-b")

	performFilterCatalogCommand(
		t,
		handler,
		"/internal/content/filter-catalog-releases/filter-release-active-a:activate",
		nil,
		"activate-a",
	)
	activeA := loadFilterCatalogRelease(t, store, "filter-release-active-a")
	if activeA.Status() != filtercatalogmodel.StatusActive {
		t.Fatalf("first release was not activated: %+v", activeA.Snapshot())
	}
	versionA := activeA.Version()
	performFilterCatalogCommand(
		t,
		handler,
		"/internal/content/filter-catalog-releases/filter-release-active-a:activate",
		nil,
		"activate-a-noop",
	)
	activeA = loadFilterCatalogRelease(t, store, "filter-release-active-a")
	if activeA.Version() != versionA {
		t.Fatalf("already-active no-op incremented version: %d -> %d", versionA, activeA.Version())
	}

	performFilterCatalogCommand(
		t,
		handler,
		"/internal/content/filter-catalog-releases/filter-release-active-b:activate",
		nil,
		"activate-b",
	)
	if activeCount := countFilterCatalogDocuments(
		t,
		bson.M{"status": string(filtercatalogmodel.StatusActive)},
	); activeCount != 1 {
		t.Fatalf("active release count=%d want=1", activeCount)
	}
	retiredA := loadFilterCatalogRelease(t, store, "filter-release-active-a")
	activeB := loadFilterCatalogRelease(t, store, "filter-release-active-b")
	if retiredA.Status() != filtercatalogmodel.StatusRetired ||
		activeB.Status() != filtercatalogmodel.StatusActive {
		t.Fatalf(
			"single-active switch drifted: a=%+v b=%+v",
			retiredA.Snapshot(),
			activeB.Snapshot(),
		)
	}
}

func TestFilterCatalogRollbackRetiredRelease(t *testing.T) {
	handler, store := newFilterCatalogAPI(t)
	stageFilterCatalog(t, handler, "filter-release-rollback-a", 12, "stage-rollback-a")
	performFilterCatalogCommand(
		t,
		handler,
		"/internal/content/filter-catalog-releases/filter-release-rollback-a:activate",
		nil,
		"activate-rollback-a",
	)
	stageFilterCatalog(t, handler, "filter-release-rollback-b", 20, "stage-rollback-b")
	performFilterCatalogCommand(
		t,
		handler,
		"/internal/content/filter-catalog-releases/filter-release-rollback-b:activate",
		nil,
		"activate-rollback-b",
	)

	performFilterCatalogCommand(
		t,
		handler,
		"/internal/content/filter-catalog-releases/filter-release-rollback-a:rollback",
		nil,
		"rollback-a",
	)
	rolledBackA := loadFilterCatalogRelease(t, store, "filter-release-rollback-a")
	retiredB := loadFilterCatalogRelease(t, store, "filter-release-rollback-b")
	if rolledBackA.Status() != filtercatalogmodel.StatusActive ||
		retiredB.Status() != filtercatalogmodel.StatusRetired {
		t.Fatalf(
			"rollback did not atomically switch active release: a=%+v b=%+v",
			rolledBackA.Snapshot(),
			retiredB.Snapshot(),
		)
	}
	rollbackVersion := rolledBackA.Version()
	performFilterCatalogCommand(
		t,
		handler,
		"/internal/content/filter-catalog-releases/filter-release-rollback-a:rollback",
		nil,
		"rollback-a-noop",
	)
	rolledBackA = loadFilterCatalogRelease(t, store, "filter-release-rollback-a")
	if rolledBackA.Version() != rollbackVersion {
		t.Fatalf("already-active rollback incremented version: %d -> %d", rollbackVersion, rolledBackA.Version())
	}

	stageFilterCatalog(t, handler, "filter-release-staged-only", 30, "stage-only")
	response := performFilterCatalogRequest(
		t,
		handler,
		http.MethodPost,
		"/internal/content/filter-catalog-releases/filter-release-staged-only:rollback",
		nil,
		"rollback-staged",
	)
	assertFilterCatalogRuntimeError(
		t,
		response,
		http.StatusConflict,
		"CONTENT.USER.filter_catalog_invalid_transition",
	)
}

func TestFilterCatalogPublicReaderReturnsOnlyActiveRelease(t *testing.T) {
	handler, _ := newFilterCatalogAPI(t)
	response := performFilterCatalogRequest(
		t,
		handler,
		http.MethodGet,
		"/content/filter-catalog",
		nil,
		"",
	)
	assertFilterCatalogRuntimeError(
		t,
		response,
		http.StatusServiceUnavailable,
		"CONTENT.SYSTEM.filter_catalog_unavailable",
	)

	fixture := validFilterCatalogStageFixture(t, "filter-release-public", 12)
	stageFilterCatalogFixture(t, handler, fixture, "stage-public")
	performFilterCatalogCommand(
		t,
		handler,
		"/internal/content/filter-catalog-releases/filter-release-public:activate",
		nil,
		"activate-public",
	)
	response = performFilterCatalogRequest(
		t,
		handler,
		http.MethodGet,
		"/content/filter-catalog",
		nil,
		"",
	)
	if response.Code != http.StatusOK {
		t.Fatalf("GET active catalog status=%d body=%s", response.Code, response.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	for _, field := range []string{
		"releaseId",
		"canonicalDigest",
		"status",
		"categoryCount",
		"presetCount",
		"categories",
		"presets",
		"recommendedFallbackPresetIds",
		"importedAt",
		"activatedAt",
	} {
		if _, found := body[field]; !found {
			t.Errorf("public active catalog missing field %q: %+v", field, body)
		}
	}
	for _, internalField := range []string{
		"sourceOwner",
		"version",
		"receipt",
		"changed",
		"replayed",
	} {
		if _, leaked := body[internalField]; leaked {
			t.Errorf("public active catalog leaked internal field %q: %+v", internalField, body)
		}
	}
	if body["releaseId"] != fixture.ReleaseID ||
		body["canonicalDigest"] != fixture.CanonicalDigest ||
		body["status"] != string(filtercatalogmodel.StatusActive) {
		t.Fatalf("public active release drifted: %+v", body)
	}
}

func TestFilterCatalogReleaseRoundTrip(t *testing.T) {
	handler, _ := newFilterCatalogAPI(t)
	stageFilterCatalog(t, handler, "filter-release-roundtrip-a", 12, "roundtrip-stage-a")
	performFilterCatalogCommand(
		t,
		handler,
		"/internal/content/filter-catalog-releases/filter-release-roundtrip-a:activate",
		nil,
		"roundtrip-activate-a",
	)
	stageFilterCatalog(t, handler, "filter-release-roundtrip-b", 20, "roundtrip-stage-b")
	performFilterCatalogCommand(
		t,
		handler,
		"/internal/content/filter-catalog-releases/filter-release-roundtrip-b:activate",
		nil,
		"roundtrip-activate-b",
	)
	performFilterCatalogCommand(
		t,
		handler,
		"/internal/content/filter-catalog-releases/filter-release-roundtrip-a:rollback",
		nil,
		"roundtrip-rollback-a",
	)
	response := performFilterCatalogRequest(
		t,
		handler,
		http.MethodGet,
		"/content/filter-catalog",
		nil,
		"",
	)
	if response.Code != http.StatusOK {
		t.Fatalf("roundtrip GET status=%d body=%s", response.Code, response.Body.String())
	}
	var active map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &active); err != nil {
		t.Fatal(err)
	}
	if active["releaseId"] != "filter-release-roundtrip-a" {
		t.Fatalf("roundtrip rollback did not restore release a: %+v", active)
	}
}
