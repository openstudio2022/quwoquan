// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
//
// SearchIndexView 声明错误码的负例断言：经真实 HTTP handler 驱动检索模式
// 越权与后端不可用路径，以字面 wire code 锁定端云契约。
package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	rtsearch "quwoquan_service/runtime/search"
	searchhttp "quwoquan_service/services/search-service/internal/search/search_index_view/adapters/inbound/http"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

type errSemFailingRecallBackend struct{}

func (errSemFailingRecallBackend) Recall(
	context.Context, rtsearch.RetrievePlan,
) ([]rtsearch.RecallCandidate, error) {
	return nil, errors.New("elasticsearch cluster unreachable")
}

func (errSemFailingRecallBackend) Name() string { return "errsem-failing-backend" }

func newErrSemSearchHandler(t *testing.T, backend rtsearch.RecallBackend) http.Handler {
	t.Helper()
	experiments, err := application.NewExperiments(&assignmentPublisherSpy{})
	if err != nil {
		t.Fatalf("new experiments: %v", err)
	}
	if err := experiments.ApplyPolicy(searchPolicy("running", 5000, 5000)); err != nil {
		t.Fatalf("apply search policy: %v", err)
	}
	return searchhttp.NewHandler(
		application.NewSearchService(backend),
		application.NewRankingDecorator(nil, experiments, 0, nil),
		nil,
	).Routes()
}

func postErrSemSearch(t *testing.T, handler http.Handler, body string) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(
		http.MethodPost, "/search", bytes.NewBufferString(body),
	)
	request.Header.Set(searchhttp.SearchSessionIDHeader, "search-errsem-session")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}

func requireErrSemResponseCode(
	t *testing.T,
	response *httptest.ResponseRecorder,
	wantStatus int,
	wantCode string,
) {
	t.Helper()
	if response.Code != wantStatus {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	var envelope struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("decode error envelope: %v body=%s", err, response.Body.String())
	}
	if envelope.Code != wantCode {
		t.Fatalf("expected code %s, got %s", wantCode, envelope.Code)
	}
}

func TestSearchRetrievalModeWithoutAssistantCallerEmitsForbidden(t *testing.T) {
	handler := newErrSemSearchHandler(t, rtsearch.NewSliceBackend(nil))

	response := postErrSemSearch(
		t, handler, `{"query":"大理","mode":"retrieval"}`,
	)
	requireErrSemResponseCode(
		t, response, http.StatusForbidden, "SEARCH.USER.forbidden",
	)
}

func TestSearchWithFailingBackendEmitsMiddlewareUnavailable(t *testing.T) {
	handler := newErrSemSearchHandler(t, errSemFailingRecallBackend{})

	response := postErrSemSearch(
		t, handler, `{"query":"大理","objectTypes":["content.post"],"contentTypes":["article"]}`,
	)
	requireErrSemResponseCode(
		t, response, http.StatusServiceUnavailable, "SEARCH.MIDDLEWARE.unavailable",
	)
}
