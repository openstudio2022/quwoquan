package intersection

import (
	"context"
	"sync/atomic"
	"testing"
	"time"
)

// countingSource 记录各读通道被调用的次数，并把 affinity reason 的 Strength
// 当作"已物化"输入直出，用于断言读路径不会按候选重复打分。
type countingSource struct {
	factCalls     int32
	affinityCalls int32
	objectCalls   int32
	facts         []IntersectionReasonView
	affinities    []IntersectionReasonView
	object        []IntersectionReasonView
}

func (s *countingSource) FactReasons(context.Context, string, string) ([]IntersectionReasonView, error) {
	atomic.AddInt32(&s.factCalls, 1)
	return s.facts, nil
}

func (s *countingSource) AffinityReasons(context.Context, string, string) ([]IntersectionReasonView, error) {
	atomic.AddInt32(&s.affinityCalls, 1)
	return s.affinities, nil
}

func (s *countingSource) ObjectReasons(context.Context, string, string, string) ([]IntersectionReasonView, error) {
	atomic.AddInt32(&s.objectCalls, 1)
	return s.object, nil
}

// TestIntersectionService_ReadPathZeroSynchronousScoring（R-IX01 不变量）：
// 交集读路径（Feed/List/Summary）只消费读模型通道（FactReasons/AffinityReasons），
// 不得对候选发起同步模型打分（/v1/score）。本测试把"读路径零同步 RPC + affinity
// 分数直出不重算"固化为契约，防止未来回归到把 /v1/score 拉进读路径的错误设计。
func TestIntersectionService_ReadPathZeroSynchronousScoring(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	const materializedStrength = 0.4242
	src := &countingSource{
		facts: []IntersectionReasonView{
			displayReadyFactReason("f1", "relationship", "sharedFollowees", "u1", "person", "陆衡", 2, 0.9),
		},
		affinities: []IntersectionReasonView{
			func() IntersectionReasonView {
				r := displayReadyAffinityReason("aff1", "content", "sharedCircle", "c1", "content", "摄影内容", materializedStrength)
				// 预物化的模型分通过 Strength/modelReasonBucket 携带；读路径只能直出。
				r.Source = "social_circle"
				r.ModelReasonBucket = "affinity:circle_hot"
				return r
			}(),
		},
	}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)
	ctx := context.Background()

	feed, err := svc.Feed(ctx, "viewer1", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}

	// 读路径只对每个读通道发起一次拉取（无 per-candidate 重复打分循环）。
	if got := atomic.LoadInt32(&src.factCalls); got != 1 {
		t.Fatalf("Feed must call FactReasons exactly once, got %d", got)
	}
	if got := atomic.LoadInt32(&src.affinityCalls); got != 1 {
		t.Fatalf("Feed must call AffinityReasons exactly once (no per-candidate re-score), got %d", got)
	}
	if got := atomic.LoadInt32(&src.objectCalls); got != 0 {
		t.Fatalf("Feed must not consult ObjectReasons, got %d calls", got)
	}

	// affinity 模型分必须原样直出，读路径不得重算/覆盖。
	var affStrength float64
	var foundAff bool
	for _, r := range feed {
		if r.IntersectionID == "aff1" {
			affStrength = r.Strength
			foundAff = true
		}
	}
	if !foundAff {
		t.Fatalf("affinity reason must survive read path, got %+v", feed)
	}
	if affStrength != materializedStrength {
		t.Fatalf("affinity Strength must pass through unchanged (no read-path re-score), want %v got %v",
			materializedStrength, affStrength)
	}

	// Summary/List 是事实通道（收件箱），不得拉概率通道或对象通道。
	if _, err := svc.Summary(ctx, "viewer1"); err != nil {
		t.Fatalf("summary: %v", err)
	}
	if _, _, _, err := svc.List(ctx, "viewer1", IntersectionListQuery{Limit: 10}); err != nil {
		t.Fatalf("list: %v", err)
	}
	if got := atomic.LoadInt32(&src.affinityCalls); got != 1 {
		t.Fatalf("Summary/List must not consult AffinityReasons, affinity calls = %d", got)
	}
	if got := atomic.LoadInt32(&src.objectCalls); got != 0 {
		t.Fatalf("Summary/List must not consult ObjectReasons, object calls = %d", got)
	}
}
