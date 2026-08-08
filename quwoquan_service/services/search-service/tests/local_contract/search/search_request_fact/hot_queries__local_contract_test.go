// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-004
// readiness_case: list-hot-queries-local
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	httpadapter "quwoquan_service/services/search-service/internal/search/search_request_fact/adapters/inbound/http"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/application/queryheat"
)

func TestListHotQueriesUsesTheObjectOwnedReaderAndBoundedHTTPWire(t *testing.T) {
	handler := httpadapter.NewHandler(readinessTermHeatReader{}).Routes()
	request := httptest.NewRequest(http.MethodGet, "/search/hot-queries?limit=2", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	var body struct {
		Items []struct {
			Query     string  `json:"query"`
			Relevance float64 `json:"relevance"`
		} `json:"items"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(body.Items) != 2 || body.Items[0].Query != "成都旅行" ||
		body.Items[0].Relevance <= body.Items[1].Relevance {
		t.Fatalf("hot query response = %+v", body.Items)
	}
}

func TestListHotQueriesEmitsObjectOwnedErrors(t *testing.T) {
	for name, testCase := range map[string]struct {
		handler    http.Handler
		target     string
		wantStatus int
		wantCode   string
	}{
		"invalid limit": {
			handler: httpadapter.NewHandler(readinessTermHeatReader{}).Routes(),
			target:  "/search/hot-queries?limit=21", wantStatus: http.StatusBadRequest,
			wantCode: "SEARCH.USER.hot_query_invalid_argument",
		},
		"reader unavailable": {
			handler: httpadapter.NewHandler(failingTermHeatReader{}).Routes(),
			target:  "/search/hot-queries", wantStatus: http.StatusServiceUnavailable,
			wantCode: "SEARCH.MIDDLEWARE.hot_query_unavailable",
		},
	} {
		t.Run(name, func(t *testing.T) {
			request := httptest.NewRequest(http.MethodGet, testCase.target, nil)
			response := httptest.NewRecorder()
			testCase.handler.ServeHTTP(response, request)
			if response.Code != testCase.wantStatus {
				t.Fatalf("status=%d want=%d body=%s", response.Code, testCase.wantStatus, response.Body.String())
			}
			var body struct {
				Code string `json:"code"`
			}
			if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
				t.Fatalf("decode response: %v", err)
			}
			if body.Code != testCase.wantCode {
				t.Fatalf("code=%q want=%q", body.Code, testCase.wantCode)
			}
		})
	}
}

type readinessTermHeatReader struct{}

type failingTermHeatReader struct{}

func (failingTermHeatReader) RelatedTerms(
	context.Context,
	string,
	int,
) ([]queryheat.TermHeat, error) {
	return nil, errors.New("term heat unavailable")
}

func (readinessTermHeatReader) RelatedTerms(
	context.Context,
	string,
	int,
) ([]queryheat.TermHeat, error) {
	return []queryheat.TermHeat{
		{NormalizedTerm: "成都旅行", Relevance: 9},
		{NormalizedTerm: "露营", Relevance: 3},
	}, nil
}
