package tests

// WP2·T1/T3 contract：事实交集读模型 rm_viewer_object_intersection 必须
// 精确往返 app.IntersectionReasonView 全字段（含云侧 primaryText），且读穿透在
// 保鲜期内零回算（summary/list/feed 热路径不重做社交图谱扫描）。

import (
	"context"
	"log/slog"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/content-service/internal/application"
	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
)

func TestViewerObjectIntersectionStore_RoundTrip(t *testing.T) {
	if mongoDB == nil {
		t.Skip("mongo unavailable")
	}
	ctx := context.Background()
	coll := mongoDB.Collection("rm_viewer_object_intersection")
	_, _ = coll.DeleteMany(ctx, bson.M{"_id": bson.M{"$regex": "^vois_"}})
	t.Cleanup(func() { _, _ = coll.DeleteMany(ctx, bson.M{"_id": bson.M{"$regex": "^vois_"}}) })

	store := recinfra.NewMongoViewerIntersectionStore(mongoDB, slog.Default())
	want := []application.IntersectionReasonView{
		{
			IntersectionID:    "vois_r1",
			IntersectionClass: "fact",
			Dimension:         "identity",
			PrimaryText:       "你们都关注了 张三",
			SecondaryText:     "共同关注 2 人",
			Strength:          0.8,
			// 架构基线 v2：边权 / 生命周期弱标必须随读模型精确往返（读路径零计算消费）。
			EdgeWeight:     0.66,
			LifecycleState: "strengthened",
		},
	}
	if err := store.Save(ctx, recinfra.ViewerIntersectionDoc{ViewerID: "vois_viewer", Reasons: want}); err != nil {
		t.Fatalf("save: %v", err)
	}
	got, found, err := store.Load(ctx, "vois_viewer")
	if err != nil || !found {
		t.Fatalf("load: found=%v err=%v", found, err)
	}
	if len(got.Reasons) != 1 {
		t.Fatalf("expected 1 reason, got %d", len(got.Reasons))
	}
	r := got.Reasons[0]
	if r.IntersectionID != "vois_r1" || r.PrimaryText != "你们都关注了 张三" || r.Dimension != "identity" ||
		r.EdgeWeight != 0.66 || r.LifecycleState != "strengthened" {
		t.Fatalf("reason not round-tripped exactly: %+v", r)
	}
	if got.ComputedAt.IsZero() {
		t.Fatalf("computedAt must be persisted")
	}
}

// countingFactSource 是只计 FactReasons 调用次数的事实源，用于断言读穿透零回算。
type countingFactSource struct {
	calls   int
	reasons []application.IntersectionReasonView
}

func (c *countingFactSource) FactReasons(context.Context, string, string) ([]application.IntersectionReasonView, error) {
	c.calls++
	return c.reasons, nil
}
func (c *countingFactSource) AffinityReasons(context.Context, string, string) ([]application.IntersectionReasonView, error) {
	return nil, nil
}
func (c *countingFactSource) ObjectReasons(context.Context, string, string, string) ([]application.IntersectionReasonView, error) {
	return nil, nil
}

// materializeFactSource 返回带真实信号（strength/points/freshAt）的事实理由，
// 用于断言 ReadModelIntersectionSource 写路径会真算物化 edgeWeight + lifecycle 并固化进 Mongo。
type materializeFactSource struct {
	reasons []application.IntersectionReasonView
}

func (m *materializeFactSource) FactReasons(context.Context, string, string) ([]application.IntersectionReasonView, error) {
	out := make([]application.IntersectionReasonView, len(m.reasons))
	copy(out, m.reasons)
	return out, nil
}
func (m *materializeFactSource) AffinityReasons(context.Context, string, string) ([]application.IntersectionReasonView, error) {
	return nil, nil
}
func (m *materializeFactSource) ObjectReasons(context.Context, string, string, string) ([]application.IntersectionReasonView, error) {
	return nil, nil
}

