package application

import (
	"context"
	"testing"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/services/search-service/internal/application/queryheat"
)

type fakeTermHeat struct {
	terms []queryheat.TermHeat
	err   error
}

func (f fakeTermHeat) RelatedTerms(_ context.Context, _ string, _ int) ([]queryheat.TermHeat, error) {
	return f.terms, f.err
}

func forcedBucket(name string) *Experiments {
	return NewExperiments(ExperimentConfig{
		Enabled: true,
		Buckets: []ExperimentBucket{{Name: name, WeightPct: 100}},
	})
}

func baseResponse() rtsearch.RetrieveResponse {
	return rtsearch.RetrieveResponse{
		Hits: []rtsearch.RetrieveHit{
			{Target: rtsearch.TargetArticle, ObjectID: "a", Title: "成都美食指南", Score: 2.0, RankPosition: 1},
			{Target: rtsearch.TargetArticle, ObjectID: "b", Title: "成都火锅攻略", Score: 1.0, RankPosition: 2},
		},
	}
}

// term_heat arm: the hot term "火锅" lifts hit B above A and stamps a transparent
// reason; relatedTerms surface on the envelope and RankPosition is renumbered.
func TestDecorateTermHeatReranksAndExplains(t *testing.T) {
	provider := fakeTermHeat{terms: []queryheat.TermHeat{{NormalizedTerm: "火锅", Relevance: 10}}}
	d := NewRankingDecorator(provider, forcedBucket(BucketTermHeat), 5.0, nil)

	res := d.Decorate(context.Background(), baseResponse(), "成都", "user_1")
	if res.ExperimentBucket != BucketTermHeat {
		t.Fatalf("bucket=%q want term_heat", res.ExperimentBucket)
	}
	if len(res.RelatedTerms) != 1 || res.RelatedTerms[0] != "火锅" {
		t.Fatalf("relatedTerms=%v want [火锅]", res.RelatedTerms)
	}
	if res.Hits[0].ObjectID != "b" {
		t.Fatalf("term-heat must lift the 火锅 hit to first, got order %s,%s", res.Hits[0].ObjectID, res.Hits[1].ObjectID)
	}
	if res.Hits[0].RankPosition != 1 || res.Hits[1].RankPosition != 2 {
		t.Fatalf("RankPosition must be renumbered after re-rank: %d,%d", res.Hits[0].RankPosition, res.Hits[1].RankPosition)
	}
	if !hasReason(res.Hits[0].RankReasons, "search.term_heat") {
		t.Fatalf("boosted hit must carry a search.term_heat reason, got %+v", res.Hits[0].RankReasons)
	}
}

// control arm: same inputs, but no heat boost — order and reasons are untouched.
func TestDecorateControlLeavesBaseRanking(t *testing.T) {
	provider := fakeTermHeat{terms: []queryheat.TermHeat{{NormalizedTerm: "火锅", Relevance: 10}}}
	d := NewRankingDecorator(provider, forcedBucket(BucketControl), 5.0, nil)

	res := d.Decorate(context.Background(), baseResponse(), "成都", "user_1")
	if res.ExperimentBucket != BucketControl {
		t.Fatalf("bucket=%q want control", res.ExperimentBucket)
	}
	if res.Hits[0].ObjectID != "a" {
		t.Fatalf("control must keep base order, got %s first", res.Hits[0].ObjectID)
	}
	if hasReason(res.Hits[1].RankReasons, "search.term_heat") {
		t.Fatalf("control must not apply term-heat reasons")
	}
	// relatedTerms still served (they back the suggest envelope regardless of arm).
	if len(res.RelatedTerms) != 1 {
		t.Fatalf("relatedTerms should still be served in control, got %v", res.RelatedTerms)
	}
}

// A failing provider must degrade to base ranking, never fail the search.
func TestDecorateProviderErrorDegrades(t *testing.T) {
	d := NewRankingDecorator(fakeTermHeat{err: context.DeadlineExceeded}, forcedBucket(BucketTermHeat), 5.0, nil)
	res := d.Decorate(context.Background(), baseResponse(), "成都", "user_1")
	if len(res.Hits) != 2 || res.Hits[0].ObjectID != "a" {
		t.Fatalf("provider error must degrade to base ranking, got %+v", res.Hits)
	}
	if len(res.RelatedTerms) != 0 {
		t.Fatalf("provider error must yield no related terms, got %v", res.RelatedTerms)
	}
}

func hasReason(reasons []rtsearch.Reason, code string) bool {
	for _, r := range reasons {
		if r.Code == code {
			return true
		}
	}
	return false
}
