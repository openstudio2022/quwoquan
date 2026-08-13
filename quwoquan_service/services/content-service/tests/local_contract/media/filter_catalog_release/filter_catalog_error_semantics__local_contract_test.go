// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
//
// FilterCatalogRelease 声明错误码的负例断言：每个用例真实驱动 HTTP handler
// 的 domain sentinel 映射到 generated AppError 工厂的 emit 点，并以字面
// wire code 锁定端云契约。
package local_contract

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	filtercataloghttp "quwoquan_service/services/content-service/internal/media/filter_catalog_release/adapters/inbound/http"
	filtercatalogapp "quwoquan_service/services/content-service/internal/media/filter_catalog_release/application"
	filtercatalogmodel "quwoquan_service/services/content-service/internal/media/filter_catalog_release/domain/model"
)

// failingActiveCatalogReader 只在读取活跃目录时注入基础设施故障，
// 驱动 application 层 ErrStorageUnavailable 包装与 handler 兜底映射。
type failingActiveCatalogReader struct {
	err error
}

func (reader failingActiveCatalogReader) GetActive(
	context.Context,
) (*filtercatalogmodel.FilterCatalogRelease, bool, error) {
	return nil, false, reader.err
}

func requireFilterCatalogErrorResponse(
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

func TestActivateUnknownReleaseEmitsFilterCatalogReleaseNotFound(t *testing.T) {
	store := &recordingFilterCatalogStore{}
	service, err := filtercatalogapp.NewService(store, store)
	if err != nil {
		t.Fatal(err)
	}
	handler := filtercataloghttp.NewHandler(filtercatalogapp.BindFacades(service))
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/content/filter-catalog-releases/filter-release-absent",
		nil,
	)
	request.SetPathValue("releaseId", "filter-release-absent")
	request.Header.Set("Idempotency-Key", "err-sem-activate-absent")
	recorder := httptest.NewRecorder()
	handler.Activate(recorder, request)
	requireFilterCatalogErrorResponse(
		t,
		recorder,
		http.StatusNotFound,
		"CONTENT.USER.filter_catalog_release_not_found",
	)
}

func TestGetActiveWithFailingStoreEmitsFilterCatalogStorageUnavailable(t *testing.T) {
	store := &recordingFilterCatalogStore{}
	service, err := filtercatalogapp.NewService(store, failingActiveCatalogReader{
		err: errors.New("filter catalog store unreachable"),
	})
	if err != nil {
		t.Fatal(err)
	}
	handler := filtercataloghttp.NewHandler(filtercatalogapp.BindFacades(service))
	request := httptest.NewRequest(http.MethodGet, "/content/filter-catalog", nil)
	recorder := httptest.NewRecorder()
	handler.GetActive(recorder, request)
	requireFilterCatalogErrorResponse(
		t,
		recorder,
		http.StatusServiceUnavailable,
		"CONTENT.SYSTEM.filter_catalog_storage_unavailable",
	)
}
