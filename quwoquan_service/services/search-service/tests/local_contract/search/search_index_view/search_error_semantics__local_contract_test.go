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
	"os"
	"path/filepath"
	"strconv"
	"testing"

	"gopkg.in/yaml.v3"
	rterrors "quwoquan_service/runtime/errors"
	rtgov "quwoquan_service/runtime/governance"
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

type searchUnavailableContractRow struct {
	Code                 string `yaml:"code"`
	HTTPStatus           int    `yaml:"http_status"`
	RecoveryAction       string `yaml:"recovery_action"`
	RecoveryAfterSeconds int    `yaml:"recovery_after_seconds"`
	DisruptionLevel      string `yaml:"disruption_level"`
}

func canonicalSearchUnavailable(t *testing.T) searchUnavailableContractRow {
	t.Helper()
	content, err := os.ReadFile(filepath.Join(
		searchServiceRoot(t),
		"contracts", "search", "search_index_view", "errors.yaml",
	))
	if err != nil {
		t.Fatalf("read Search errors contract: %v", err)
	}
	var document struct {
		Errors []searchUnavailableContractRow `yaml:"errors"`
	}
	if err := yaml.Unmarshal(content, &document); err != nil {
		t.Fatalf("decode Search errors contract: %v", err)
	}
	for _, row := range document.Errors {
		if row.Code == "SEARCH.MIDDLEWARE.unavailable" {
			return row
		}
	}
	t.Fatal("SEARCH.MIDDLEWARE.unavailable is absent from canonical errors")
	return searchUnavailableContractRow{}
}

func requireSearchUnavailableWire(
	t *testing.T,
	response *httptest.ResponseRecorder,
) {
	t.Helper()
	want := canonicalSearchUnavailable(t)
	if response.Code != want.HTTPStatus {
		t.Fatalf("status=%d want=%d body=%s", response.Code, want.HTTPStatus, response.Body.String())
	}
	var envelope rterrors.ErrorResponse
	if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("decode Search error envelope: %v body=%s", err, response.Body.String())
	}
	if envelope.Code != want.Code ||
		envelope.Recovery.Action != want.RecoveryAction ||
		envelope.Recovery.AfterSeconds != want.RecoveryAfterSeconds ||
		envelope.Recovery.DisruptionLevel != want.DisruptionLevel {
		t.Fatalf("wire=%+v want=%+v", envelope, want)
	}
	headerSeconds, err := strconv.Atoi(response.Header().Get("Retry-After"))
	if err != nil || headerSeconds != want.RecoveryAfterSeconds {
		t.Fatalf(
			"Retry-After=%q want=%d: %v",
			response.Header().Get("Retry-After"),
			want.RecoveryAfterSeconds,
			err,
		)
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
	requireSearchUnavailableWire(t, response)
}

func TestSearchInflightShedUsesCanonicalUnavailableWire(t *testing.T) {
	limiter := rtgov.NewInflightLimiter(1)
	if !limiter.Acquire() {
		t.Fatal("reserve inflight limiter slot")
	}
	defer limiter.Release()
	handler := searchhttp.MaxInflightMiddleware(
		limiter,
		nil,
	)(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("shed request must not reach downstream handler")
	}))

	response := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodPost, "/search", nil)
	handler.ServeHTTP(response, request)

	requireSearchUnavailableWire(t, response)
}
