package recommendation

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/runtime/recpolicy"
)

func TestRuleScorer_QualityScoreLiftsColdStartCandidate(t *testing.T) {
	scorer := &RuleScorer{}
	now := time.Now()
	cands := []ContentCandidate{
		{ContentID: "low_quality", ContentType: "article", PublishedAt: now, QualityScore: 0.2},
		{ContentID: "high_quality", ContentType: "article", PublishedAt: now, QualityScore: 0.9},
	}
	features := &ScoringFeatures{
		Weights:       recpolicy.Baseline().WeightPresets[recpolicy.Baseline().DefaultPreset],
		Scorer:        recpolicy.Baseline().Scorer,
		Deterministic: true,
	}

	scored, err := scorer.ScoreBatch(context.Background(), features, cands)
	if err != nil {
		t.Fatalf("score: %v", err)
	}
	byID := map[string]ScoredCandidate{}
	for _, s := range scored {
		byID[s.Candidate.ContentID] = s
	}
	if !(byID["high_quality"].Score > byID["low_quality"].Score) {
		t.Fatalf("qualityScore must lift cold-start content: high=%.4f low=%.4f", byID["high_quality"].Score, byID["low_quality"].Score)
	}
	if byID["high_quality"].Detail["qualityScore"] != 0.9 {
		t.Fatalf("quality detail not projected: %+v", byID["high_quality"].Detail)
	}
}
