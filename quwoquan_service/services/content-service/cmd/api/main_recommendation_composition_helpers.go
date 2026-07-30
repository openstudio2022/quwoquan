package main

import (
	"context"
	"log"
	"log/slog"
	"os"

	rtrec "quwoquan_service/runtime/recommendation"
	rtrecpolicy "quwoquan_service/runtime/recpolicy"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

// applyRecommendationCandidateGates 只对 main 已显式选择的候选源应用固定门禁。
func applyRecommendationCandidateGates(
	rawCandidateSources []rtrec.CandidateSource,
	accountRestrictions ...recinfra.AccountRestrictionReader,
) []rtrec.CandidateSource {
	var restrictionReader recinfra.AccountRestrictionReader
	if len(accountRestrictions) > 0 {
		restrictionReader = accountRestrictions[0]
	}
	candidateSources := make([]rtrec.CandidateSource, 0, len(rawCandidateSources))
	for _, candidateSource := range rawCandidateSources {
		// 类型判定必须基于原始源：门禁嵌套包装后类型断言会失效。
		_, isAuthorRecall := candidateSource.(*recinfra.AuthorRecallSource)
		gated := recinfra.GatePremiumStreamSource(candidateSource)
		if gated == nil {
			continue
		}
		gated = recinfra.GateFollowFeedSource(gated, isAuthorRecall)
		if restrictionReader != nil {
			gated = recinfra.GateAccountRestrictedSource(
				gated,
				restrictionReader,
			)
		}
		candidateSources = append(candidateSources, gated)
	}
	return candidateSources
}

// startRecommendationPolicyHotReload 启动策略文件热加载；
// policyStore 的具体实现仍由 main 显式选择。
func startRecommendationPolicyHotReload(
	ctx context.Context,
	policyStore *rtrecpolicy.Store,
	logger *slog.Logger,
) {
	policyPath := os.Getenv("QWQ_REC_POLICY_PATH")
	if policyPath == "" {
		policyPath = "services/content-service/resources/policies/content/post/recommendation_policy.yaml"
	}
	if _, statErr := os.Stat(policyPath); statErr == nil {
		go rtrecpolicy.StartSyncLoop(ctx, policyStore, logger, rtrecpolicy.SyncConfig{
			Path:     policyPath,
			OnReload: rtrec.RecordPolicyReload,
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
