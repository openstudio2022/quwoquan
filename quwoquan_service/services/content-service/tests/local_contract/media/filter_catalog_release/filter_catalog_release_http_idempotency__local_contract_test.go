// readiness_case: stage-filter-catalog-release-local
// readiness_case: activate-filter-catalog-release-local
// readiness_case: rollback-filter-catalog-release-local
// readiness_case: get-active-filter-catalog-local
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/filter-catalog-release/spec.md#gwt-001

package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	filtercataloghttp "quwoquan_service/services/content-service/internal/media/filter_catalog_release/adapters/inbound/http"
	filtercatalogapp "quwoquan_service/services/content-service/internal/media/filter_catalog_release/application"
	filtercatalogmodel "quwoquan_service/services/content-service/internal/media/filter_catalog_release/domain/model"
	filtercatalogports "quwoquan_service/services/content-service/internal/media/filter_catalog_release/domain/ports"
)

type recordingFilterCatalogStore struct {
	stageCommits []filtercatalogports.StageCommit
	releases     map[string]*filtercatalogmodel.FilterCatalogRelease
}

func (store *recordingFilterCatalogStore) Load(
	_ context.Context,
	releaseID string,
) (*filtercatalogmodel.FilterCatalogRelease, bool, error) {
	release, found := store.releases[releaseID]
	return release, found, nil
}

func (store *recordingFilterCatalogStore) Stage(
	_ context.Context,
	commit filtercatalogports.StageCommit,
) (filtercatalogports.CommandResult, error) {
	store.stageCommits = append(store.stageCommits, commit)
	if store.releases == nil {
		store.releases = make(map[string]*filtercatalogmodel.FilterCatalogRelease)
	}
	store.releases[commit.Release.Snapshot().ReleaseID] = commit.Release
	return filtercatalogports.CommandResult{
		Release: commit.Release,
		Changed: true,
	}, nil
}

func (store *recordingFilterCatalogStore) Activate(
	_ context.Context,
	commit filtercatalogports.TransitionCommit,
) (filtercatalogports.CommandResult, error) {
	release, found := store.releases[commit.ReleaseID]
	if !found {
		return filtercatalogports.CommandResult{}, filtercatalogmodel.ErrReleaseNotFound
	}
	for id, candidate := range store.releases {
		if id != commit.ReleaseID && candidate.Status() == filtercatalogmodel.StatusActive {
			if err := candidate.Retire(); err != nil {
				return filtercatalogports.CommandResult{}, err
			}
		}
	}
	if err := release.Activate(commit.TransitionedAt); err != nil {
		return filtercatalogports.CommandResult{}, err
	}
	return filtercatalogports.CommandResult{Release: release, Changed: true}, nil
}

func (store *recordingFilterCatalogStore) Rollback(
	_ context.Context,
	commit filtercatalogports.TransitionCommit,
) (filtercatalogports.CommandResult, error) {
	release, found := store.releases[commit.ReleaseID]
	if !found {
		return filtercatalogports.CommandResult{}, filtercatalogmodel.ErrReleaseNotFound
	}
	for id, candidate := range store.releases {
		if id != commit.ReleaseID && candidate.Status() == filtercatalogmodel.StatusActive {
			if err := candidate.Retire(); err != nil {
				return filtercatalogports.CommandResult{}, err
			}
		}
	}
	if err := release.Rollback(commit.TransitionedAt); err != nil {
		return filtercatalogports.CommandResult{}, err
	}
	return filtercatalogports.CommandResult{Release: release, Changed: true}, nil
}

func (store *recordingFilterCatalogStore) GetActive(
	_ context.Context,
) (*filtercatalogmodel.FilterCatalogRelease, bool, error) {
	for _, release := range store.releases {
		if release.Status() == filtercatalogmodel.StatusActive {
			return release, true, nil
		}
	}
	return nil, false, nil
}

