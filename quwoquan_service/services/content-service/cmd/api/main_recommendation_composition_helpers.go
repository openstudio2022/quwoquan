package bootstrap

import (
	"context"
	"log"
	"log/slog"
	"os"

	rtrec "quwoquan_service/runtime/recommendation"
	rtrecpolicy "quwoquan_service/runtime/recpolicy"
)

// startRecommendationPolicyHotReload 启动策略文件热加载；
// policyStore 的具体实现仍由 main 显式选择。
func startRecommendationPolicyHotReload(
	workers *workerRegistry,
	policyStore *rtrecpolicy.Store,
	logger *slog.Logger,
) {
	policyPath := os.Getenv("QWQ_REC_POLICY_PATH")
	if policyPath == "" {
		policyPath = "services/content-service/resources/policies/content/post/recommendation_policy.yaml"
	}
	if _, statErr := os.Stat(policyPath); statErr == nil {
		workers.Add(func(ctx context.Context) {
			rtrecpolicy.StartSyncLoop(ctx, policyStore, logger, rtrecpolicy.SyncConfig{
				Path:     policyPath,
				OnReload: rtrec.RecordPolicyReload,
			})
		})
		log.Printf(
			"content-service rec policy hot-reload enabled path=%s baselineDigest=%s",
			policyPath,
			policyStore.EffectiveHash(),
		)
	} else {
		log.Printf(
			"content-service rec policy using codegen baselineDigest=%s (no live file at %s)",
			policyStore.EffectiveHash(),
			policyPath,
		)
	}
}
