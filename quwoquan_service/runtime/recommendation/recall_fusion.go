package recommendation

import (
	recpolicy "quwoquan_service/runtime/recpolicy"
)

// applySourceQuota 按 policy 源配额截断单源候选（source-quota 轻量融合）。
// quota = poolLimit * pct / 100（至少 1）；未登记的 recallPath 不受限。
// 截断保持候选原有顺序（稳定分页），disabled/空配置零行为。
func applySourceQuota(
	candidates []ContentCandidate,
	cfg recpolicy.RecallFusionConfig,
	poolLimit int,
) []ContentCandidate {
	if !cfg.Enabled || len(cfg.SourceQuotaPct) == 0 || len(candidates) == 0 {
		return candidates
	}
	if poolLimit <= 0 {
		poolLimit = len(candidates)
	}
	quotaBySource := make(map[string]int, len(cfg.SourceQuotaPct))
	for source, pct := range cfg.SourceQuotaPct {
		quota := poolLimit * pct / 100
		if quota < 1 {
			quota = 1
		}
		quotaBySource[source] = quota
	}
	countBySource := make(map[string]int, len(quotaBySource))
	out := candidates[:0]
	for _, candidate := range candidates {
		quota, limited := quotaBySource[candidate.RecallPath]
		if limited {
			if countBySource[candidate.RecallPath] >= quota {
				continue
			}
			countBySource[candidate.RecallPath]++
		}
		out = append(out, candidate)
	}
	return out
}

// applyRecallSourceBoost 按 policy 源间校准乘数调整精排分（W9）。
// 未登记的 recallPath 乘数为 1.0（中性）；disabled/空配置零行为。
// boost 只做源间校准，validate 约束 (0,5]，不允许伪造/湮灭单源。
func applyRecallSourceBoost(scored []ScoredCandidate, cfg recpolicy.RecallFusionConfig) {
	if !cfg.Enabled || len(cfg.SourceBoost) == 0 {
		return
	}
	for i := range scored {
		if boost, ok := cfg.SourceBoost[scored[i].Candidate.RecallPath]; ok && boost > 0 {
			scored[i].Score *= boost
		}
	}
}
