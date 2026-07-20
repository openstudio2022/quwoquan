package main

import rtrec "quwoquan_service/runtime/recommendation"

// recommendationCandidateSources 选择唯一候选事实轨。
// Mongo 物化召回可用时，禁止再并入 posts fallback：两者对同一内容的 viewCount
// 新鲜度不同，pre-rank 后去重会让陈旧候选覆盖新鲜候选。fallback 只服务无 Mongo
// 的本地/降级装配。
func recommendationCandidateSources(
	materialized []rtrec.CandidateSource,
	fallback rtrec.CandidateSource,
) []rtrec.CandidateSource {
	if len(materialized) > 0 {
		return append([]rtrec.CandidateSource(nil), materialized...)
	}
	if fallback == nil {
		return nil
	}
	return []rtrec.CandidateSource{fallback}
}
