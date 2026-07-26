package recommendation_test

import (
	"context"
	"errors"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"sync"
	"testing"
	"time"

	intersectionapp "quwoquan_service/services/content-service/internal/content/post/application/intersection"
)

// fakeIntersectionCompute 是可计数的底层 compute 源，用于断言读穿透是否回算。
type fakeIntersectionCompute struct {
	mu        sync.Mutex
	factCalls int
	factErr   error
	reasons   []intersectionapp.IntersectionReasonView
}

func (f *fakeIntersectionCompute) FactReasons(context.Context, string, string) ([]intersectionapp.IntersectionReasonView, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.factCalls++
	if f.factErr != nil {
		return nil, f.factErr
	}
	return f.reasons, nil
}

func (f *fakeIntersectionCompute) AffinityReasons(context.Context, string, string) ([]intersectionapp.IntersectionReasonView, error) {
	return []intersectionapp.IntersectionReasonView{{IntersectionID: "aff", IntersectionClass: "affinity"}}, nil
}

func (f *fakeIntersectionCompute) ObjectReasons(context.Context, string, string, string) ([]intersectionapp.IntersectionReasonView, error) {
	return []intersectionapp.IntersectionReasonView{{IntersectionID: "obj", IntersectionClass: "fact"}}, nil
}

// memViewerStore 是内存读模型，避免单测依赖 Mongo/Docker。
type memViewerStore struct {
	mu   sync.Mutex
	docs map[string]ViewerIntersectionDoc
	save int
}

func newMemViewerStore() *memViewerStore {
	return &memViewerStore{docs: map[string]ViewerIntersectionDoc{}}
}

func (m *memViewerStore) Load(_ context.Context, viewerID string) (ViewerIntersectionDoc, bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	doc, ok := m.docs[viewerID]
	return doc, ok, nil
}

func (m *memViewerStore) Save(_ context.Context, doc ViewerIntersectionDoc) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.save++
	m.docs[doc.ViewerID] = doc
	return nil
}

func newSourceAt(compute intersectionapp.IntersectionSource, store ViewerIntersectionReadModel, now *time.Time, ttlDays map[string]int) *ReadModelIntersectionSource {
	s := NewReadModelIntersectionSource(compute, store, ttlDays)
	s.SetNow(func() time.Time { return *now })
	return s
}

func TestReadModelSource_FirstReadComputesAndMaterializes(t *testing.T) {
	now := time.Date(2026, 6, 16, 0, 0, 0, 0, time.UTC)
	compute := &fakeIntersectionCompute{reasons: []intersectionapp.IntersectionReasonView{
		{IntersectionID: "r1", IntersectionClass: "fact", Dimension: "content"},
	}}
	store := newMemViewerStore()
	src := newSourceAt(compute, store, &now, map[string]int{"content": 7})

	got, err := src.FactReasons(context.Background(), "viewer-1", "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 1 || got[0].IntersectionID != "r1" {
		t.Fatalf("unexpected reasons: %+v", got)
	}
	if compute.factCalls != 1 {
		t.Fatalf("expected 1 compute call, got %d", compute.factCalls)
	}
	if store.save != 1 {
		t.Fatalf("expected snapshot materialized once, got %d", store.save)
	}
}

func TestReadModelSource_FreshHitServesReadModelZeroCompute(t *testing.T) {
	now := time.Date(2026, 6, 16, 0, 0, 0, 0, time.UTC)
	compute := &fakeIntersectionCompute{reasons: []intersectionapp.IntersectionReasonView{
		{IntersectionID: "r1", IntersectionClass: "fact", Dimension: "content"},
	}}
	store := newMemViewerStore()
	src := newSourceAt(compute, store, &now, map[string]int{"content": 7})

	if _, err := src.FactReasons(context.Background(), "v", ""); err != nil {
		t.Fatalf("seed compute failed: %v", err)
	}
	// 3 天后（content TTL=7d 内）：必须直出读模型，零回算。
	now = now.Add(3 * 24 * time.Hour)
	got, err := src.FactReasons(context.Background(), "v", "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("expected cached reasons, got %+v", got)
	}
	if compute.factCalls != 1 {
		t.Fatalf("fresh hit must not recompute; compute calls=%d", compute.factCalls)
	}
}

