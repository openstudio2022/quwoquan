package search

import "testing"

func TestSplitQueryTerms(t *testing.T) {
	got := SplitQueryTerms("  洱海 骑行  ")
	if len(got) != 3 || got[0] != "洱海 骑行" || got[1] != "洱海" || got[2] != "骑行" {
		t.Fatalf("unexpected terms: %#v", got)
	}
	if SplitQueryTerms("   ") != nil {
		t.Fatalf("blank query should yield nil terms")
	}
	single := SplitQueryTerms("大理")
	if len(single) != 1 || single[0] != "大理" {
		t.Fatalf("single-token query should not duplicate: %#v", single)
	}
}

func TestNormalizeTargets(t *testing.T) {
	defaults := []Target{TargetArticle}
	got := NormalizeTargets([]string{"Photo", "video", "unknown", "photo"}, defaults)
	if len(got) != 2 || got[0] != TargetPhoto || got[1] != TargetVideo {
		t.Fatalf("unexpected targets: %#v", got)
	}
	if fallback := NormalizeTargets([]string{"bogus"}, defaults); len(fallback) != 1 || fallback[0] != TargetArticle {
		t.Fatalf("expected default fallback, got %#v", fallback)
	}
}

func TestBuildQueryFirstRequest(t *testing.T) {
	req := BuildQueryFirstRequest("大理 古城", []string{"article"}, 15, RetrieveFilters{Tags: []string{"旅行"}}, AllTargets)
	if len(req.Targets) != 1 || req.Targets[0] != TargetArticle {
		t.Fatalf("targets: %#v", req.Targets)
	}
	if req.Page.Limit != 15 || len(req.Terms) == 0 || req.Filters.Tags[0] != "旅行" {
		t.Fatalf("request not assembled: %#v", req)
	}
}
