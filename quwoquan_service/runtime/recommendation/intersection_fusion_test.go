package recommendation

import (
	"context"
	"math"
	"testing"
	"time"

	"quwoquan_service/runtime/recpolicy"
)

// 交集信号在 socialPrior 单点注入：社交/交集来源候选按 viewer 揭示的同 kind 参与度
// 取得有界提升，非交集来源候选不受影响。
func TestRuleScorer_IntersectionSignalLiftsSocialOriginCandidates(t *testing.T) {
	scorer := &RuleScorer{}
	now := time.Now()
	cands := []ContentCandidate{
		{ContentID: "friend", ContentType: "article", PublishedAt: now, RecallPath: "social_friend"},
		{ContentID: "circle", ContentType: "article", PublishedAt: now, RecallPath: "social_circle"},
		{ContentID: "hot", ContentType: "article", PublishedAt: now, RecallPath: "hot_recall"},
	}
	features := &ScoringFeatures{
		Weights:       recpolicy.Baseline().WeightPresets[recpolicy.Baseline().DefaultPreset],
		Scorer:        recpolicy.Baseline().Scorer,
		Deterministic: true,
		User:          &UserFeatureVector{SharedFolloweesCount: 8, SharedCircleCount: 4},
	}
	scored, err := scorer.ScoreBatch(context.Background(), features, cands)
	if err != nil {
		t.Fatalf("score: %v", err)
	}
	byID := map[string]ScoredCandidate{}
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
	// SharedFolloweesCount(8) > SharedCircleCount(4) ⇒ friend 提升大于 circle。
	if !(friendSP > circleSP) {
		t.Fatalf("higher revealed engagement should yield larger lift: friend=%.4f circle=%.4f", friendSP, circleSP)
	}
}

func TestRuleScorer_IntersectionSignalDisabledWhenFactorZero(t *testing.T) {
	scorer := &RuleScorer{}
	now := time.Now()
	cands := []ContentCandidate{{ContentID: "friend", ContentType: "article", PublishedAt: now, RecallPath: "social_friend"}}
	sc := recpolicy.Baseline().Scorer
	sc.IntersectionSignalFactor = 0 // 关闭融合
	features := &ScoringFeatures{
		Weights:       recpolicy.Baseline().WeightPresets[recpolicy.Baseline().DefaultPreset],
		Scorer:        sc,
		Deterministic: true,
		User:          &UserFeatureVector{SharedFolloweesCount: 8},
	}
	scored, err := scorer.ScoreBatch(context.Background(), features, cands)
	if err != nil {
		t.Fatalf("score: %v", err)
	}
	if got := scored[0].Detail["socialPrior"]; math.Abs(got) > 1e-12 {
		t.Fatalf("zero factor must disable intersection lift, got socialPrior=%.6f", got)
	}
}

func TestRuleScorer_IntersectionSignalNoUserNoPanic(t *testing.T) {
	scorer := &RuleScorer{}
	cands := []ContentCandidate{{ContentID: "friend", ContentType: "article", PublishedAt: time.Now(), RecallPath: "social_friend"}}
	features := &ScoringFeatures{
		Weights:       recpolicy.Baseline().WeightPresets[recpolicy.Baseline().DefaultPreset],
		Scorer:        recpolicy.Baseline().Scorer,
		Deterministic: true,
		User:          nil, // 游客 / 无特征
	}
	scored, err := scorer.ScoreBatch(context.Background(), features, cands)
	if err != nil {
		t.Fatalf("score: %v", err)
	}
	if got := scored[0].Detail["socialPrior"]; math.Abs(got) > 1e-12 {
		t.Fatalf("nil user must yield zero socialPrior, got %.6f", got)
	}
}