func TestReadModelSource_PerDimensionFreshnessTriggersRecompute(t *testing.T) {
	now := time.Date(2026, 6, 16, 0, 0, 0, 0, time.UTC)
	// 快照含 content(7d) 与 identity(30d) 两维度：按最短者 content 7d 触发整快照刷新。
	compute := &fakeIntersectionCompute{reasons: []intersectionapp.IntersectionReasonView{
		{IntersectionID: "c1", IntersectionClass: "fact", Dimension: "content"},
		{IntersectionID: "i1", IntersectionClass: "fact", Dimension: "identity"},
	}}
	store := newMemViewerStore()
	src := newSourceAt(compute, store, &now, map[string]int{"content": 7, "identity": 30})

	if _, err := src.FactReasons(context.Background(), "v", ""); err != nil {
		t.Fatalf("seed failed: %v", err)
	}
	// 8 天后：content 维已过保鲜（7d），即便 identity 仍新鲜，也必须整快照重算。
	now = now.Add(8 * 24 * time.Hour)
	if _, err := src.FactReasons(context.Background(), "v", ""); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if compute.factCalls != 2 {
		t.Fatalf("expired most-perishable dimension must recompute; compute calls=%d", compute.factCalls)
	}
	if store.save != 2 {
		t.Fatalf("recompute must re-materialize; saves=%d", store.save)
	}
}

func TestReadModelSource_ComputeErrorServesStaleSnapshot(t *testing.T) {
	now := time.Date(2026, 6, 16, 0, 0, 0, 0, time.UTC)
	compute := &fakeIntersectionCompute{reasons: []intersectionapp.IntersectionReasonView{
		{IntersectionID: "r1", IntersectionClass: "fact", Dimension: "content"},
	}}
	store := newMemViewerStore()
	src := newSourceAt(compute, store, &now, map[string]int{"content": 7})

	if _, err := src.FactReasons(context.Background(), "v", ""); err != nil {
		t.Fatalf("seed failed: %v", err)
	}
	// 过期后底层重算失败：必须回落上一次良好快照而非空窗。
	now = now.Add(10 * 24 * time.Hour)
	compute.factErr = errors.New("upstream graph timeout")
	got, err := src.FactReasons(context.Background(), "v", "")
	if err != nil {
		t.Fatalf("stale fallback must not surface error: %v", err)
	}
	if len(got) != 1 || got[0].IntersectionID != "r1" {
		t.Fatalf("expected stale snapshot served, got %+v", got)
	}
}

func TestReadModelSource_AffinityAndObjectDelegateToCompute(t *testing.T) {
	now := time.Date(2026, 6, 16, 0, 0, 0, 0, time.UTC)
	compute := &fakeIntersectionCompute{}
	src := newSourceAt(compute, newMemViewerStore(), &now, nil)

	aff, err := src.AffinityReasons(context.Background(), "v", "")
	if err != nil || len(aff) != 1 || aff[0].IntersectionClass != "affinity" {
		t.Fatalf("affinity must delegate to compute: %+v err=%v", aff, err)
	}
	obj, err := src.ObjectReasons(context.Background(), "v", "obj-1", "circle")
	if err != nil || len(obj) != 1 || obj[0].IntersectionID != "obj" {
		t.Fatalf("object must delegate to compute: %+v err=%v", obj, err)
	}
}

// factReasonsForGen 让 fakeIntersectionCompute 在每次重算返回不同代的理由，
// 用于断言 lifecycle 跨快照的增量真算。
type genCompute struct {
	calls int
	gens  [][]intersectionapp.IntersectionReasonView
}

func (g *genCompute) FactReasons(context.Context, string, string) ([]intersectionapp.IntersectionReasonView, error) {
	idx := g.calls
	if idx >= len(g.gens) {
		idx = len(g.gens) - 1
	}
	g.calls++
	// 返回深拷贝，避免物化原地写回污染下一代输入。
	src := g.gens[idx]
	out := make([]intersectionapp.IntersectionReasonView, len(src))
	copy(out, src)
	return out, nil
}
func (g *genCompute) AffinityReasons(context.Context, string, string) ([]intersectionapp.IntersectionReasonView, error) {
	return nil, nil
}
func (g *genCompute) ObjectReasons(context.Context, string, string, string) ([]intersectionapp.IntersectionReasonView, error) {
	return nil, nil
}

