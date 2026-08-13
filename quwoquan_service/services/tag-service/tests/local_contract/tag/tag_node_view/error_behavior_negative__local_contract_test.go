// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-002
//
// tag_node_view 错误行为负例：经真实 HTTP adapter（NewTagHandler + Routes）
// 触发 errors.yaml 声明的每个错误码，断言 wire 响应的 code 与 http_status
// 与契约一致。typed double reader 注入依赖失败驱动 SYSTEM 码。
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	httpadapter "quwoquan_service/services/tag-service/internal/tag/tag_node_view/adapters/inbound/http"
	application "quwoquan_service/services/tag-service/internal/tag/tag_node_view/application"
	model "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/model"
	ports "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/ports"
)

// failingTagNodeReader 注入存储读失败，驱动 TAG.SYSTEM.storage_read_failed。
type failingTagNodeReader struct{}

var errTagStorageDown = errors.New("injected tag storage failure")

func (failingTagNodeReader) FindByReleaseAndTagRef(context.Context, string, string) (*model.TagNode, error) {
	return nil, errTagStorageDown
}

func (failingTagNodeReader) ListChildrenInRelease(context.Context, string, string, int64) ([]model.TagNode, error) {
	return nil, errTagStorageDown
}

func (failingTagNodeReader) CountUsableChildrenInRelease(context.Context, string, string) (int64, error) {
	return 0, errTagStorageDown
}

func (failingTagNodeReader) ListDimensionsInRelease(context.Context, string) ([]model.TagNode, error) {
	return nil, errTagStorageDown
}

func (failingTagNodeReader) ListAllInRelease(context.Context, string) ([]model.TagNode, error) {
	return nil, errTagStorageDown
}

func (failingTagNodeReader) IsUsableLeaf(context.Context, string, string) (bool, error) {
	return false, errTagStorageDown
}

func tagNegativeHandler(t *testing.T, nodeReader ports.TagNodeReader) http.Handler {
	t.Helper()
	service := application.NewTagService(
		nodeReader,
		migratedObjectTagIndexReader{},
		migratedActiveReleaseReader{releaseID: "release-current", found: true},
	)
	return httpadapter.NewTagHandler(service).Routes()
}

func wireErrorOf(t *testing.T, recorder *httptest.ResponseRecorder) string {
	t.Helper()
	var body struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode error body %q: %v", recorder.Body.String(), err)
	}
	return body.Code
}

func TestTagResolveWithoutTagRefEmitsInvalidArgument(t *testing.T) {
	t.Parallel()
	handler := tagNegativeHandler(t, migratedTagNodeReader{nodes: map[string]*model.TagNode{}})

	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/tag/resolve", nil))

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", recorder.Code)
	}
	if code := wireErrorOf(t, recorder); code != "TAG.USER.invalid_argument" {
		t.Fatalf("code = %s, want TAG.USER.invalid_argument", code)
	}
}

func TestTagResolveUnknownTagEmitsNotFound(t *testing.T) {
	t.Parallel()
	handler := tagNegativeHandler(t, migratedTagNodeReader{nodes: map[string]*model.TagNode{}})

	recorder := httptest.NewRecorder()
	handler.ServeHTTP(
		recorder,
		httptest.NewRequest(http.MethodGet, "/tag/resolve?tagRef=Topic%2F不存在", nil),
	)

	if recorder.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404", recorder.Code)
	}
	if code := wireErrorOf(t, recorder); code != "TAG.USER.tag_not_found" {
		t.Fatalf("code = %s, want TAG.USER.tag_not_found", code)
	}
}

func TestTagResolveStorageFailureEmitsStorageReadFailed(t *testing.T) {
	t.Parallel()
	handler := tagNegativeHandler(t, failingTagNodeReader{})

	recorder := httptest.NewRecorder()
	handler.ServeHTTP(
		recorder,
		httptest.NewRequest(http.MethodGet, "/tag/resolve?tagRef=Topic%2F旅行", nil),
	)

	if recorder.Code != http.StatusInternalServerError {
		t.Fatalf("status = %d, want 500", recorder.Code)
	}
	if code := wireErrorOf(t, recorder); code != "TAG.SYSTEM.storage_read_failed" {
		t.Fatalf("code = %s, want TAG.SYSTEM.storage_read_failed", code)
	}
}
