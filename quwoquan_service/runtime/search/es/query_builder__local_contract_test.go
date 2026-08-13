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
	// The commercial ranking is pushed down: bool recall is wrapped inside one
	// function_score (freshness/quality/geo), so the engine order is final.
	fs, ok := q["function_score"].(map[string]any)
	if !ok {
		t.Fatalf("missing function_score pushdown: %#v", q)
	}
	inner, ok := fs["query"].(map[string]any)
	if !ok {
		t.Fatalf("missing function_score query: %#v", fs)
	}
	b, ok := inner["bool"].(map[string]any)
	if !ok {
		t.Fatalf("missing bool: %#v", inner)
	}
	return b
}

func TestBuildTermsProduceComposedTextRecall(t *testing.T) {
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
	composed, ok := must[0]["bool"].(map[string]any)
	if !ok || composed["minimum_should_match"] != 1 {
		t.Fatalf("expected composed text bool with minimum_should_match=1, got %#v", must[0])
	}
	clauses, ok := composed["should"].([]map[string]any)
	if !ok || len(clauses) == 0 {
		t.Fatalf("expected text should clauses, got %#v", composed["should"])
	}
	var hasBestFields, hasPhrase, hasPinyin bool
	for _, clause := range clauses {
		mm, ok := clause["multi_match"].(map[string]any)
		if !ok {
			t.Fatalf("expected multi_match clause, got %#v", clause)
		}
		switch {
		case mm["type"] == "phrase":
			hasPhrase = true
		case fieldsContain(mm["fields"], "title.py^1.2"):
			hasPinyin = true
		case mm["type"] == "best_fields" && fieldsContain(mm["fields"], "title^3"):
			hasBestFields = true
		}
	}
	if !hasBestFields || !hasPhrase || !hasPinyin {
		t.Fatalf("composed recall incomplete best=%v phrase=%v pinyin=%v: %#v", hasBestFields, hasPhrase, hasPinyin, clauses)
	}
	if _, ok := body["highlight"].(map[string]any); !ok {
		t.Fatalf("term queries must request the server-side highlighter: %#v", body)
	}
}

func fieldsContain(value any, expected string) bool {
	fields, ok := value.([]string)
	if !ok {
		if anyFields, isAny := value.([]any); isAny {
			for _, field := range anyFields {
				if field == expected {
					return true
				}
			}
		}
		return false
	}
	for _, field := range fields {
		if field == expected {
			return true
		}
	}
	return false
}

func TestBuildFuzzinessOnlyFiresForShortQueries(t *testing.T) {
	b := NewQueryBuilder()
	shortPlan, _ := rtsearch.PlanRequest(rtsearch.RetrieveRequest{
		Targets: []rtsearch.Target{rtsearch.TargetArticle},
		Terms:   []string{"露营"},
	}, rtsearch.Viewer{})
	longPlan, _ := rtsearch.PlanRequest(rtsearch.RetrieveRequest{
		Targets: []rtsearch.Target{rtsearch.TargetArticle},
		Terms:   []string{"四川", "露营", "亲子", "路线"},
	}, rtsearch.Viewer{})
	if !buildHasFuzziness(t, b, shortPlan) {
		t.Fatal("short queries must include the bounded fuzziness clause")
	}
	if buildHasFuzziness(t, b, longPlan) {
		t.Fatal("long queries must not pay the fuzziness CPU cost")
	}
}

func buildHasFuzziness(t *testing.T, b *QueryBuilder, plan rtsearch.RetrievePlan) bool {
	t.Helper()
	bq := boolOf(t, b.Build(plan))
	must, _ := bq["must"].([]map[string]any)
	if len(must) != 1 {
		t.Fatalf("expected one must clause, got %#v", bq["must"])
	}
	composed, _ := must[0]["bool"].(map[string]any)
	clauses, _ := composed["should"].([]map[string]any)
	for _, clause := range clauses {
		if mm, ok := clause["multi_match"].(map[string]any); ok {
			if _, has := mm["fuzziness"]; has {
				return true
			}
		}
	}
	return false
}

