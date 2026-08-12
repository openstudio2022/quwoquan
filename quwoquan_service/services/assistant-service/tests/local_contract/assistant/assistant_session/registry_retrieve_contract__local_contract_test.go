package local_contract

import (
	"context"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	"strings"
	"testing"
)

func TestRetrieveToolsRequireCanonicalQueryWithoutCompatSelectors(t *testing.T) {
	registry := assistantSessionRegistryRetrieveContractRetrievalContractTestRegistry()
	appSearch, ok := registry.Metadata("app_search")
	if !ok {
		t.Fatal(`tool "app_search" not registered`)
	}
	if !assistantSessionRegistryRetrieveContractContainsString(appSearch.RequiredInputKeys(), "query") {
		t.Fatalf("app_search required inputs=%#v, want query", appSearch.RequiredInputKeys())
	}
	for _, forbidden := range []string{"mode", "strategy", "type", "relation", "targets", "terms"} {
		if assistantSessionRegistryRetrieveContractContainsString(appSearch.RequiredInputKeys(), forbidden) {
			t.Fatalf("tool %q must not require compat key %q", appSearch.ToolName, forbidden)
		}
	}
	webSearch, ok := registry.Metadata("web_search")
	if !ok {
		t.Fatal(`tool "web_search" not registered`)
	}
	if !assistantSessionRegistryRetrieveContractContainsString(webSearch.RequiredInputKeys(), "query") {
		t.Fatalf("web_search required inputs=%#v, want query", webSearch.RequiredInputKeys())
	}
	for _, forbidden := range []string{"mode", "type", "relation"} {
		if strings.Contains(webSearch.Description, "\""+forbidden+"\"") {
			t.Fatalf("tool %q description should not promote %q", webSearch.ToolName, forbidden)
		}
	}
}

func TestAppSearchReturnsFrozenPlanBucketsWithoutOwnerInternals(t *testing.T) {
	registry := assistantSessionRegistryRetrieveContractRetrievalContractTestRegistry()
	result, err := registry.Execute(context.Background(), Request{
		ToolName: "app_search",
		Input:    map[string]any{"query": "四川 露营"},
	})
	if err != nil {
		t.Fatalf("app_search err=%v", err)
	}
	buckets, ok := result.Output["resultBuckets"].([]any)
	if !ok || len(buckets) != 1 {
		t.Fatalf("expected one planned result bucket, got %#v", result.Output["resultBuckets"])
	}
	bucket, ok := buckets[0].(map[string]any)
	if !ok {
		t.Fatalf("result bucket type=%T, want object", buckets[0])
	}
	hits, ok := bucket["hits"].([]any)
	if !ok || len(hits) != 1 {
		t.Fatalf("result bucket hits=%#v", bucket["hits"])
	}
	hit, ok := hits[0].(map[string]any)
	if !ok || hit["objectRef"] != "opaque:test:post" {
		t.Fatalf("owner hit must expose opaque objectRef, got %#v", hits[0])
	}
	for _, forbidden := range []string{"objectId", "score", "provider", "index", "rankingFeatures"} {
		if _, leaked := hit[forbidden]; leaked {
			t.Fatalf("retrieve hit must not expose %q: %#v", forbidden, hit)
		}
	}
	for _, forbidden := range []string{"results", "provider"} {
		if _, exposed := result.Output[forbidden]; exposed {
			t.Fatalf("app_search output must not expose legacy %q: %#v", forbidden, result.Output)
		}
	}
	plan, ok := result.Output["retrievalPlan"].(map[string]any)
	if !ok || plan["digest"] == "" {
		t.Fatalf("retrievalPlan=%#v, want frozen digest", result.Output["retrievalPlan"])
	}
}

func TestSearchToolQueryCanonicalInput(t *testing.T) {
	registry := assistantSessionRegistryRetrieveContractRetrievalContractTestRegistry()
	result, err := registry.Execute(context.Background(), Request{
		ToolName: "web_search",
		Input:    map[string]any{"query": "四川 露营"},
	})
	if err != nil {
		t.Fatalf("web_search err=%v", err)
	}
	if _, exposed := result.Output["provider"]; exposed {
		t.Fatalf("web_search must not expose adapter provider: %#v", result.Output)
	}
}

func assistantSessionRegistryRetrieveContractRetrievalContractTestRegistry() Registry {
	registry := BaseRegistry()
	appSearchMetadata := AppSearchMetadata()
	registry.Register(appSearchMetadata, func(_ context.Context, request Request) (Result, error) {
		query, _ := request.Input["query"].(string)
		return Result{Output: map[string]any{
			"summary": "typed test result",
			"resultBuckets": []any{map[string]any{
				"dimension": "primary",
				"query":     query,
				"hits": []any{map[string]any{
					"objectRef":  "opaque:test:post",
					"objectType": "content.post",
					"title":      "typed test result",
				}},
			}},
			"citations":          []any{},
			"emergedTagRefs":     []string{},
			"provenance":         map[string]any{"operation": "search.search_index_view.Search"},
			"retrievalPlan":      map[string]any{"digest": "sha256:test_frozen_plan"},
			"evidenceAssessment": acceptedEvidenceAssessment("test_app_search_stub"),
		}}, nil
	})
	registry.Register(WebSearchMetadata(), func(_ context.Context, _ Request) (Result, error) {
		return Result{Output: map[string]any{
			"summary":            "web test result",
			"references":         []map[string]any{},
			"reliable":           true,
			"evidenceAssessment": acceptedEvidenceAssessment("test_web_search_stub"),
		}}, nil
	})
	return registry
}

func assistantSessionRegistryRetrieveContractContainsString(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}
