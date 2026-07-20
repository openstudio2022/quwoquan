package tool

import (
	"context"
	"strings"
	"testing"
)

func TestRetrieveToolsDoNotRequireCompatQuery(t *testing.T) {
	registry := retrievalContractTestRegistry()
	appSearch, ok := registry.Metadata("app_search")
	if !ok {
		t.Fatal(`tool "app_search" not registered`)
	}
	for _, key := range appSearch.RequiredInputKeys {
		if key == "query" || key == "mode" || key == "strategy" || key == "type" || key == "relation" {
			t.Fatalf("tool %q must not require compat key %q", appSearch.ToolName, key)
		}
	}
	webSearch, ok := registry.Metadata("web_search")
	if !ok {
		t.Fatal(`tool "web_search" not registered`)
	}
	if !containsString(webSearch.RequiredInputKeys, "query") {
		t.Fatalf("web_search required inputs=%#v, want query", webSearch.RequiredInputKeys)
	}
	for _, forbidden := range []string{"mode", "type", "relation"} {
		if strings.Contains(webSearch.Description, "\""+forbidden+"\"") {
			t.Fatalf("tool %q description should not promote %q", webSearch.ToolName, forbidden)
		}
	}
}

func TestAppSearchExecutesViaRetrieveTargets(t *testing.T) {
	registry := retrievalContractTestRegistry()
	result, err := registry.Execute(context.Background(), Request{
		ToolName: "app_search",
		Input: map[string]any{
			"targets": []any{"article", "entity"},
			"terms":   []any{"四川", "露营"},
		},
	})
	if err != nil {
		t.Fatalf("app_search err=%v", err)
	}
	results, ok := result.Output["results"].([]map[string]any)
	if !ok || len(results) == 0 {
		t.Fatalf("expected retrieve hits, got %#v", result.Output["results"])
	}
	for _, hit := range results {
		target, _ := hit["target"].(string)
		switch target {
		case "article", "photo", "video", "user", "entity", "circle", "group", "chat":
		default:
			t.Fatalf("hit target must be an AI target, got %q", target)
		}
		if _, leaked := hit["objectType"]; leaked {
			t.Fatalf("retrieve hit must not expose internal objectType: %#v", hit)
		}
	}
}

func TestSearchToolQueryCanonicalInput(t *testing.T) {
	registry := retrievalContractTestRegistry()
	result, err := registry.Execute(context.Background(), Request{
		ToolName: "web_search",
		Input:    map[string]any{"query": "四川 露营"},
	})
	if err != nil {
		t.Fatalf("web_search err=%v", err)
	}
	if result.Output["provider"] == nil {
		t.Fatalf("web_search output missing provider: %#v", result.Output)
	}
}

func retrievalContractTestRegistry() Registry {
	registry := BaseRegistry()
	appSearchMetadata := AppSearchMetadata()
	appSearchMetadata.RequiredInputKeys = []string{"targets", "terms"}
	registry.Register(appSearchMetadata, func(_ context.Context, request Request) (Result, error) {
		targets := toTestStringSlice(request.Input["targets"])
		results := make([]map[string]any, 0, len(targets))
		for _, target := range targets {
			results = append(results, map[string]any{
				"target":   target,
				"objectId": target + "_test",
				"title":    "typed test result",
			})
		}
		return Result{Output: map[string]any{
			"provider":  "test_search_adapter",
			"summary":   "typed test result",
			"results":   results,
			"citations": []map[string]any{},
			"provenance": map[string]any{
				"provider":     "test_search_adapter",
				"indexVersion": "test",
			},
		}}, nil
	})
	registry.Register(WebSearchMetadata(), func(_ context.Context, _ Request) (Result, error) {
		return Result{Output: map[string]any{
			"provider":   "test_web_adapter",
			"summary":    "web test result",
			"references": []map[string]any{},
		}}, nil
	})
	return registry
}

func toTestStringSlice(value any) []string {
	raw, _ := value.([]any)
	result := make([]string, 0, len(raw))
	for _, item := range raw {
		if text, ok := item.(string); ok {
			result = append(result, text)
		}
	}
	return result
}

func containsString(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}