func TestBuildSortAlignsWithLessHitStable(t *testing.T) {
	b := NewQueryBuilder()
	plan, _ := rtsearch.PlanRequest(rtsearch.RetrieveRequest{
		Targets: []rtsearch.Target{rtsearch.TargetArticle},
		Terms:   []string{"西湖"},
	}, rtsearch.Viewer{})
	body := b.Build(plan)
	sortClauses, ok := body["sort"].([]map[string]any)
	if !ok || len(sortClauses) != 4 {
		t.Fatalf("expected the 4-key stable sort, got %#v", body["sort"])
	}
	keys := make([]string, 0, len(sortClauses))
	for _, clause := range sortClauses {
		for key := range clause {
			keys = append(keys, key)
		}
	}
	expected := []string{"_score", "title.kw", "target", "objectId"}
	for index, key := range expected {
		if keys[index] != key {
			t.Fatalf("sort keys %v must align with rtsearch.LessHitStable %v", keys, expected)
		}
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

func TestBuildNearAddsGeoDistanceFilter(t *testing.T) {
	b := NewQueryBuilder()
	plan, _ := rtsearch.PlanRequest(rtsearch.RetrieveRequest{
		Targets: []rtsearch.Target{rtsearch.TargetEntity},
		Terms:   []string{"露营"},
		Filters: rtsearch.RetrieveFilters{
			Near: &rtsearch.GeoNear{Lat: 30.25, Lng: 120.15, RadiusKm: 5},
		},
	}, rtsearch.Viewer{})

	bq := boolOf(t, b.Build(plan))
	filters, ok := bq["filter"].([]map[string]any)
	if !ok {
		t.Fatalf("expected filter clauses, got %#v", bq["filter"])
	}
	var found bool
	for _, f := range filters {
		gd, ok := f["geo_distance"].(map[string]any)
		if !ok {
			continue
		}
		found = true
		if gd["distance"] != "5km" {
			t.Fatalf("geo_distance distance=%v want 5km", gd["distance"])
		}
		pin, ok := gd["geo"].(map[string]any)
		if !ok || pin["lat"] != 30.25 || pin["lon"] != 120.15 {
			t.Fatalf("geo_distance pin wrong: %#v", gd["geo"])
		}
	}
	if !found {
		t.Fatalf("expected geo_distance filter, got %#v", filters)
	}
}

func TestBuildNearFractionalRadius(t *testing.T) {
	b := NewQueryBuilder()
	plan, _ := rtsearch.PlanRequest(rtsearch.RetrieveRequest{
		Targets: []rtsearch.Target{rtsearch.TargetEntity},
		Filters: rtsearch.RetrieveFilters{Near: &rtsearch.GeoNear{Lat: 1, Lng: 2, RadiusKm: 2.5}},
	}, rtsearch.Viewer{})
	bq := boolOf(t, b.Build(plan))
	filters, _ := bq["filter"].([]map[string]any)
	var distance any
	for _, f := range filters {
		if gd, ok := f["geo_distance"].(map[string]any); ok {
			distance = gd["distance"]
		}
	}
	if distance != "2.5km" {
		t.Fatalf("fractional radius distance=%v want 2.5km", distance)
	}
}

func TestBuildNoNearOmitsGeoDistance(t *testing.T) {
	b := NewQueryBuilder()
	plan, _ := rtsearch.PlanRequest(rtsearch.RetrieveRequest{
		Targets: []rtsearch.Target{rtsearch.TargetEntity},
		Terms:   []string{"露营"},
	}, rtsearch.Viewer{})
	bq := boolOf(t, b.Build(plan))
	if filters, ok := bq["filter"].([]map[string]any); ok {
		for _, f := range filters {
			if _, ok := f["geo_distance"]; ok {
				t.Fatalf("no Near must omit geo_distance, got %#v", f)
			}
		}
	}
}

func TestBuildUsesStablePrefixInsteadOfExternalOffsetOrSearchAfter(t *testing.T) {
	b := NewQueryBuilder()
	plan, _ := rtsearch.PlanRequest(rtsearch.RetrieveRequest{
		Targets: []rtsearch.Target{rtsearch.TargetArticle},
		Terms:   []string{"西湖"},
		Page:    rtsearch.PageRequest{Limit: 11, Offset: 20},
	}, rtsearch.Viewer{})
	body := b.Build(plan)
	if body["from"] != 0 || body["size"] != 31 {
		t.Fatalf("ES recall must use prefix size=offset+limit from=0: %#v", body)
	}
	if _, exists := body["search_after"]; exists {
		t.Fatalf("ES search_after must not escape the Search owner cursor: %#v", body)
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
