// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-002
// readiness_case: search-local
package local_contract

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	rtsearch "quwoquan_service/runtime/search"
	searchhttp "quwoquan_service/services/search-service/internal/search/search_index_view/adapters/inbound/http"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

func TestSearchHTTPRunsCanonicalQueryFacade(t *testing.T) {
	backend := rtsearch.NewSliceBackend([]rtsearch.Document{{
		ObjectType: rtsearch.ObjectTypeContentPost,
		ObjectID:   "post-search-local",
		Title:      "大理古城漫步",
		Visibility: "public",
	}})
	experiments, err := application.NewExperiments(&assignmentPublisherSpy{})
	if err != nil {
		t.Fatalf("new experiments: %v", err)
	}
	if err := experiments.ApplyPolicy(searchPolicy("running", 5000, 5000)); err != nil {
		t.Fatalf("apply search policy: %v", err)
	}
	handler := searchhttp.NewHandler(
		application.NewSearchService(backend),
		application.NewRankingDecorator(nil, experiments, 0, nil),
		nil,
	).Routes()

	request := httptest.NewRequest(
		http.MethodPost,
		"/search",
		bytes.NewBufferString(`{"query":"大理","objectTypes":["article"]}`),
	)
	request.Header.Set(searchhttp.SearchSessionIDHeader, "search-local-session")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("search status=%d body=%s", response.Code, response.Body.String())
	}
	var body struct {
		Hits []struct {
			ObjectID string `json:"objectId"`
		} `json:"hits"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode search response: %v", err)
	}
	if len(body.Hits) != 1 || body.Hits[0].ObjectID != "post-search-local" {
		t.Fatalf("canonical search response=%s", response.Body.String())
	}
}
