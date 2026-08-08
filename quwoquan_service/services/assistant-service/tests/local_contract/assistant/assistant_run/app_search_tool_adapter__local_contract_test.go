// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-003
package assistant_run_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
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
		_ = json.NewEncoder(writer).Encode(rtsearch.RetrieveResponse{
			Hits: []rtsearch.RetrieveHit{{
				Target:      rtsearch.TargetArticle,
				ObjectType:  rtsearch.ObjectTypeContentPost,
				ObjectID:    "post-1",
				Title:       "西湖行程",
				MatchedTags: []string{"Topic/旅行"},
				Payload: map[string]any{
					"categoryId":  "旅行",
					"subCategory": "周末游",
				},
			}},
			Citations: []rtsearch.Citation{{
				CitationID: "citation-1",
				ObjectType: "content.post",
				ObjectID:   "post-1",
				Title:      "西湖行程",
			}},
			Provenance: rtsearch.Provenance{
				Provider:    "search-service",
				GeneratedAt: time.Unix(1_700_000_000, 0).UTC(),
			},
		})
	}))
	defer server.Close()

	client, err := searchclient.New(server.URL, server.Client())
	if err != nil {
		t.Fatalf("new search client: %v", err)
	}
	result, err := client.Handler()(t.Context(), toolpkg.Request{Input: map[string]any{
		"query": "西湖行程",
	}})
	if err != nil {
		t.Fatalf("execute app_search adapter: %v", err)
	}
	wire := <-received
	if len(wire) != 4 || wire["query"] != "西湖行程" ||
		wire["mode"] != "result" || wire["limit"] != float64(10) {
		t.Fatalf("search request used a non-canonical input path: %#v", wire)
	}
	// objectTypes is part of the canonical input: app_search may only ask for the
	// types the object contracts open to 小趣.
	requested, ok := wire["objectTypes"].([]any)
	if !ok || len(requested) != len(searchclient.AssistantReadableObjectTypes()) {
		t.Fatalf("objectTypes=%#v", wire["objectTypes"])
	}
	for index, allowed := range searchclient.AssistantReadableObjectTypes() {
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
	if !ok || len(emergedTagRefs) != 2 ||
		emergedTagRefs[0] != "Topic/旅行" ||
		emergedTagRefs[1] != "Topic/周末游" {
		t.Fatalf("emergedTagRefs=%#v", result.Output["emergedTagRefs"])
	}
}
