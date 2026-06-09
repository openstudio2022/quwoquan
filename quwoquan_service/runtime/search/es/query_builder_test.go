package es

import (
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
)

func boolOf(t *testing.T, body map[string]any) map[string]any {
	t.Helper()
	q, ok := body["query"].(map[string]any)
	if !ok {
		t.Fatalf("missing query: %#v", body)
	}
	b, ok := q["bool"].(map[string]any)
	if !ok {
		t.Fatalf("missing bool: %#v", q)
	}
	return b
}

func TestBuildTermsProduceMultiMatch(t *testing.T) {
	b := NewQueryBuilder()
	plan, _ := rtsearch.PlanRequest(rtsearch.RetrieveRequest{
		Targets: []rtsearch.Target{rtsearch.TargetArticle},
		Terms:   []string{"四川", "露营"},
	}, rtsearch.Viewer{})
	body := b.Build(plan)
	bq := boolOf(t, body)
	must, ok := bq["must"].([]map[string]any)
	if !ok || len(must) != 1 {
		t.Fatalf("expected one must clause, got %#v", bq["must"])
	}
	if _, ok := must[0]["multi_match"]; !ok {
		t.Fatalf("expected multi_match, got %#v", must[0])
	}
}

func TestBuildAppliesFiltersAndPermission(t *testing.T) {
	b := NewQueryBuilder()
	plan, _ := rtsearch.PlanRequest(rtsearch.RetrieveRequest{
		Targets: []rtsearch.Target{rtsearch.TargetArticle},
		Terms:   []string{"露营"},
		Filters: rtsearch.RetrieveFilters{
			Tags:      []string{"旅行"},
			TimeRange: &rtsearch.TimeRange{From: time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)},
		},
	}, rtsearch.Viewer{}) // not IncludePrivate -> visibility filter

	bq := boolOf(t, body(b, plan))
	filters, ok := bq["filter"].([]map[string]any)
	if !ok {
		t.Fatalf("expected filter clauses, got %#v", bq["filter"])
	}
	var hasTarget, hasTags, hasRange, hasVisibility bool
	for _, f := range filters {
		if terms, ok := f["terms"].(map[string]any); ok {
			if _, ok := terms["target"]; ok {
				hasTarget = true
			}
			if _, ok := terms["tags"]; ok {
				hasTags = true
			}
			if _, ok := terms["visibility"]; ok {
				hasVisibility = true
			}
		}
		if _, ok := f["range"]; ok {
			hasRange = true
		}
	}
	if !hasTarget || !hasTags || !hasRange || !hasVisibility {
		t.Fatalf("filters incomplete target=%v tags=%v range=%v vis=%v", hasTarget, hasTags, hasRange, hasVisibility)
	}
}

func body(b *QueryBuilder, plan rtsearch.RetrievePlan) map[string]any { return b.Build(plan) }

func TestBuildAnchorOnlyRequiresShouldMatch(t *testing.T) {
	b := NewQueryBuilder()
	plan, _ := rtsearch.PlanRequest(rtsearch.RetrieveRequest{
		Targets: []rtsearch.Target{rtsearch.TargetArticle},
		Names:   []string{"alice"},
	}, rtsearch.Viewer{})
	bq := boolOf(t, b.Build(plan))
	if _, ok := bq["must"]; ok {
		t.Fatalf("anchor-only query must have no must clause: %#v", bq)
	}
	if bq["minimum_should_match"] != 1 {
		t.Fatalf("anchor-only query must require minimum_should_match=1, got %#v", bq["minimum_should_match"])
	}
	if _, ok := bq["should"].([]map[string]any); !ok {
		t.Fatalf("expected should anchors, got %#v", bq["should"])
	}
}

func TestBuildHybridAddsKnnAndRRF(t *testing.T) {
	b := NewQueryBuilder()
	plan, _ := rtsearch.PlanRequest(rtsearch.RetrieveRequest{
		Targets: []rtsearch.Target{rtsearch.TargetArticle},
		Terms:   []string{"露营"},
	}, rtsearch.Viewer{})
	body := b.BuildHybrid(plan, []float64{0.1, 0.2, 0.3}, 10)
	if _, ok := body["knn"]; !ok {
		t.Fatalf("expected knn clause, got %#v", body)
	}
	if _, ok := body["rank"]; !ok {
		t.Fatalf("expected rrf rank, got %#v", body)
	}
}
