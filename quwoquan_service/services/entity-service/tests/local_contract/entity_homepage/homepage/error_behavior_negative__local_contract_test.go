// spec_ref: specs/feature-tree/object-homepage-network/spec.md#dom-002
//
// entity homepage 错误行为负例：经真实 HTTP adapter（NewHandler + Routes）
// 与生产内 memory store 触发 errors.yaml 声明的错误码，断言 wire 响应
// code 与 http_status 与契约一致。
package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	httpadapter "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/adapters/inbound/http"
	application "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	homepagepersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence"
)

func homepageNegativeHandler(t *testing.T) http.Handler {
	t.Helper()
	store, err := homepagepersistence.NewMemoryHomepageStore()
	if err != nil {
		t.Fatalf("build memory homepage store: %v", err)
	}
	service := application.NewHomepageServiceWithStore(context.Background(), store)
	return httpadapter.NewHandler(service).Routes()
}

func homepageWireError(t *testing.T, recorder *httptest.ResponseRecorder) string {
	t.Helper()
	var body struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode error body %q: %v", recorder.Body.String(), err)
	}
	return body.Code
}

func TestHomepageGetUnknownIDEmitsNotFound(t *testing.T) {
	t.Parallel()
	handler := homepageNegativeHandler(t)

	recorder := httptest.NewRecorder()
	handler.ServeHTTP(
		recorder,
		httptest.NewRequest(http.MethodGet, "/homepages/hp_missing_negative", nil),
	)

	if recorder.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404 (body=%s)", recorder.Code, recorder.Body.String())
	}
	if code := homepageWireError(t, recorder); code != "ENTITY.USER.homepage_not_found" {
		t.Fatalf("code = %s, want ENTITY.USER.homepage_not_found", code)
	}
}

func TestHomepageSuggestMalformedBodyEmitsInvalidArgument(t *testing.T) {
	t.Parallel()
	handler := homepageNegativeHandler(t)

	recorder := httptest.NewRecorder()
	handler.ServeHTTP(
		recorder,
		httptest.NewRequest(
			http.MethodPost, "/homepages/candidates/suggest",
			strings.NewReader("{malformed"),
		),
	)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400 (body=%s)", recorder.Code, recorder.Body.String())
	}
	if code := homepageWireError(t, recorder); code != "ENTITY.USER.invalid_argument" {
		t.Fatalf("code = %s, want ENTITY.USER.invalid_argument", code)
	}
}

func TestHomepageSuggestUnknownTypeEmitsInvalidHomepageType(t *testing.T) {
	t.Parallel()
	handler := homepageNegativeHandler(t)

	recorder := httptest.NewRecorder()
	handler.ServeHTTP(
		recorder,
		httptest.NewRequest(
			http.MethodPost, "/homepages/candidates/suggest",
			strings.NewReader(`{
				"homepageType": "not_a_type",
				"title": "负例主页",
				"city": "成都"
			}`),
		),
	)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400 (body=%s)", recorder.Code, recorder.Body.String())
	}
	if code := homepageWireError(t, recorder); code != "ENTITY.USER.invalid_homepage_type" {
		t.Fatalf("code = %s, want ENTITY.USER.invalid_homepage_type", code)
	}
}
