// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-object-taxonomy-and-provider-registry/spec.md#gwt-001
// readiness_case: stage-tag-taxonomy-release-local
// readiness_case: activate-tag-taxonomy-release-local
package tag_taxonomy_release_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

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

func TestTaxonomyReleaseStageAllowsDifferentReleaseIDsToShareDigest(t *testing.T) {
	store := &readinessReleaseStore{releases: map[string]releasemodel.Release{}}
	facade, err := taxonomyrelease.NewFacade(store, readinessSnapshotReader{})
	if err != nil {
		t.Fatalf("NewFacade() error = %v", err)
	}
	ctx := context.Background()
	command := taxonomyrelease.StageCommand{
		ReleaseID:       "release-first",
		SourceOwner:     "quwoquan_data",
		CanonicalDigest: "sha256:shared-taxonomy-snapshot",
		ReleaseKind:     releasemodel.ReleaseKindContent,
		NodeCount:       1,
	}
	if _, err := facade.Stage(ctx, command); err != nil {
		t.Fatalf("stage first release: %v", err)
	}
	command.ReleaseID = "release-second"
	if _, err := facade.Stage(ctx, command); err != nil {
		t.Fatalf("stage second release with shared digest: %v", err)
	}
	if len(store.releases) != 2 {
		t.Fatalf("stored releases = %d, want 2", len(store.releases))
	}
	if _, err := facade.Activate(ctx, "release-second"); err != nil {
		t.Fatalf("activate second release: %v", err)
	}
	if store.activeID != "release-second" {
		t.Fatalf("active release = %q, want release-second", store.activeID)
	}

	command.ReleaseID = "release-first"
	command.NodeCount = 2
	if _, err := facade.Stage(ctx, command); err != releasemodel.ErrDigestConflict {
		t.Fatalf("same releaseId drift error = %v, want idempotency conflict", err)
	}
}

func TestTaxonomyReleaseStageResolvesConcurrentReleaseIDVersionConflict(t *testing.T) {
	command := taxonomyrelease.StageCommand{
		ReleaseID:       "release-concurrent",
		SourceOwner:     "quwoquan_data",
		CanonicalDigest: "sha256:concurrent-taxonomy-snapshot",
		ReleaseKind:     releasemodel.ReleaseKindContent,
		NodeCount:       1,
	}
	existing, err := releasemodel.NewStaged(
		command.ReleaseID,
		command.SourceOwner,
		command.CanonicalDigest,
		command.ReleaseKind,
		command.NodeCount,
		time.Unix(1, 0),
	)
	if err != nil {
		t.Fatalf("build concurrent release: %v", err)
	}

	for _, test := range []struct {
		name     string
		existing releasemodel.Release
		wantErr  error
	}{
		{name: "identical intent replays", existing: existing},
		{
			name: "drifted intent conflicts",
			existing: func() releasemodel.Release {
				drifted := existing
				drifted.CanonicalDigest = "sha256:drifted-taxonomy-snapshot"
				return drifted
			}(),
			wantErr: releasemodel.ErrDigestConflict,
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			store := &versionConflictReleaseStore{
				readinessReleaseStore: readinessReleaseStore{releases: map[string]releasemodel.Release{}},
				existing:              test.existing,
			}
			facade, err := taxonomyrelease.NewFacade(store, readinessSnapshotReader{})
			if err != nil {
				t.Fatalf("NewFacade() error = %v", err)
			}
			replayed, err := facade.Stage(context.Background(), command)
			if !errors.Is(err, test.wantErr) {
				t.Fatalf("Stage() error = %v, want %v", err, test.wantErr)
			}
			if test.wantErr == nil && replayed.ReleaseID != existing.ReleaseID {
				t.Fatalf("Stage() release = %+v, want existing release", replayed)
			}
			if store.loadCalls != 2 {
				t.Fatalf("Load() calls = %d, want initial miss plus conflict reload", store.loadCalls)
			}
		})
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

type versionConflictReleaseStore struct {
	readinessReleaseStore
	existing  releasemodel.Release
	loadCalls int
}

func (store *versionConflictReleaseStore) Load(
	_ context.Context,
	_ string,
) (releasemodel.Release, bool, error) {
	store.loadCalls++
	if store.loadCalls == 1 {
		return releasemodel.Release{}, false, nil
	}
	return store.existing, true, nil
}

func (store *versionConflictReleaseStore) InsertStaged(
	_ context.Context,
	_ releasemodel.Release,
) error {
	return releasemodel.ErrVersionConflict
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
