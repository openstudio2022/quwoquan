package recommendation

// N0-1 契约：CascadeScorer 降级语义与 engine 真实 scorer 路径上报。
// 断言三件事：
//  1. Primary 失败时 ScoreBatchWithPath 返回 usedFallback=true 且结果来自 Fallback；
//  2. model 分桶下模型故障时 GetFeed 仍返回非空 items（RuleScorer 兜底，feed 永不空）；
//  3. 降级被计入 ModelFallbacks（model_fallback_rate 的真实分子）。

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/runtime/recpolicy"
)

// failingModelScorer 复用 engine__local_contract_test.go 中的声明。

func TestCascadeScorer_ScoreBatchWithPath_FallbackOnPrimaryError(t *testing.T) {
	cascade := NewCascadeScorer(&failingModelScorer{}, &RuleScorer{}, 50*time.Millisecond)

	candidates := []ContentCandidate{
		{ContentID: "c1", ContentType: "photo", PublishedAt: time.Now()},
	}
	features := &ScoringFeatures{Session: &SessionState{}}

	scored, usedFallback, err := cascade.ScoreBatchWithPath(context.Background(), features, candidates)
	if err != nil {
		t.Fatalf("fallback path must not error: %v", err)
	}
	if !usedFallback {
		t.Fatal("usedFallback must be true when primary fails")
	}
	if len(scored) != 1 {
		t.Fatalf("fallback must score all candidates, got %d", len(scored))
	}
}

func TestCascadeScorer_ScoreBatchWithPath_NoFallbackOnSuccess(t *testing.T) {
	cascade := NewCascadeScorer(&RuleScorer{}, &failingModelScorer{}, 50*time.Millisecond)

	candidates := []ContentCandidate{
		{ContentID: "c1", ContentType: "photo", PublishedAt: time.Now()},
	}
	features := &ScoringFeatures{Session: &SessionState{}}

	_, usedFallback, err := cascade.ScoreBatchWithPath(context.Background(), features, candidates)
	if err != nil {
		t.Fatalf("primary success must not error: %v", err)
	}
	if usedFallback {
		t.Fatal("usedFallback must be false when primary succeeds")
	}
}

// model 分桶 100% + 模型故障：feed 仍由 RuleScorer 供给（非空），
// 且 ModelFallbacks 计数增加。这是 N0 完成判据的 local_contract 版。
func TestEngine_GetFeed_ModelFailure_ServesRuleFallbackFeed(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	source := &mockCandidateSource{
		candidates: []ContentCandidate{
			{ContentID: "c1", ContentType: "photo", PublishedAt: time.Now()},
			{ContentID: "c2", ContentType: "video", PublishedAt: time.Now()},
		},
	}

	allModelPolicy := testPolicyStore(func(p *recpolicy.RecPolicy) {
		p.Scorer.ExploreFraction = 0
		for i := range p.Experiments {
			if p.Experiments[i].ID == recpolicy.ExpModelVsRule {
				p.Experiments[i].Enabled = true
				p.Experiments[i].Buckets = []recpolicy.ExperimentBucket{
					{Name: "model", WeightPct: 100},
					{Name: "rule", WeightPct: 0},
				}
			}
		}
	})

	cascade := NewCascadeScorer(&failingModelScorer{}, &RuleScorer{}, 50*time.Millisecond)
	engine := NewEngine(hp, []CandidateSource{source},
		WithScorer(cascade),
		WithPolicyStore(allModelPolicy),
	)

	fallbacksBefore := GlobalEngagementMetrics.ModelFallbacks.Load()

	resp, err := engine.GetFeed(ctx, GetFeedRequest{UserID: "u1", SessionID: "s1", Limit: 10})
	if err != nil {
		t.Fatalf("GetFeed must not fail on model outage: %v", err)
	}
	if len(resp.Items) == 0 {
		t.Fatal("feed must be served by RuleScorer fallback, got empty feed")
	}
	if got := GlobalEngagementMetrics.ModelFallbacks.Load(); got <= fallbacksBefore {
		t.Fatalf("ModelFallbacks must increase on cascade fallback, before=%d after=%d", fallbacksBefore, got)
	}
}
