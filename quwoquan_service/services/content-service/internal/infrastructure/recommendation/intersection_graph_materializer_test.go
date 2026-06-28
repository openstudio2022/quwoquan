package recommendation

import (
	"math"
	"testing"
	"time"

	intersectionapp "quwoquan_service/services/content-service/internal/application/intersection"
)

func approxEqual(a, b float64) bool { return math.Abs(a-b) < 1e-4 }

// TestComputeEdgeWeight_ThreeFactorProduct 验证边权 = 关系强度 × 交互频率 × 新鲜度衰减，
// 且全部由理由自身真实信号确定性派生（无外部打分调用）。
func TestComputeEdgeWeight_ThreeFactorProduct(t *testing.T) {
	now := time.Date(2026, 6, 16, 0, 0, 0, 0, time.UTC)
	r := intersectionapp.IntersectionReasonView{
		Strength: 0.8,
		FreshAt:  now.Format(time.RFC3339), // 刚生成 → decay=1
		IntersectionPoints: []intersectionapp.IntersectionPointView{
			{Count: 1}, {Count: 1}, {Count: 1}, // 绝对多跳计数 3
		},
	}
	freq := 1 - math.Exp(-3.0/interactionSaturation)
	want := 0.8 * freq * 1.0
	got := computeEdgeWeight(r, now)
	if !approxEqual(got, want) {
		t.Fatalf("edgeWeight = %.4f, want %.4f (strength×freq×decay)", got, want)
	}
	if got <= 0 || got > 1 {
		t.Fatalf("edgeWeight out of (0,1]: %.4f", got)
	}
}

// TestRecencyDecay_OldEdgeDecays 验证陈旧边权随半衰期衰减、且不破 floor。
func TestRecencyDecay_OldEdgeDecays(t *testing.T) {
	now := time.Date(2026, 6, 16, 0, 0, 0, 0, time.UTC)
	fresh := now.Format(time.RFC3339)
	old := now.Add(-edgeRecencyHalfLife).Format(time.RFC3339) // 正好一个半衰期

	if d := recencyDecay(fresh, now); !approxEqual(d, 1.0) {
		t.Fatalf("fresh decay = %.4f, want 1.0", d)
	}
	if d := recencyDecay(old, now); !approxEqual(d, 0.5) {
		t.Fatalf("half-life decay = %.4f, want 0.5", d)
	}
	veryOld := now.Add(-100 * edgeRecencyHalfLife).Format(time.RFC3339)
	if d := recencyDecay(veryOld, now); d != edgeRecencyFloor {
		t.Fatalf("very old decay = %.4f, want floor %.4f", d, edgeRecencyFloor)
	}
	if d := recencyDecay("", now); d != 1.0 {
		t.Fatalf("missing freshAt must default decay=1.0, got %.4f", d)
	}
}

// TestInteractionFrequency_AbsoluteMultiHopCount 验证 Propagation：频率单调随绝对多跳计数增长、收敛 <1。
func TestInteractionFrequency_AbsoluteMultiHopCount(t *testing.T) {
	mk := func(count int) intersectionapp.IntersectionReasonView {
		pts := make([]intersectionapp.IntersectionPointView, count)
		for i := range pts {
			pts[i] = intersectionapp.IntersectionPointView{Count: 1}
		}
		return intersectionapp.IntersectionReasonView{IntersectionPoints: pts}
	}
	f1 := interactionFrequency(mk(1))
	f3 := interactionFrequency(mk(3))
	f10 := interactionFrequency(mk(10))
	if !(f1 < f3 && f3 < f10) {
		t.Fatalf("frequency must increase with multi-hop count: f1=%.4f f3=%.4f f10=%.4f", f1, f3, f10)
	}
	if f10 >= 1.0 {
		t.Fatalf("saturating frequency must stay <1: f10=%.4f", f10)
	}
	if f0 := interactionFrequency(intersectionapp.IntersectionReasonView{}); f0 != 0 {
		t.Fatalf("zero evidence → zero frequency, got %.4f", f0)
	}
}

// TestEvidenceCount_PrefersPointSum 验证多跳证据计数取点 Count 求和，回退聚合计数。
func TestEvidenceCount_PrefersPointSum(t *testing.T) {
	r := intersectionapp.IntersectionReasonView{
		IntersectionPoints: []intersectionapp.IntersectionPointView{{Count: 2}, {Count: 3}},
		TotalPointCount:    99,
	}
	if n := evidenceCount(r); n != 5 {
		t.Fatalf("point sum should win: got %d want 5", n)
	}
	fallback := intersectionapp.IntersectionReasonView{TotalPointCount: 4, MutualCount: 7, FactPointCount: 2}
	if n := evidenceCount(fallback); n != 7 {
		t.Fatalf("fallback should be max(total,mutual,fact): got %d want 7", n)
	}
}

