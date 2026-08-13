// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-003
package assistant_run_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/searchclient"
)

func TestAppSearchAdapterUsesOnlyCanonicalToolInputAndReturnsEvidenceAssessment(
	t *testing.T,
) {
	received := make(chan map[string]any, 1)
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		var body map[string]any
		if err := json.NewDecoder(request.Body).Decode(&body); err != nil {
			t.Errorf("decode search request: %v", err)
			writer.WriteHeader(http.StatusBadRequest)
			return
		}
		received <- body
		writer.Header().Set("Content-Type", "application/json")
		writer.Header().Set("X-Contract-Graph-SHA256", testSHA256)
		_ = json.NewEncoder(writer).Encode(map[string]any{
			"interpretedQuery": map[string]any{
				"normalized": "西湖行程", "tokens": []string{}, "variants": []string{},
				"detectedEntities": []string{}, "detectedTags": []string{}, "selectedObjectTypes": []string{"content.post"},
			},
			"hits":      []map[string]any{{"objectRef": "opaque-post-1", "objectType": "content.post", "contentType": "article", "title": "西湖行程", "snippet": ""}},
			"citations": []map[string]any{{"citationId": "citation-1", "objectRef": "opaque-post-1", "objectType": "content.post", "contentType": "article", "title": "西湖行程", "snippet": "", "url": "", "deepLink": ""}},
			"facets":    []any{}, "degradeSignals": []any{},
			"provenance": map[string]any{"source": "search_index_view", "generatedAt": time.Unix(1_700_000_000, 0).UTC()},
			"nextCursor": "",
		})
	}))
	defer server.Close()

	client, err := searchclient.New(server.URL, server.Client(), searchAuthorizationFixture{}, testSHA256)
	if err != nil {
		t.Fatalf("new search client: %v", err)
	}
	result, err := client.Handler()(t.Context(), toolpkg.Request{
		ToolName: "app_search", RunID: "run-adapter", TurnID: "turn-adapter",
		ToolCatalogDigest: testSHA256, RuntimeCandidateDigest: testSHA256,
		ContractGraphDigest: testSHA256, MaximumToolCalls: 1,
		Input: map[string]any{"query": "西湖行程"},
	})
	if err != nil {
		t.Fatalf("execute app_search adapter: %v", err)
	}
	wire := <-received
	if len(wire) != 4 || wire["query"] != "西湖行程" ||
		wire["mode"] != "retrieval" || wire["limit"] != float64(10) {
		t.Fatalf("search request used a non-canonical input path: %#v", wire)
	}
	// objectTypes is part of the canonical input: app_search may only ask for the
	// types the object contracts open to 小趣.
	requested, ok := wire["objectTypes"].([]any)
	if !ok || len(requested) != len(searchclient.SearchIndexEligibleObjectTypes()) {
		t.Fatalf("objectTypes=%#v", wire["objectTypes"])
	}
	for index, allowed := range searchclient.SearchIndexEligibleObjectTypes() {
		if requested[index] != allowed {
			t.Fatalf("objectTypes[%d]=%v want %q", index, requested[index], allowed)
		}
	}
	assessment, ok := result.Output["evidenceAssessment"].(map[string]any)
	if !ok || assessment["status"] != "accepted" ||
		assessment["evidenceSufficient"] != true ||
		assessment["replanRequired"] != false {
		t.Fatalf("evidence assessment=%#v", result.Output["evidenceAssessment"])
	}
	sourceIDs, ok := assessment["sourceIds"].([]string)
	if !ok || len(sourceIDs) != 1 || sourceIDs[0] != "citation-1" {
		t.Fatalf("sourceIds=%#v", assessment["sourceIds"])
	}
	emergedTagRefs, ok := result.Output["emergedTagRefs"].([]string)
	if !ok || len(emergedTagRefs) != 0 {
		t.Fatalf("emergedTagRefs=%#v", result.Output["emergedTagRefs"])
	}
}
