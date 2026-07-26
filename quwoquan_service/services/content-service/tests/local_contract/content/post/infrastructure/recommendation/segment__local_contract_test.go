package recommendation_test

import (
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"reflect"
	"testing"
)

func testSegmentDefs() []SegmentDef {
	return []SegmentDef{
		{ID: "travel_enthusiast", Priority: 100, Match: SegmentMatch{
			LifecycleStages: []string{"active", "dormant"},
			MinTagScores:    []SegmentTagScoreReq{{TagRef: "旅行", Dimension: "topic", Min: 0.6}},
		}},
		{ID: "visual_content_lover", Priority: 80, Match: SegmentMatch{
			MinTagScores: []SegmentTagScoreReq{{TagRef: "图文", Dimension: "format", Min: 0.5}},
		}},
		{ID: "newcomer", Priority: 10, Match: SegmentMatch{
			LifecycleStages: []string{"new"},
		}},
	}
}

func TestMatchSegments_HitWithScoreAndStage(t *testing.T) {
	p := InterestProfile{
		LifecycleStage: StageActive,
		TopInterests: []TopInterest{
			{TagRef: "旅行", Dimension: DimTopic, Score: 0.7},
			{TagRef: "图文", Dimension: DimFormat, Score: 0.6},
		},
	}
	got := MatchSegments(p, testSegmentDefs())
	want := []string{"travel_enthusiast", "visual_content_lover"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v (priority desc)", got, want)
	}
}

func TestMatchSegments_ScoreBelowThreshold(t *testing.T) {
	p := InterestProfile{
		LifecycleStage: StageActive,
		TopInterests:   []TopInterest{{TagRef: "旅行", Dimension: DimTopic, Score: 0.5}},
	}
	if got := MatchSegments(p, testSegmentDefs()); len(got) != 0 {
		t.Fatalf("got %v, want none (0.5<0.6)", got)
	}
}

func TestMatchSegments_StageMismatch(t *testing.T) {
	// 旅行 score high but lifecycle=new is not in [active,dormant].
	p := InterestProfile{
		LifecycleStage: StageNew,
		TopInterests:   []TopInterest{{TagRef: "旅行", Dimension: DimTopic, Score: 0.9}},
	}
	got := MatchSegments(p, testSegmentDefs())
	want := []string{"newcomer"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}

func TestMatchSegments_DimensionMustMatch(t *testing.T) {
	// 旅行 high score but on wrong dimension (format, not topic) → no travel hit.
	p := InterestProfile{
		LifecycleStage: StageActive,
		TopInterests:   []TopInterest{{TagRef: "旅行", Dimension: DimFormat, Score: 0.9}},
	}
	if got := MatchSegments(p, testSegmentDefs()); len(got) != 0 {
		t.Fatalf("got %v, want none (dimension mismatch)", got)
	}
}

func TestMatchSegments_EmptyProfileNoCrash(t *testing.T) {
	if got := MatchSegments(InterestProfile{}, testSegmentDefs()); len(got) != 0 {
		t.Fatalf("empty profile should match nothing, got %v", got)
	}
}

func TestMatchSegments_EmptyPredicateNeverMatches(t *testing.T) {
	defs := []SegmentDef{{ID: "catch_all", Priority: 1, Match: SegmentMatch{}}}
	p := InterestProfile{LifecycleStage: StageActive, TopInterests: []TopInterest{{TagRef: "x", Score: 1}}}
	if got := MatchSegments(p, defs); len(got) != 0 {
		t.Fatalf("empty-predicate segment must not match, got %v", got)
	}
}