// TestMaterializeFactReasons_LifecycleStateMachine 覆盖生命周期五态：new/strengthened/stable/weakened/reactivated。
func TestMaterializeFactReasons_LifecycleStateMachine(t *testing.T) {
	now := time.Date(2026, 6, 16, 0, 0, 0, 0, time.UTC)

	// 第一次：无 prev → 全部 new。
	r := func(id string, strength float64, pts int) intersectionapp.IntersectionReasonView {
		points := make([]intersectionapp.IntersectionPointView, pts)
		for i := range points {
			points[i] = intersectionapp.IntersectionPointView{Count: 1}
		}
		return intersectionapp.IntersectionReasonView{
			IntersectionID:     id,
			Strength:           strength,
			FreshAt:            now.Format(time.RFC3339),
			IntersectionPoints: points,
		}
	}
	gen1 := materializeFactReasons(nil, []intersectionapp.IntersectionReasonView{r("e1", 0.8, 3)}, now)
	if gen1[0].LifecycleState != "new" {
		t.Fatalf("first appearance must be new, got %q", gen1[0].LifecycleState)
	}
	if gen1[0].PreviousStrength != 0 {
		t.Fatalf("new edge previousStrength must be 0, got %.4f", gen1[0].PreviousStrength)
	}

	// 第二次：边权显著上升 → strengthened。
	gen2 := materializeFactReasons(gen1, []intersectionapp.IntersectionReasonView{r("e1", 1.0, 10)}, now)
	if gen2[0].LifecycleState != "strengthened" {
		t.Fatalf("rising edge must be strengthened, got %q (delta=%.4f)", gen2[0].LifecycleState, gen2[0].StrengthDelta)
	}
	if gen2[0].PreviousStrength != gen1[0].EdgeWeight {
		t.Fatalf("previousStrength must equal prior edgeWeight: got %.4f want %.4f", gen2[0].PreviousStrength, gen1[0].EdgeWeight)
	}

	// 第三次：边权基本不变 → stable。
	gen3 := materializeFactReasons(gen2, []intersectionapp.IntersectionReasonView{r("e1", 1.0, 10)}, now)
	if gen3[0].LifecycleState != "stable" {
		t.Fatalf("unchanged edge must be stable, got %q (delta=%.4f)", gen3[0].LifecycleState, gen3[0].StrengthDelta)
	}

	// 第四次：边权显著下降 → weakened。
	gen4 := materializeFactReasons(gen3, []intersectionapp.IntersectionReasonView{r("e1", 0.55, 1)}, now)
	if gen4[0].LifecycleState != "weakened" {
		t.Fatalf("falling edge must be weakened, got %q (delta=%.4f)", gen4[0].LifecycleState, gen4[0].StrengthDelta)
	}

	// 第五次：曾衰退、本轮重新增强 → reactivated。
	gen5 := materializeFactReasons(gen4, []intersectionapp.IntersectionReasonView{r("e1", 1.0, 10)}, now)
	if gen5[0].LifecycleState != "reactivated" {
		t.Fatalf("re-rising after weakened must be reactivated, got %q (delta=%.4f)", gen5[0].LifecycleState, gen5[0].StrengthDelta)
	}
}

// TestApplyGraphWeights_DeterministicAndBounded 验证边权物化幂等、确定性、有界。
func TestApplyGraphWeights_DeterministicAndBounded(t *testing.T) {
	now := time.Date(2026, 6, 16, 0, 0, 0, 0, time.UTC)
	in := []intersectionapp.IntersectionReasonView{
		{IntersectionID: "a", Strength: 0.9, FreshAt: now.Format(time.RFC3339), TotalPointCount: 4},
		{IntersectionID: "b"}, // 无信号
	}
	first := applyGraphWeights(append([]intersectionapp.IntersectionReasonView(nil), in...), now)
	second := applyGraphWeights(append([]intersectionapp.IntersectionReasonView(nil), in...), now)
	for i := range first {
		if first[i].EdgeWeight != second[i].EdgeWeight {
			t.Fatalf("edgeWeight must be deterministic at idx %d: %.4f vs %.4f", i, first[i].EdgeWeight, second[i].EdgeWeight)
		}
		if first[i].EdgeWeight < 0 || first[i].EdgeWeight > 1 {
			t.Fatalf("edgeWeight out of [0,1] at idx %d: %.4f", i, first[i].EdgeWeight)
		}
	}
	if first[1].EdgeWeight != 0 {
		t.Fatalf("signal-less reason must yield 0 edgeWeight, got %.4f", first[1].EdgeWeight)
	}
}

// TestReasonIdentityKey_StableMatching 验证跨快照同一条边的稳定匹配键优先级。
func TestReasonIdentityKey_StableMatching(t *testing.T) {
	if k := reasonIdentityKey(intersectionapp.IntersectionReasonView{DedupeKey: "dk", IntersectionID: "ix"}); k != "d:dk" {
		t.Fatalf("dedupeKey must win, got %q", k)
	}
	if k := reasonIdentityKey(intersectionapp.IntersectionReasonView{IntersectionID: "ix"}); k != "i:ix" {
		t.Fatalf("intersectionId fallback, got %q", k)
	}
	if k := reasonIdentityKey(intersectionapp.IntersectionReasonView{ActionTargetID: "at"}); k != "a:at" {
		t.Fatalf("actionTargetId fallback, got %q", k)
	}
	if k := reasonIdentityKey(intersectionapp.IntersectionReasonView{Dimension: "d", DisplayName: "n"}); k != "n:d|n" {
		t.Fatalf("last-resort key, got %q", k)
	}
}
