package recommendation

import (
	"testing"

	recpolicy "quwoquan_service/runtime/recpolicy"
)

// W9 轻量融合契约：源配额截断防单源霸屏、boost 源间校准、
// disabled 零行为（可一键回滚）。
func TestApplySourceQuotaCapsPerSourceShare(t *testing.T) {
	candidates := make([]ContentCandidate, 0, 30)
	for i := 0; i < 20; i++ {
		candidates = append(candidates, ContentCandidate{
			ContentID: "collab_" + string(rune('a'+i)), RecallPath: "collab_i2i",
		})
	}
	for i := 0; i < 10; i++ {
		candidates = append(candidates, ContentCandidate{
			ContentID: "tag_" + string(rune('a'+i)), RecallPath: "tag_recall",
		})
	}

	out := applySourceQuota(candidates, recpolicy.RecallFusionConfig{
		Enabled:        true,
		SourceQuotaPct: map[string]int{"collab_i2i": 15},
	}, 60)

	collab, tag := 0, 0
	for _, c := range out {
		switch c.RecallPath {
		case "collab_i2i":
			collab++
		case "tag_recall":
			tag++
		}
	}
	if collab != 9 { // 60 * 15% = 9
		t.Fatalf("collab_i2i must be capped at quota 9, got %d", collab)
	}
	if tag != 10 {
		t.Fatalf("unregistered source must not be limited, got %d", tag)
	}
}

func TestApplySourceQuotaDisabledIsZeroBehavior(t *testing.T) {
	candidates := []ContentCandidate{
		{ContentID: "a", RecallPath: "collab_i2i"},
		{ContentID: "b", RecallPath: "collab_i2i"},
	}
	out := applySourceQuota(candidates, recpolicy.RecallFusionConfig{
		Enabled:        false,
		SourceQuotaPct: map[string]int{"collab_i2i": 1},
	}, 100)
	if len(out) != 2 {
		t.Fatalf("disabled fusion must keep all candidates, got %d", len(out))
	}
}

func TestApplyRecallSourceBoostCalibratesScores(t *testing.T) {
	scored := []ScoredCandidate{
		{Candidate: ContentCandidate{ContentID: "v", RecallPath: "vector_recall"}, Score: 1.0},
		{Candidate: ContentCandidate{ContentID: "t", RecallPath: "tag_recall"}, Score: 1.0},
	}
	applyRecallSourceBoost(scored, recpolicy.RecallFusionConfig{
		Enabled:     true,
		SourceBoost: map[string]float64{"vector_recall": 1.5},
	})
	if scored[0].Score != 1.5 {
		t.Fatalf("boosted source score = %v want 1.5", scored[0].Score)
	}
	if scored[1].Score != 1.0 {
		t.Fatalf("unregistered source must stay neutral, got %v", scored[1].Score)
	}
}

// W9 LTR 阶段策略契约（B11）：S0 期 model 桶必须为 0（shadow-only），
// 爬坡只能按 S1 样本量触发经 policy 变更推进，不得代码内偷跑。
func TestModelVsRuleBucketIsShadowOnlyInBaseline(t *testing.T) {
	policy := recpolicy.Baseline()
	for _, exp := range policy.Experiments {
		if exp.ID != recpolicy.ExpModelVsRule {
			continue
		}
		for _, bucket := range exp.Buckets {
			switch bucket.Name {
			case "rule":
				if bucket.WeightPct != 100 {
					t.Fatalf("S0 rule bucket must be 100%%, got %d", bucket.WeightPct)
				}
			case "model":
				if bucket.WeightPct != 0 {
					t.Fatalf("S0 model bucket must be 0%% (shadow-only), got %d", bucket.WeightPct)
				}
			}
		}
		return
	}
	t.Fatalf("experiment %s missing from baseline policy", recpolicy.ExpModelVsRule)
}
