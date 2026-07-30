package intersection_test

import (
	"context"
	"testing"
	"time"

	generated "quwoquan_service/services/content-service/generated/content/post"
	. "quwoquan_service/services/content-service/internal/content/post/application/intersection"
)

// deferredKind 取注册表里任意一个 status: deferred 的 kind。
// 不硬编码具体 kind：deferred 集合会随 producer 逐批落地而收缩，
// 测试要断言的是「deferred 一律不下发」这条不变量，而不是某个 kind 的当前状态。
func deferredKind(t *testing.T) string {
	t.Helper()
	for _, kind := range []string{
		"coVisitedEntity", "followeeVisited", "sameSchool", "sameCompany",
		"coPresentHere", "nearbyAffinity", "coPlannedTrip", "coCreatedContent",
	} {
		if _, ok := generated.IntersectionDeferredKinds[kind]; ok {
			return kind
		}
	}
	t.Fatal("registry has no deferred kind left; remove or replace the obsolete deferred-kind acceptance deliberately")
	return ""
}

func deferredReason(t *testing.T, id string) IntersectionReasonView {
	t.Helper()
	r := displayReadyFactReason(
		id, "location", deferredKind(t), westLakeHomepageID,
		"place", "西湖", 1, 0.9,
	)
	r.RelationObjectID = westLakeHomepageID
	return withDisplayStatement(r, "西湖", "林清越", "actor_"+id)
}

// deferred kind 在四个入口都不下发：注册表把 kind 标为 deferred 表示可证数据源缺位，
// 禁止产出。这条不变量不能依赖「恰好没有 producer」——一旦有人写了 producer 或
// 读模型里残留历史数据，服务边界必须仍然拦住。
func TestDeferredKindGate_NeverDeliveredOnAnySurface(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	src := stubSource{
		facts:  []IntersectionReasonView{freshReason(deferredReason(t, "ix_deferred"), now)},
		object: []IntersectionReasonView{freshReason(deferredReason(t, "ix_deferred"), now)},
	}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)
	ctx := context.Background()

	feed, err := svc.Feed(ctx, "u_viewer", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	if len(feed) != 0 {
		t.Fatalf("feed must drop deferred kind, got %d reasons", len(feed))
	}

	list, _, _, err := svc.List(ctx, "u_viewer", IntersectionListQuery{})
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(list) != 0 {
		t.Fatalf("inbox must drop deferred kind, got %d reasons", len(list))
	}

	object, err := svc.ObjectIntersections(ctx, "u_viewer", westLakeHomepageID, "entity", 10)
	if err != nil {
		t.Fatalf("object intersections: %v", err)
	}
	if len(object) != 0 {
		t.Fatalf("object page must drop deferred kind, got %d reasons", len(object))
	}

	sum, err := svc.Summary(ctx, "u_viewer")
	if err != nil {
		t.Fatalf("summary: %v", err)
	}
	if sum.TotalCount != 0 || len(sum.Dimensions) != 0 {
		t.Fatalf(
			"red dot must not count deferred kind: total=%d dims=%+v",
			sum.TotalCount, sum.Dimensions,
		)
	}
}

// deferred 判定不因探针可用性而松动：冷启动供给闸门在探针缺失时 fail-open，
// 但诚实红线不是可观测能力的函数。
func TestDeferredKindGate_HoldsWithoutSupplyProbe(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	probe := newStubSupplyProbe(nil)
	probe.err = context.DeadlineExceeded
	src := stubSource{
		facts: []IntersectionReasonView{freshReason(deferredReason(t, "ix_deferred"), now)},
	}
	svc := NewIntersectionService(
		newTestRouter(t),
		WithIntersectionSource(src),
		WithIntersectionSupplyProbe(probe),
	)
	fixedNow(svc, now)

	feed, err := svc.Feed(context.Background(), "u_viewer", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	if len(feed) != 0 {
		t.Fatalf("deferred kind must not fail open, got %d reasons", len(feed))
	}
}

// 混合供给下只丢 deferred 的那条：闸门按 kind 判定，不得连坐同一请求里的 active 交集。
func TestDeferredKindGate_KeepsActiveKindsInSameRequest(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	src := stubSource{
		facts: []IntersectionReasonView{
			freshReason(deferredReason(t, "ix_deferred"), now),
			freshReason(sharedFolloweesReason("ix_followees"), now),
		},
	}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)

	feed, err := svc.Feed(context.Background(), "u_viewer", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	if len(feed) != 1 || feed[0].IntersectionID != "ix_followees" {
		t.Fatalf("only the deferred reason may be dropped, got %+v", feed)
	}
}

// 点级 deferred：多点 reason 里 deferred 的点被剔除，reason 靠剩余 active 点存活，
// 且摘要/计数只由存活点派生（不出现「句子来自被闸掉的点」的错配）。
func TestDeferredKindGate_DropsDeferredPointsButKeepsReason(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	reason := IntersectionReasonView{
		IntersectionID:    "multi",
		IntersectionClass: "fact",
		Dimension:         "relationship",
		Kind:              "sharedFollowees",
		ObjectKind:        "person",
		ActionTargetID:    "u_person",
		DisplayName:       "交集约伴体验号",
		Strength:          0.9,
		FreshAt:           now.Add(-time.Hour).Format(time.RFC3339),
		IntersectionPoints: []IntersectionPointView{
			{
				PointID: "p_rel", PointClass: "fact", Dimension: "relationship",
				SourceRef: "sharedCircle", Visibility: "public", Count: 1,
			},
			{
				PointID: "p_deferred", PointClass: "fact", Dimension: "location",
				SourceRef: deferredKind(t), Visibility: "public", Count: 1,
			},
		},
	}
	src := stubSource{facts: []IntersectionReasonView{reason}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)
	ctx := context.Background()

	list, _, _, err := svc.List(ctx, "u_viewer", IntersectionListQuery{})
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("reason with a surviving point must stay, got %d", len(list))
	}
	for _, point := range list[0].IntersectionPoints {
		if point.PointID == "p_deferred" {
			t.Fatalf("deferred point must not reach the client: %+v", list[0].IntersectionPoints)
		}
	}

	// 红点维度必须与下钻同源：location 维度只由被闸掉的点贡献，因此不得出现。
	sum, err := svc.Summary(ctx, "u_viewer")
	if err != nil {
		t.Fatalf("summary: %v", err)
	}
	for _, dim := range sum.Dimensions {
		if dim.Dimension == "location" {
			t.Fatalf("deferred point must not create a drilldown-empty dimension: %+v", sum.Dimensions)
		}
	}
}
