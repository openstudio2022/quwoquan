// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
//
// MediaImageReprocessRun HTTP handler 声明错误码的负例断言：每个用例真实
// 驱动 handler 的 domain sentinel 映射到 generated AppError 工厂的 emit 点，
// 并以字面 wire code 锁定端云契约。
package http_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/commandmeta"
	reprocesshttp "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/adapters/inbound/http"
	reprocessapp "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/application"
	reprocessmodel "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/domain/model"
	reprocessports "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/domain/ports"
	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
)

type errSemRunStore struct {
	run     *reprocessmodel.Run
	loadErr error
}

func (s *errSemRunStore) LoadMediaImageReprocessRun(
	_ context.Context,
	runID string,
) (*reprocessmodel.Run, bool, error) {
	if s.loadErr != nil {
		return nil, false, s.loadErr
	}
	return s.run, s.run != nil && s.run.RunID() == runID, nil
}

func (s *errSemRunStore) FindMediaImageReprocessRunReceipt(
	context.Context, string, string, string,
) (reprocessports.CommitResult, bool, error) {
	return reprocessports.CommitResult{}, false, nil
}

func (s *errSemRunStore) CommitMediaImageReprocessRun(
	_ context.Context,
	commit reprocessports.Commit,
) (reprocessports.CommitResult, error) {
	s.run = commit.Aggregate
	return reprocessports.CommitResult{Aggregate: commit.Aggregate}, nil
}

func (s *errSemRunStore) ListRunnableMediaImageReprocessRuns(
	context.Context, int,
) ([]*reprocessmodel.Run, error) {
	return nil, nil
}

func (s *errSemRunStore) TryAcquireMediaImageReprocessRunLease(
	context.Context, string, string, time.Time, time.Duration,
) (bool, error) {
	return true, nil
}

func (s *errSemRunStore) RenewMediaImageReprocessRunLease(
	context.Context, string, string, time.Time, time.Duration,
) (bool, error) {
	return true, nil
}

type errSemAssetReader struct{}

func (errSemAssetReader) LoadMediaAsset(
	context.Context,
	string,
) (*mediamodel.MediaAsset, bool, error) {
	return nil, false, nil
}

func newErrSemReprocessHandler(store *errSemRunStore) *reprocesshttp.Handler {
	return reprocesshttp.NewHandler(reprocessapp.NewService(store, errSemAssetReader{}))
}

func requireReprocessErrorResponse(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
	wantStatus int,
	wantCode string,
) {
	t.Helper()
	if recorder.Code != wantStatus {
		t.Fatalf(
			"status=%d want=%d body=%s",
			recorder.Code,
			wantStatus,
			recorder.Body.String(),
		)
	}
	if !strings.Contains(recorder.Body.String(), `"code":"`+wantCode+`"`) {
		t.Fatalf("body missing code %s: %s", wantCode, recorder.Body.String())
	}
}

func TestStartWithoutAssetsEmitsMediaImageReprocessInvalidArgument(t *testing.T) {
	handler := newErrSemReprocessHandler(&errSemRunStore{})
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/content/media-image-reprocess-runs",
		strings.NewReader(`{"runId":"run-err-sem","assetIds":[]}`),
	)
	recorder := httptest.NewRecorder()
	handler.Start(recorder, request)
	requireReprocessErrorResponse(
		t,
		recorder,
		http.StatusBadRequest,
		"CONTENT.USER.media_image_reprocess_invalid_argument",
	)
}

func TestGetUnknownRunEmitsMediaImageReprocessRunNotFound(t *testing.T) {
	handler := newErrSemReprocessHandler(&errSemRunStore{})
	request := httptest.NewRequest(
		http.MethodGet,
		"/internal/content/media-image-reprocess-runs/run-absent",
		nil,
	)
	request.SetPathValue("runId", "run-absent")
	recorder := httptest.NewRecorder()
	handler.Get(recorder, request)
	requireReprocessErrorResponse(
		t,
		recorder,
		http.StatusNotFound,
		"CONTENT.USER.media_image_reprocess_run_not_found",
	)
}

func TestPausePausedRunEmitsMediaImageReprocessInvalidTransition(t *testing.T) {
	now := time.Date(2026, 8, 1, 10, 0, 0, 0, time.UTC)
	run, err := reprocessmodel.Start(reprocessmodel.StartParams{
		RunID:                         "run-err-sem-paused",
		TargetDerivativePolicyVersion: 1,
		AssetIDs:                      []string{"image-err-sem"},
		Now:                           now,
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	if err := run.Pause(now.Add(time.Second)); err != nil {
		t.Fatalf("pause run: %v", err)
	}
	handler := newErrSemReprocessHandler(&errSemRunStore{run: run})
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/content/media-image-reprocess-runs/run-err-sem-paused/pause",
		nil,
	)
	request = request.WithContext(commandmeta.WithIdempotencyKey(
		request.Context(),
		"err-sem-pause-paused",
	))
	request.SetPathValue("runId", "run-err-sem-paused")
	recorder := httptest.NewRecorder()
	handler.Pause(recorder, request)
	requireReprocessErrorResponse(
		t,
		recorder,
		http.StatusConflict,
		"CONTENT.USER.media_image_reprocess_invalid_transition",
	)
}

func TestGetWithFailingStoreEmitsMediaImageReprocessStorageUnavailable(t *testing.T) {
	handler := newErrSemReprocessHandler(&errSemRunStore{
		loadErr: errors.New("reprocess run store unreachable"),
	})
	request := httptest.NewRequest(
		http.MethodGet,
		"/internal/content/media-image-reprocess-runs/run-err-sem",
		nil,
	)
	request.SetPathValue("runId", "run-err-sem")
	recorder := httptest.NewRecorder()
	handler.Get(recorder, request)
	requireReprocessErrorResponse(
		t,
		recorder,
		http.StatusServiceUnavailable,
		"CONTENT.SYSTEM.media_image_reprocess_storage_unavailable",
	)
}