// TestReadModelSource_MaterializesEdgeWeightAndLifecycleAcrossRecompute 是切片⑥的端内
// 物化证据：经 ReadModelIntersectionSource 写路径，edgeWeight 与 lifecycle 弱标必须被真算
// 并随快照固化；fresh 命中读路径零回算地消费已物化字段（R-IX01 不变量）。
func TestReadModelSource_MaterializesEdgeWeightAndLifecycleAcrossRecompute(t *testing.T) {
	now := time.Date(2026, 6, 16, 0, 0, 0, 0, time.UTC)
	mk := func(strength float64, pts int) intersectionapp.IntersectionReasonView {
		points := make([]intersectionapp.IntersectionPointView, pts)
		for i := range points {
			points[i] = intersectionapp.IntersectionPointView{Count: 1}
		}
		return intersectionapp.IntersectionReasonView{
			IntersectionID:     "edge-1",
			IntersectionClass:  "fact",
			Dimension:          "relationship",
			Strength:           strength,
			FreshAt:            now.Format(time.RFC3339),
			IntersectionPoints: points,
		}
	}
	compute := &genCompute{gens: [][]intersectionapp.IntersectionReasonView{
		{mk(0.6, 1)},  // 第 1 代：弱边
		{mk(1.0, 12)}, // 第 2 代：显著增强
	}}
	store := newMemViewerStore()
	src := newSourceAt(compute, store, &now, map[string]int{"relationship": 7})

	// 第一次读：真算物化，edgeWeight>0，lifecycle=new。
	gen1, err := src.FactReasons(context.Background(), "v", "")
	if err != nil {
		t.Fatalf("gen1: %v", err)
	}
	if gen1[0].EdgeWeight <= 0 {
		t.Fatalf("edgeWeight must be materialized >0, got %.4f", gen1[0].EdgeWeight)
	}
	if gen1[0].LifecycleState != "new" {
		t.Fatalf("first materialization lifecycle must be new, got %q", gen1[0].LifecycleState)
	}
	// 已固化进快照。
	if doc, ok, _ := store.Load(context.Background(), "v"); !ok || doc.Reasons[0].EdgeWeight <= 0 {
		t.Fatalf("snapshot must persist materialized edgeWeight: %+v", doc)
	}

	// fresh 命中（TTL 内）：零回算，消费已物化字段。
	now = now.Add(2 * 24 * time.Hour)
	hit, err := src.FactReasons(context.Background(), "v", "")
	if err != nil {
		t.Fatalf("fresh hit: %v", err)
	}
	if compute.calls != 1 {
		t.Fatalf("fresh hit must not recompute; calls=%d", compute.calls)
	}
	if hit[0].LifecycleState != "new" || hit[0].EdgeWeight != gen1[0].EdgeWeight {
		t.Fatalf("fresh hit must serve materialized snapshot verbatim: %+v", hit[0])
	}

	// 过 TTL 后重算：lifecycle 基于上一次快照增量 → strengthened，previousStrength = 上一次 edgeWeight。
	now = now.Add(8 * 24 * time.Hour)
	gen2, err := src.FactReasons(context.Background(), "v", "")
	if err != nil {
		t.Fatalf("gen2: %v", err)
	}
	if compute.calls != 2 {
		t.Fatalf("expired snapshot must recompute; calls=%d", compute.calls)
	}
	if gen2[0].LifecycleState != "strengthened" {
		t.Fatalf("rising edge across recompute must be strengthened, got %q (delta=%.4f)", gen2[0].LifecycleState, gen2[0].StrengthDelta)
	}
	if gen2[0].PreviousStrength != gen1[0].EdgeWeight {
		t.Fatalf("previousStrength must equal prior materialized edgeWeight: got %.4f want %.4f", gen2[0].PreviousStrength, gen1[0].EdgeWeight)
	}
	if gen2[0].EdgeWeight <= gen1[0].EdgeWeight {
		t.Fatalf("strengthened edge must have higher edgeWeight: gen1=%.4f gen2=%.4f", gen1[0].EdgeWeight, gen2[0].EdgeWeight)
	}
}
