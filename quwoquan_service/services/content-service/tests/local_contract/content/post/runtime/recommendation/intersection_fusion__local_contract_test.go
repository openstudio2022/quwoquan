package recommendationlocalcontract

import (
	"context"
	"math"
	"testing"
	"time"

	"quwoquan_service/runtime/recommendation"
	"quwoquan_service/runtime/recpolicy"
)

func TestRuleScorerIntersectionSignalFusionLocalContractTest(t *testing.T) {
	scorer := &recommendation.RuleScorer{}
	now := time.Now()
	cands := []recommendation.ContentCandidate{
		{ContentID: "friend", ContentType: "article", PublishedAt: now, RecallPath: "social_friend"},
		{ContentID: "circle", ContentType: "article", PublishedAt: now, RecallPath: "social_circle"},
		{ContentID: "hot", ContentType: "article", PublishedAt: now, RecallPath: "hot_recall"},
	}
	features := &recommendation.ScoringFeatures{
		Weights:       recpolicy.Baseline().WeightPresets[recpolicy.Baseline().DefaultPreset],
		Scorer:        recpolicy.Baseline().Scorer,
		Deterministic: true,
		User:          &recommendation.UserFeatureVector{SharedFolloweesCount: 8, SharedCircleCount: 4},
	}
	scored, err := scorer.ScoreBatch(context.Background(), features, cands)
	if err != nil {
		t.Fatalf("score: %v", err)
	}
	byID := map[string]recommendation.ScoredCandidate{}
	for _, s := range scored {
		byID[s.Candidate.ContentID] = s
	}
	friendSP := byID["friend"].Detail["socialPrior"]
	circleSP := byID["circle"].Detail["socialPrior"]
	hotSP := byID["hot"].Detail["socialPrior"]
	if !(friendSP > hotSP) {
		t.Fatalf("social_friend candidate must earn intersection socialPrior lift: friend=%.4f hot=%.4f", friendSP, hotSP)
	}
	if !(circleSP > hotSP) {
		t.Fatalf("social_circle candidate must earn intersection socialPrior lift: circle=%.4f hot=%.4f", circleSP, hotSP)
	}
	if math.Abs(hotSP) > 1e-12 {
		t.Fatalf("non-intersection candidate must not receive intersection lift, got socialPrior=%.6f", hotSP)
	}
	if !(friendSP > circleSP) {
		t.Fatalf("higher revealed engagement should yield larger lift: friend=%.4f circle=%.4f", friendSP, circleSP)
	}
}

func TestRuleScorerIntersectionFactOutranksAffinityLocalContractTest(t *testing.T) {
	scorer := &recommendation.RuleScorer{}
	now := time.Now()
	cands := []recommendation.ContentCandidate{
		{
			ContentID:         "fact",
			ContentType:       "article",
			PublishedAt:       now,
			AuthorID:          "u_fact_author",
			IntersectionClass: "fact",
		},
		{
			ContentID:                   "affinity",
			ContentType:                 "article",
			PublishedAt:                 now,
			AffinityIntersectionScore:   1,
			IntersectionConfidenceLabel: "high",
			IntersectionClass:           "affinity",
		},
	}
	features := &recommendation.ScoringFeatures{
		Weights:       recpolicy.Baseline().WeightPresets[recpolicy.Baseline().DefaultPreset],
		Scorer:        recpolicy.Baseline().Scorer,
		Deterministic: true,
		// 事实通道读的是 viewer↔候选对象的物化交集边（rm_viewer_object_intersection），
		// 不是候选自身的 intersectionFactStrength（那是内容侧交集承载力，与看的人无关）。
		User: &recommendation.UserFeatureVector{
			IntersectionEdges: map[string]recommendation.IntersectionEdgeFeature{
				"u_fact_author": {Weight: 1, Freshness: 1, Kind: "commonFollower"},
			},
		},
	}
	scored, err := scorer.ScoreBatch(context.Background(), features, cands)
	if err != nil {
		t.Fatalf("score: %v", err)
	}
	byID := map[string]recommendation.ScoredCandidate{}
	for _, s := range scored {
		byID[s.Candidate.ContentID] = s
	}
	if !(byID["fact"].Score > byID["affinity"].Score) {
		t.Fatalf("fact intersection must outrank affinity: fact=%.4f affinity=%.4f", byID["fact"].Score, byID["affinity"].Score)
	}
	if !(byID["fact"].Detail["intersectionFact"] > byID["affinity"].Detail["intersectionAffinity"]) {
		t.Fatalf("fact detail must be stronger than affinity: fact=%v affinity=%v", byID["fact"].Detail, byID["affinity"].Detail)
	}
}

func TestRuleScorerAffinityIntersectionRequiresConfidenceLabelLocalContractTest(t *testing.T) {
	scorer := &recommendation.RuleScorer{}
	now := time.Now()
	cands := []recommendation.ContentCandidate{{
		ContentID:                 "affinity_without_label",
		ContentType:               "article",
		PublishedAt:               now,
		AffinityIntersectionScore: 1,
		IntersectionClass:         "affinity",
	}}
	features := &recommendation.ScoringFeatures{
		Weights:       recpolicy.Baseline().WeightPresets[recpolicy.Baseline().DefaultPreset],
		Scorer:        recpolicy.Baseline().Scorer,
		Deterministic: true,
	}
	scored, err := scorer.ScoreBatch(context.Background(), features, cands)
	if err != nil {
		t.Fatalf("score: %v", err)
	}
	if got := scored[0].Detail["intersectionAffinity"]; math.Abs(got) > 1e-12 {
		t.Fatalf("affinity without confidenceLabel must be ignored, got %.6f", got)
	}
}
