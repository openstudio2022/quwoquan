// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-object-taxonomy-and-provider-registry/spec.md#gwt-001
// readiness_case: stage-tag-taxonomy-release-local
// readiness_case: activate-tag-taxonomy-release-local
package tag_taxonomy_release_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	releasehttp "quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/adapters/inbound/http"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/application/taxonomyrelease"
	releasemodel "quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/domain/taxonomyrelease/model"
)

func TestTaxonomyReleaseCommandsOwnTheHTTPBoundary(t *testing.T) {
	store := &readinessReleaseStore{releases: map[string]releasemodel.Release{}}
	facade, err := taxonomyrelease.NewFacade(store, readinessSnapshotReader{})
	if err != nil {
		t.Fatalf("NewFacade() error = %v", err)
	}
	mux := http.NewServeMux()
	releasehttp.NewTaxonomyReleaseHandler(facade).Register(mux)

	stage := httptest.NewRequest(
		http.MethodPost,
		"/internal/tag/taxonomy-releases",
		strings.NewReader(`{"releaseId":"release-readiness","sourceOwner":"quwoquan_data","canonicalDigest":"sha256:0d583629fd806d8367064dcb64093c34e0a74446c3d9adb04603639a875bb04e","releaseKind":"content","nodeCount":1}`),
	)
	stageResponse := httptest.NewRecorder()
	mux.ServeHTTP(stageResponse, stage)
	if stageResponse.Code != http.StatusOK {
		t.Fatalf("stage status=%d body=%s", stageResponse.Code, stageResponse.Body.String())
	}

	activate := httptest.NewRequest(
		http.MethodPost,
		"/internal/tag/taxonomy-releases/release-readiness:activate",
		nil,
	)
	activateResponse := httptest.NewRecorder()
	mux.ServeHTTP(activateResponse, activate)
	if activateResponse.Code != http.StatusOK {
		t.Fatalf("activate status=%d body=%s", activateResponse.Code, activateResponse.Body.String())
	}
	if got := store.releases["release-readiness"]; got.Status != releasemodel.StatusActive {
		t.Fatalf("release status = %q, want active", got.Status)
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-errors/error-code-and-response-envelope/spec.md#gwt-003
func TestTaxonomyReleaseErrorPathUsesCompleteRuntimeErrorEnvelope(t *testing.T) {
	store := &readinessReleaseStore{releases: map[string]releasemodel.Release{}}
	facade, err := taxonomyrelease.NewFacade(store, readinessSnapshotReader{})
	if err != nil {
		t.Fatalf("NewFacade() error = %v", err)
	}
	mux := http.NewServeMux()
	releasehttp.NewTaxonomyReleaseHandler(facade).Register(mux)

	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/tag/taxonomy-releases",
		strings.NewReader(`{not json`),
	)
	request.Header.Set("X-Request-Id", "req-envelope-tag")
	response := httptest.NewRecorder()
	mux.ServeHTTP(response, request)

	if response.Code != http.StatusBadRequest {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	// 完整 RuntimeErrorResponse 信封形状：不允许退化为裸 {"code": ...}。
	var envelope map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("decode error envelope: %v", err)
	}
	if envelope["code"] != "TAG.USER.release_invalid_argument" {
		t.Fatalf("code=%v", envelope["code"])
	}
	if envelope["requestId"] != "req-envelope-tag" {
		t.Fatalf("requestId=%v", envelope["requestId"])
	}
	for _, field := range []string{"userMessage", "kind", "origin", "nature"} {
		value, _ := envelope[field].(string)
		if value == "" {
			t.Fatalf("%s missing in envelope: %s", field, response.Body.String())
		}
	}
}

type readinessSnapshotReader struct{}

func (readinessSnapshotReader) HasCompleteSnapshot(context.Context, string, int) (bool, error) {
	return true, nil
}

type readinessReleaseStore struct {
	releases map[string]releasemodel.Release
	activeID string
}

func (store *readinessReleaseStore) ActiveReleaseID(context.Context) (string, bool, error) {
	return store.activeID, store.activeID != "", nil
}

func (store *readinessReleaseStore) FindActive(context.Context) (releasemodel.Release, bool, error) {
	release, found := store.releases[store.activeID]
	return release, found, nil
}

func (store *readinessReleaseStore) Load(
	_ context.Context,
	releaseID string,
) (releasemodel.Release, bool, error) {
	release, found := store.releases[releaseID]
	return release, found, nil
}

func (store *readinessReleaseStore) FindByDigest(
	_ context.Context,
	digest string,
) (releasemodel.Release, bool, error) {
	for _, release := range store.releases {
		if release.CanonicalDigest == digest {
			return release, true, nil
		}
	}
	return releasemodel.Release{}, false, nil
}

func (store *readinessReleaseStore) InsertStaged(
	_ context.Context,
	release releasemodel.Release,
) error {
	store.releases[release.ReleaseID] = release
	return nil
}

func (store *readinessReleaseStore) ActivateExclusive(
	_ context.Context,
	target releasemodel.Release,
	previous *releasemodel.Release,
) error {
	if previous != nil {
		store.releases[previous.ReleaseID] = *previous
	}
	store.releases[target.ReleaseID] = target
	store.activeID = target.ReleaseID
	return nil
}
