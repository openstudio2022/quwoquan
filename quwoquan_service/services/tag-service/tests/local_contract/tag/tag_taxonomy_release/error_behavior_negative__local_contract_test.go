// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-002
//
// tag_taxonomy_release 错误行为负例：经真实 HTTP adapter
// （NewTaxonomyReleaseHandler）触发 errors.yaml 声明的每个错误码，断言
// wire 响应 code 与 http_status。typed double store/readiness 注入
// 各失败形态。
package tag_taxonomy_release

import (
	"context"
	"encoding/json"
	"errors"
	nethttp "net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	releasehttp "quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/adapters/inbound/http"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/application/taxonomyrelease"
	releasemodel "quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/domain/taxonomyrelease/model"
)

type stubReleaseStore struct {
	loadRelease *releasemodel.Release
	loadErr     error
	active      *releasemodel.Release
	insertErr   error
	activateErr error
}

func (s stubReleaseStore) ActiveReleaseID(context.Context) (string, bool, error) {
	if s.active != nil {
		return s.active.ReleaseID, true, nil
	}
	return "", false, nil
}

func (s stubReleaseStore) FindActive(context.Context) (releasemodel.Release, bool, error) {
	if s.active != nil {
		return *s.active, true, nil
	}
	return releasemodel.Release{}, false, nil
}

func (s stubReleaseStore) Load(context.Context, string) (releasemodel.Release, bool, error) {
	if s.loadErr != nil {
		return releasemodel.Release{}, false, s.loadErr
	}
	if s.loadRelease != nil {
		return *s.loadRelease, true, nil
	}
	return releasemodel.Release{}, false, nil
}

func (s stubReleaseStore) InsertStaged(context.Context, releasemodel.Release) error {
	return s.insertErr
}

func (s stubReleaseStore) ActivateExclusive(
	context.Context, releasemodel.Release, *releasemodel.Release,
) error {
	return s.activateErr
}

type stubSnapshotReadiness struct {
	complete bool
	err      error
}

func (s stubSnapshotReadiness) HasCompleteSnapshot(context.Context, string, int) (bool, error) {
	return s.complete, s.err
}

func stagedRelease(t *testing.T, releaseID, digest string) *releasemodel.Release {
	t.Helper()
	release, err := releasemodel.NewStaged(
		releaseID, "qwq_data", digest, releasemodel.ReleaseKindContent, 10,
		time.Now().UTC(),
	)
	if err != nil {
		t.Fatalf("build staged release: %v", err)
	}
	return &release
}

func releaseNegativeHandler(
	t *testing.T, store stubReleaseStore, readiness stubSnapshotReadiness,
) nethttp.Handler {
	t.Helper()
	facade, err := taxonomyrelease.NewFacade(store, readiness)
	if err != nil {
		t.Fatalf("build taxonomy release facade: %v", err)
	}
	mux := nethttp.NewServeMux()
	releasehttp.NewTaxonomyReleaseHandler(facade).Register(mux)
	return mux
}

func releaseWireError(t *testing.T, recorder *httptest.ResponseRecorder) string {
	t.Helper()
	var body struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode error body %q: %v", recorder.Body.String(), err)
	}
	return body.Code
}

func activateRequest(releaseID string) *nethttp.Request {
	return httptest.NewRequest(
		nethttp.MethodPost,
		"/internal/tag/taxonomy-releases/"+releaseID+":activate",
		nil,
	)
}

func assertReleaseError(
	t *testing.T,
	handler nethttp.Handler,
	request *nethttp.Request,
	wantStatus int,
	wantCode string,
) {
	t.Helper()
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != wantStatus {
		t.Fatalf(
			"status = %d, want %d (body=%s)",
			recorder.Code, wantStatus, recorder.Body.String(),
		)
	}
	if code := releaseWireError(t, recorder); code != wantCode {
		t.Fatalf("code = %s, want %s", code, wantCode)
	}
}