// TestViewerObjectIntersectionMaterialization_PersistsGraphLifecycle 是切片⑥的 T3 证据：
// 经真实 Mongo 读模型写路径，Graph 边权与 Lifecycle 弱标必须被真算并精确固化、读穿透零回算复现。
func TestViewerObjectIntersectionMaterialization_PersistsGraphLifecycle(t *testing.T) {
	if mongoDB == nil {
		t.Skip("mongo unavailable")
	}
	ctx := context.Background()
	coll := mongoDB.Collection("rm_viewer_object_intersection")
	_, _ = coll.DeleteMany(ctx, bson.M{"_id": bson.M{"$regex": "^voim_"}})
	t.Cleanup(func() { _, _ = coll.DeleteMany(ctx, bson.M{"_id": bson.M{"$regex": "^voim_"}}) })

	now := time.Now().UTC()
	compute := &materializeFactSource{reasons: []application.IntersectionReasonView{
		{
			IntersectionID:    "voim_edge",
			IntersectionClass: "fact",
			Dimension:         "relationship",
			Strength:          0.8,
			FreshAt:           now.Format(time.RFC3339),
			IntersectionPoints: []application.IntersectionPointView{
				{Count: 1}, {Count: 1}, {Count: 1}, {Count: 1},
			},
		},
	}}
	store := recinfra.NewMongoViewerIntersectionStore(mongoDB, slog.Default())
	src := recinfra.NewReadModelIntersectionSource(compute, store, map[string]int{"relationship": 7})

	got, err := src.FactReasons(ctx, "voim_viewer", "")
	if err != nil {
		t.Fatalf("first read: %v", err)
	}
	if len(got) != 1 || got[0].EdgeWeight <= 0 {
		t.Fatalf("materialized edgeWeight must be >0, got %+v", got)
	}
	if got[0].LifecycleState != "new" {
		t.Fatalf("first materialization lifecycle must be new, got %q", got[0].LifecycleState)
	}

	// 直接 Load 校验已固化进 Mongo（读穿透下次零回算即取此快照）。
	doc, found, err := store.Load(ctx, "voim_viewer")
	if err != nil || !found {
		t.Fatalf("load: found=%v err=%v", found, err)
	}
	if doc.Reasons[0].EdgeWeight != got[0].EdgeWeight || doc.Reasons[0].LifecycleState != "new" {
		t.Fatalf("snapshot must persist materialized graph/lifecycle exactly: %+v", doc.Reasons[0])
	}
}

func TestViewerObjectIntersectionReadThrough_FreshHitZeroCompute(t *testing.T) {
	if mongoDB == nil {
		t.Skip("mongo unavailable")
	}
	ctx := context.Background()
	coll := mongoDB.Collection("rm_viewer_object_intersection")
	_, _ = coll.DeleteMany(ctx, bson.M{"_id": bson.M{"$regex": "^voirt_"}})
	t.Cleanup(func() { _, _ = coll.DeleteMany(ctx, bson.M{"_id": bson.M{"$regex": "^voirt_"}}) })

	compute := &countingFactSource{reasons: []application.IntersectionReasonView{
		{IntersectionID: "voirt_r", IntersectionClass: "fact", Dimension: "content"},
	}}
	store := recinfra.NewMongoViewerIntersectionStore(mongoDB, slog.Default())
	src := recinfra.NewReadModelIntersectionSource(compute, store, map[string]int{"content": 7})

	if _, err := src.FactReasons(ctx, "voirt_viewer", ""); err != nil {
		t.Fatalf("first read: %v", err)
	}
	if _, err := src.FactReasons(ctx, "voirt_viewer", ""); err != nil {
		t.Fatalf("second read: %v", err)
	}
	if compute.calls != 1 {
		t.Fatalf("fresh read model hit must serve without recompute; compute calls=%d", compute.calls)
	}
}
