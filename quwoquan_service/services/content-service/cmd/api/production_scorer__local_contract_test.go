package main

// 装配级契约测试（N0-1）：生产 scorer 必须是 CascadeScorer{Primary: RemoteModelScorer,
// Fallback: RuleScorer}。此前 main.go 直接 WithScorer(remoteScorer) 裸装配，导致：
// ① policy rule 分桶失效（engine 找不到 CascadeScorer.Fallback）；
// ② 模型故障时无 RuleScorer 兜底 → 空 feed；
// ③ shadow 采样的 *CascadeScorer 类型断言永不通过 → LTR 对比样本零积累。
// 本测试固定生产装配形状，防止再次回退为裸 scorer。

import (
	"context"
	"log/slog"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
)

type stubModelServiceClient struct{}

func (stubModelServiceClient) Predict(_ context.Context, _ *rtrec.ModelPredictRequest) (*rtrec.ModelPredictResponse, error) {
	return &rtrec.ModelPredictResponse{}, nil
}

func TestNewProductionScorer_ShapeIsCascadeWithRuleFallback(t *testing.T) {
	scorer := newProductionScorer(stubModelServiceClient{}, 50*time.Millisecond, slog.Default())

	if scorer == nil {
		t.Fatal("newProductionScorer returned nil")
	}
	if _, ok := scorer.Primary.(*rtrec.RemoteModelScorer); !ok {
		t.Fatalf("Primary must be *RemoteModelScorer, got %T", scorer.Primary)
	}
	if _, ok := scorer.Fallback.(*rtrec.RuleScorer); !ok {
		t.Fatalf("Fallback must be *RuleScorer, got %T", scorer.Fallback)
	}
	if scorer.Timeout <= 0 {
		t.Fatalf("Timeout must be positive, got %v", scorer.Timeout)
	}
	if scorer.Logger == nil {
		t.Fatal("Logger must be set so cascade fallbacks are observable")
	}
}

// 防再犯：ModelScorer 接口层面上 CascadeScorer 必须可被 engine 的
// *CascadeScorer 类型断言命中（shadow 采样与 rule 分桶都依赖该断言）。
func TestNewProductionScorer_SatisfiesEngineCascadeAssertion(t *testing.T) {
	var scorer rtrec.ModelScorer = newProductionScorer(stubModelServiceClient{}, 50*time.Millisecond, slog.Default())
	if _, ok := scorer.(*rtrec.CascadeScorer); !ok {
		t.Fatalf("production scorer must be *CascadeScorer for engine bucket/shadow logic, got %T", scorer)
	}
}
