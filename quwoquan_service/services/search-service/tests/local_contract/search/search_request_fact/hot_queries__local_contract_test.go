// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-004
// readiness_case: list-hot-queries-local
package local_contract

import (
	"context"
	"encoding/json"
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

type readinessTermHeatReader struct{}

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
