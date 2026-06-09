package tool

import (
	"context"
	"strings"
	"testing"
)

func TestRetrieveToolsDoNotRequireLegacyQuery(t *testing.T) {
	registry := DefaultRegistry()
	for _, name := range []string{"search", "app_search"} {
		meta, ok := registry.Metadata(name)
		if !ok {
			t.Fatalf("tool %q not registered", name)
		}
		for _, key := range meta.RequiredInputKeys {
			if key == "query" || key == "mode" || key == "strategy" || key == "type" || key == "relation" {
				t.Fatalf("tool %q must not require legacy key %q", name, key)
			}
		}
		for _, forbidden := range []string{"mode", "type", "relation"} {
			if strings.Contains(meta.Description, "\""+forbidden+"\"") {
				t.Fatalf("tool %q description should not promote %q", name, forbidden)
			}
		}
	}
}

func TestAppSearchExecutesViaRetrieveTargets(t *testing.T) {
	registry := DefaultRegistry()
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

func TestSearchToolLegacyQueryStillParsed(t *testing.T) {
	registry := DefaultRegistry()
	result, err := registry.Execute(context.Background(), Request{
		ToolName: "search",
		Input:    map[string]any{"query": "四川 露营"},
	})
	if err != nil {
		t.Fatalf("search err=%v", err)
	}
	if result.Output["provider"] == nil {
		t.Fatalf("search output missing provider: %#v", result.Output)
	}
}
