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
}

func (store *recordingFilterCatalogStore) Load(
	_ context.Context,
	_ string,
) (*filtercatalogmodel.FilterCatalogRelease, bool, error) {
	return nil, false, nil
}

func (store *recordingFilterCatalogStore) Stage(
	_ context.Context,
	commit filtercatalogports.StageCommit,
) (filtercatalogports.CommandResult, error) {
	store.stageCommits = append(store.stageCommits, commit)
	return filtercatalogports.CommandResult{
		Release: commit.Release,
		Changed: true,
	}, nil
}

func (store *recordingFilterCatalogStore) Activate(
	_ context.Context,
	_ filtercatalogports.TransitionCommit,
) (filtercatalogports.CommandResult, error) {
	return filtercatalogports.CommandResult{}, filtercatalogmodel.ErrReleaseNotFound
}

func (store *recordingFilterCatalogStore) Rollback(
	_ context.Context,
	_ filtercatalogports.TransitionCommit,
) (filtercatalogports.CommandResult, error) {
	return filtercatalogports.CommandResult{}, filtercatalogmodel.ErrReleaseNotFound
}

func (store *recordingFilterCatalogStore) GetActive(
	_ context.Context,
) (*filtercatalogmodel.FilterCatalogRelease, bool, error) {
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
