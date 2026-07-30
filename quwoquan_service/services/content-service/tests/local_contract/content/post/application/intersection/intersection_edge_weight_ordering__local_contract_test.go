package intersection_test

import (
	"context"
	"testing"
	"time"

	. "quwoquan_service/services/content-service/internal/content/post/application/intersection"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

// 物化边权必须真正参与排序，不能只被计算、落库、下发。
//
// 背景：intersection_graph_materializer 真算 edgeWeight = relationStrength ×
// interactionFrequency × recencyDecay 并随快照落库。如果三个排序比较器都不读它，
// 它就退化成第二真相源——读路径按另一套键排序，运营看到的边权与实际顺序无关。
// 本组测试锁住「同等语义序下边权决定先后」，防止该信号再次悬空。

// edgeWeightHostID 让同一对象页上出现多条 reason：对象页是 host_plain 上下文，
// reason 对象必须就是宿主对象，否则会在展示校验里被淘汰。
const edgeWeightHostID = "u_edge_weight_host"

func edgeWeightReason(
	t *testing.T,
	id, targetID string,
	points int,
	freshAt time.Time,
) IntersectionReasonView {
	t.Helper()
	r := displayReadyFactReason(
		id, "relationship", "sharedFollowees", targetID,
		"person", "林清越", points, 0.6,
	)
	r.RelationObjectID = targetID
	r.FreshAt = freshAt.Format(time.RFC3339)
	return withDisplayStatement(r, "林清越", "林清越", "actor_"+id)
}

func TestEdgeWeightParticipatesInObjectOrdering(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	// 同 kind、同 Strength、同证据计数：唯一差异是新鲜度，因此唯一区分键是边权。
	// 若比较器不读边权，两条的相对顺序只能由 stub 输入顺序决定（stale 在前）。
	stale := edgeWeightReason(t, "ix_stale", edgeWeightHostID, 2, now.Add(-30*24*time.Hour))
	recent := edgeWeightReason(t, "ix_recent", edgeWeightHostID, 2, now.Add(-1*time.Hour))
	materialized := recinfra.ApplyGraphWeights(
		[]IntersectionReasonView{stale, recent}, now,
	)
	if materialized[0].EdgeWeight >= materialized[1].EdgeWeight {
		t.Fatalf(
			"fixture broken: stale edge must weigh less than recent, got %.4f vs %.4f",
			materialized[0].EdgeWeight, materialized[1].EdgeWeight,
		)
	}

	src := stubSource{object: materialized}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)

	out, err := svc.ObjectIntersections(
		context.Background(), "u_viewer", edgeWeightHostID, "person", 10,
	)
	if err != nil {
		t.Fatalf("object intersections: %v", err)
	}
	if len(out) < 2 {
		t.Fatalf("want both reasons on object page, got %d", len(out))
	}
	if out[0].EdgeWeight < out[1].EdgeWeight {
		t.Fatalf(
			"object page must rank by materialized edge weight: got %.4f before %.4f",
			out[0].EdgeWeight, out[1].EdgeWeight,
		)
	}
}

func TestEdgeWeightParticipatesInInboxOrdering(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	// 收件箱先按 Strength、再按时间桶排序。这里把两条都放进同一天、同 Strength，
	// 只让证据密度不同：边权是第一个能区分它们的键（裸计数排在边权之后）。
	// 收件箱按 (viewer, object, objectType, kind) 去重，所以两条必须指向不同对象。
	sparse := edgeWeightReason(t, "ix_sparse", "u_edge_sparse", 1, now.Add(-2*time.Hour))
	dense := edgeWeightReason(t, "ix_dense", "u_edge_dense", 6, now.Add(-2*time.Hour))
	materialized := recinfra.ApplyGraphWeights(
		[]IntersectionReasonView{sparse, dense}, now,
	)

	src := stubSource{facts: materialized}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)

	list, _, _, err := svc.List(context.Background(), "u_viewer", IntersectionListQuery{})
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(list) < 2 {
		t.Fatalf("want both reasons in inbox, got %d", len(list))
	}
	if list[0].EdgeWeight < list[1].EdgeWeight {
		t.Fatalf(
			"inbox must rank by materialized edge weight: got %.4f before %.4f",
			list[0].EdgeWeight, list[1].EdgeWeight,
		)
	}
}

// 请求期直算的 reason 没有物化边权（0）。边权键必须在这种情况下静默让位，
// 否则「没被物化过」会变成排序惩罚，未物化通道的既有顺序会被打乱。
func TestZeroEdgeWeightFallsThroughToExistingKeys(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	few := freshReason(edgeWeightReason(t, "ix_few", "u_edge_few", 1, now), now)
	many := freshReason(edgeWeightReason(t, "ix_many", "u_edge_many", 5, now), now)
	if few.EdgeWeight != 0 || many.EdgeWeight != 0 {
		t.Fatalf("fixture broken: request-time reasons must carry no edge weight")
	}

	src := stubSource{facts: []IntersectionReasonView{few, many}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)

	list, _, _, err := svc.List(context.Background(), "u_viewer", IntersectionListQuery{})
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(list) < 2 {
		t.Fatalf("want both reasons in inbox, got %d", len(list))
	}
	// 边权全 0 时退回既有键：证据计数多的在前。
	if list[0].TotalPointCount < list[1].TotalPointCount {
		t.Fatalf(
			"without edge weight, ordering must fall back to point count: got %d before %d",
			list[0].TotalPointCount, list[1].TotalPointCount,
		)
	}
}
