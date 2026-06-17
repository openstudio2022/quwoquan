package recommendation

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	app "quwoquan_service/services/content-service/internal/application"
)

// fakeIntersectionCompute 是可计数的底层 compute 源，用于断言读穿透是否回算。
type fakeIntersectionCompute struct {
	mu        sync.Mutex
	factCalls int
	factErr   error
	reasons   []app.IntersectionReasonView
}

func (f *fakeIntersectionCompute) FactReasons(context.Context, string, string) ([]app.IntersectionReasonView, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.factCalls++
	if f.factErr != nil {
		return nil, f.factErr
	}
	return f.reasons, nil
}

func (f *fakeIntersectionCompute) AffinityReasons(context.Context, string, string) ([]app.IntersectionReasonView, error) {
	return []app.IntersectionReasonView{{IntersectionID: "aff", IntersectionClass: "affinity"}}, nil
}

func (f *fakeIntersectionCompute) ObjectReasons(context.Context, string, string, string) ([]app.IntersectionReasonView, error) {
	return []app.IntersectionReasonView{{IntersectionID: "obj", IntersectionClass: "fact"}}, nil
}

// memViewerStore 是内存读模型，避免单测依赖 Mongo/Docker。
type memViewerStore struct {
	mu   sync.Mutex
	docs map[string]ViewerIntersectionDoc
	save int
}

func newMemViewerStore() *memViewerStore { return &memViewerStore{docs: map[string]ViewerIntersectionDoc{}} }

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

func newSourceAt(compute app.IntersectionSource, store ViewerIntersectionReadModel, now *time.Time, ttlDays map[string]int) *ReadModelIntersectionSource {
	s := NewReadModelIntersectionSource(compute, store, ttlDays)
	s.now = func() time.Time { return *now }
	return s
}

func TestReadModelSource_FirstReadComputesAndMaterializes(t *testing.T) {
	now := time.Date(2026, 6, 16, 0, 0, 0, 0, time.UTC)
	compute := &fakeIntersectionCompute{reasons: []app.IntersectionReasonView{
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
	compute := &fakeIntersectionCompute{reasons: []app.IntersectionReasonView{
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
	compute := &fakeIntersectionCompute{reasons: []app.IntersectionReasonView{
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
	compute := &fakeIntersectionCompute{reasons: []app.IntersectionReasonView{
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
