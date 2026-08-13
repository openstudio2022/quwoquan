package bootstrap

import (
	"log/slog"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
)

// newProductionScorer 是生产打分器的唯一装配点（N0-1）。
// 形状固定为 CascadeScorer{Primary: RemoteModelScorer, Fallback: RuleScorer}：
//   - engine 的 policy rule 分桶依赖 cascade.Fallback；
//   - 模型故障/超时由 RuleScorer 兜底，feed 永不因模型不可用而为空；
//   - shadow 采样依赖 *CascadeScorer 类型断言。
//
// 形状由 production_scorer__local_contract_test.go 固定，改动前先改测试。
func newProductionScorer(
	client rtrec.ModelServiceClient,
	timeout time.Duration,
	logger *slog.Logger,
) *rtrec.CascadeScorer {
	remote := rtrec.NewRemoteModelScorer(client, "content_feed")
	cascade := rtrec.NewCascadeScorer(remote, &rtrec.RuleScorer{}, timeout)
	cascade.Logger = logger
	return cascade
}