func TestFilterCatalogStageHTTPBindsIdempotencyKey(t *testing.T) {
	categories, presets, fallbacks := validFilterCatalogPayload()
	digest, err := filtercatalogmodel.ComputeCanonicalDigest(categories, presets, fallbacks)
	if err != nil {
		t.Fatalf("compute digest: %v", err)
	}
	store := &recordingFilterCatalogStore{}
	service, err := filtercatalogapp.NewService(store, store)
	if err != nil {
		t.Fatal(err)
	}
	handler := filtercataloghttp.NewHandler(filtercatalogapp.BindFacades(service))
	body, err := json.Marshal(map[string]any{
		"releaseId":                    "filter-release-http-idempotency",
		"sourceOwner":                  "qwq-data",
		"canonicalDigest":              digest,
		"categories":                   categories,
		"presets":                      presets,
		"recommendedFallbackPresetIds": fallbacks,
	})
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/content/filter-catalog-releases",
		bytes.NewReader(body),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", "http-stage-key-1")
	recorder := httptest.NewRecorder()
	handler.Stage(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("Stage HTTP status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	if len(store.stageCommits) != 1 {
		t.Fatalf("expected one Stage commit, got %d", len(store.stageCommits))
	}
	if store.stageCommits[0].IdempotencyKey != "http-stage-key-1" {
		t.Fatalf(
			"Idempotency-Key was not bound into Stage commit: %q",
			store.stageCommits[0].IdempotencyKey,
		)
	}
	if store.stageCommits[0].Release == nil ||
		store.stageCommits[0].Release.Snapshot().ReleaseID != "filter-release-http-idempotency" {
		t.Fatalf("unexpected staged release: %+v", store.stageCommits[0].Release)
	}
}

func TestFilterCatalogTransitionAndActiveQueryHTTPUseObjectFacades(t *testing.T) {
	categories, presets, fallbacks := validFilterCatalogPayload()
	digest, err := filtercatalogmodel.ComputeCanonicalDigest(categories, presets, fallbacks)
	if err != nil {
		t.Fatalf("compute digest: %v", err)
	}
	store := &recordingFilterCatalogStore{releases: make(map[string]*filtercatalogmodel.FilterCatalogRelease)}
	service, err := filtercatalogapp.NewService(store, store)
	if err != nil {
		t.Fatal(err)
	}
	handler := filtercataloghttp.NewHandler(filtercatalogapp.BindFacades(service))

	stage := func(releaseID, key string) {
		body, marshalErr := json.Marshal(map[string]any{
			"releaseId": releaseID, "sourceOwner": "qwq-data", "canonicalDigest": digest,
			"categories": categories, "presets": presets,
			"recommendedFallbackPresetIds": fallbacks,
		})
		if marshalErr != nil {
			t.Fatal(marshalErr)
		}
		request := httptest.NewRequest(http.MethodPost, "/internal/content/filter-catalog-releases", bytes.NewReader(body))
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("Idempotency-Key", key)
		recorder := httptest.NewRecorder()
		handler.Stage(recorder, request)
		if recorder.Code != http.StatusOK {
			t.Fatalf("Stage %s status=%d body=%s", releaseID, recorder.Code, recorder.Body.String())
		}
	}
	transition := func(releaseID, key string, action func(http.ResponseWriter, *http.Request)) {
		request := httptest.NewRequest(http.MethodPost, "/internal/content/filter-catalog-releases/"+releaseID, nil)
		request.SetPathValue("releaseId", releaseID)
		request.Header.Set("Idempotency-Key", key)
		recorder := httptest.NewRecorder()
		action(recorder, request)
		if recorder.Code != http.StatusOK {
			t.Fatalf("transition %s status=%d body=%s", releaseID, recorder.Code, recorder.Body.String())
		}
	}

	stage("filter-release-a", "stage-a")
	transition("filter-release-a", "activate-a", handler.Activate)
	stage("filter-release-b", "stage-b")
	transition("filter-release-b", "activate-b", handler.Activate)
	transition("filter-release-a", "rollback-a", handler.Rollback)

	activeRequest := httptest.NewRequest(http.MethodGet, "/content/filter-catalog", nil)
	activeRecorder := httptest.NewRecorder()
	handler.GetActive(activeRecorder, activeRequest)
	if activeRecorder.Code != http.StatusOK {
		t.Fatalf("GetActive status=%d body=%s", activeRecorder.Code, activeRecorder.Body.String())
	}
	var active filtercatalogapp.FilterCatalogSlice
	if err := json.Unmarshal(activeRecorder.Body.Bytes(), &active); err != nil {
		t.Fatal(err)
	}
	if active.ReleaseID != "filter-release-a" || active.Status != filtercatalogmodel.StatusActive {
		t.Fatalf("rollback must restore the retired release as the active projection: %+v", active)
	}
}