func TestReleaseStageMalformedBodyEmitsInvalidArgument(t *testing.T) {
	t.Parallel()
	handler := releaseNegativeHandler(t, stubReleaseStore{}, stubSnapshotReadiness{complete: true})
	request := httptest.NewRequest(
		nethttp.MethodPost, "/internal/tag/taxonomy-releases",
		strings.NewReader("{malformed"),
	)
	assertReleaseError(
		t, handler, request,
		nethttp.StatusBadRequest, "TAG.USER.release_invalid_argument",
	)
}

func TestReleaseActivateUnknownIDEmitsNotFound(t *testing.T) {
	t.Parallel()
	handler := releaseNegativeHandler(t, stubReleaseStore{}, stubSnapshotReadiness{complete: true})
	assertReleaseError(
		t, handler, activateRequest("release-missing"),
		nethttp.StatusNotFound, "TAG.USER.release_not_found",
	)
}

func TestReleaseActivateCorruptedStatusEmitsInvalidTransition(t *testing.T) {
	t.Parallel()
	corrupted := stagedRelease(t, "release-corrupted", "sha256:"+strings.Repeat("a", 64))
	corrupted.Status = releasemodel.Status("corrupted")
	handler := releaseNegativeHandler(
		t, stubReleaseStore{loadRelease: corrupted}, stubSnapshotReadiness{complete: true},
	)
	assertReleaseError(
		t, handler, activateRequest("release-corrupted"),
		nethttp.StatusConflict, "TAG.USER.release_invalid_transition",
	)
}

func TestReleaseActivateIncompleteSnapshotEmitsSnapshotIncomplete(t *testing.T) {
	t.Parallel()
	handler := releaseNegativeHandler(
		t,
		stubReleaseStore{loadRelease: stagedRelease(t, "release-staged", "sha256:"+strings.Repeat("b", 64))},
		stubSnapshotReadiness{complete: false},
	)
	assertReleaseError(
		t, handler, activateRequest("release-staged"),
		nethttp.StatusConflict, "TAG.USER.release_snapshot_incomplete",
	)
}

func TestReleaseActivateCASExhaustionEmitsVersionConflict(t *testing.T) {
	t.Parallel()
	handler := releaseNegativeHandler(
		t,
		stubReleaseStore{
			loadRelease: stagedRelease(t, "release-cas", "sha256:"+strings.Repeat("c", 64)),
			activateErr: releasemodel.ErrVersionConflict,
		},
		stubSnapshotReadiness{complete: true},
	)
	assertReleaseError(
		t, handler, activateRequest("release-cas"),
		nethttp.StatusConflict, "TAG.USER.release_version_conflict",
	)
}

func TestReleaseStageDriftedReplayEmitsIdempotencyConflict(t *testing.T) {
	t.Parallel()
	existing := stagedRelease(t, "release-replay", "sha256:"+strings.Repeat("d", 64))
	handler := releaseNegativeHandler(
		t, stubReleaseStore{loadRelease: existing}, stubSnapshotReadiness{complete: true},
	)
	request := httptest.NewRequest(
		nethttp.MethodPost, "/internal/tag/taxonomy-releases",
		strings.NewReader(`{
			"releaseId": "release-replay",
			"sourceOwner": "qwq_data",
			"canonicalDigest": "sha256:`+strings.Repeat("e", 64)+`",
			"releaseKind": "content",
			"nodeCount": 10
		}`),
	)
	assertReleaseError(
		t, handler, request,
		nethttp.StatusConflict, "TAG.USER.release_idempotency_conflict",
	)
}

func TestReleaseActivateStorageFailureEmitsStorageFailed(t *testing.T) {
	t.Parallel()
	handler := releaseNegativeHandler(
		t,
		stubReleaseStore{loadErr: errors.New("injected release storage failure")},
		stubSnapshotReadiness{complete: true},
	)
	assertReleaseError(
		t, handler, activateRequest("release-any"),
		nethttp.StatusInternalServerError, "TAG.SYSTEM.release_storage_failed",
	)
}
