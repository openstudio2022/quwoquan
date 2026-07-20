package recommendation

import (
	"context"
	"math"
	"testing"
	"time"

	"quwoquan_service/runtime/recpolicy"
)

func TestUCBExplorationRadius_FavorsUnderExposed(t *testing.T) {
	// 同一 corpus 下，曝光越少探索半径越大；全新内容应取得最大半径。
	fresh := ucbExplorationRadius(0, 10_000)
	mid := ucbExplorationRadius(100, 10_000)
	heavy := ucbExplorationRadius(10_000, 10_000)
	if !(fresh > mid && mid > heavy) {
		t.Fatalf("expected monotonic decreasing radius: fresh=%.4f mid=%.4f heavy=%.4f", fresh, mid, heavy)
	}
	if fresh < 0 || fresh > 1 {
		t.Fatalf("radius must be clamped to [0,1], got %.4f", fresh)
	}
}

func TestUCBExplorationRadius_DeterministicAndBounded(t *testing.T) {
	// 纯函数：相同输入必得相同输出（保证跨游标分页可复现）。
	a := ucbExplorationRadius(42, 5000)
	b := ucbExplorationRadius(42, 5000)
	if a != b {
		t.Fatalf("ucb radius must be deterministic: %.6f != %.6f", a, b)
	}
	// 大 corpus + 零曝光会触发 clamp 到 1。
	if got := ucbExplorationRadius(0, 1_000_000_000); got != 1 {
		t.Fatalf("expected clamp to 1 for huge corpus + zero exposure, got %.6f", got)
	}
	// 负值防御。
	if got := ucbExplorationRadius(-5, -5); got < 0 || got > 1 {
		t.Fatalf("negative inputs must stay in [0,1], got %.6f", got)
	}
}

func TestRuleScorer_ExploreBoostExposureAware(t *testing.T) {
	scorer := &RuleScorer{}
	now := time.Now()
	cands := []ContentCandidate{
		{ContentID: "fresh", ContentType: "article", PublishedAt: now, ViewCount: 0},
		{ContentID: "heavy", ContentType: "article", PublishedAt: now, ViewCount: 100000},
	}
	features := &ScoringFeatures{
		Weights:       recpolicy.Baseline().WeightPresets[recpolicy.Baseline().DefaultPreset],
		Scorer:        recpolicy.Baseline().Scorer,
		ExploreRate:   0.2,
		Deterministic: false,
	}
	scored, err := scorer.ScoreBatch(context.Background(), features, cands)
	if err != nil {
		t.Fatalf("score: %v", err)
	}
	byID := map[string]ScoredCandidate{}
	for _, s := range scored {
		byID[s.Candidate.ContentID] = s
	}
	freshBoost := byID["fresh"].Detail["exploreBoost"]
	heavyBoost := byID["heavy"].Detail["exploreBoost"]
	if !(freshBoost > heavyBoost) {
		t.Fatalf("under-exposed content must earn a larger explore boost: fresh=%.4f heavy=%.4f", freshBoost, heavyBoost)
	}
	if freshBoost > features.ExploreRate+1e-9 {
		t.Fatalf("explore boost must not exceed ExploreRate, got %.4f > %.4f", freshBoost, features.ExploreRate)
	}
}

func TestRuleScorer_ExploreBoostDisabledWhenDeterministic(t *testing.T) {
	scorer := &RuleScorer{}
	cands := []ContentCandidate{{ContentID: "x", ContentType: "article", PublishedAt: time.Now(), ViewCount: 0}}
	features := &ScoringFeatures{
		Weights:       recpolicy.Baseline().WeightPresets[recpolicy.Baseline().DefaultPreset],
		Scorer:        recpolicy.Baseline().Scorer,
		ExploreRate:   0.2,
		Deterministic: true, // 游标分页：稳定排序，关闭探索扰动
	}
	scored, err := scorer.ScoreBatch(context.Background(), features, cands)
	if err != nil {
		t.Fatalf("score: %v", err)
	}
	if got := scored[0].Detail["exploreBoost"]; math.Abs(got) > 1e-12 {
		t.Fatalf("deterministic mode must zero the explore boost, got %.6f", got)
	}
}
