// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-007
package intersection_test

import (
	"context"
	"errors"
	"testing"
	"time"

	. "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
)

// stubSupplyProbe 是冷启动供给探针的对象级 typed double：按 supplyKey 返回预置的
// 去重对象数，并记录每个 key 被问了几次（用于断言同一请求内只探一次）。
type stubSupplyProbe struct {
	supply map[string]int
	err    error
	calls  map[string]int
}

func newStubSupplyProbe(supply map[string]int) *stubSupplyProbe {
	return &stubSupplyProbe{supply: supply, calls: map[string]int{}}
}

func (p *stubSupplyProbe) DistinctObjectSupply(_ context.Context, supplyKey string) (int, error) {
	p.calls[supplyKey]++
	if p.err != nil {
		return 0, p.err
	}
	n, ok := p.supply[supplyKey]
	if !ok {
		return 0, errors.New("unknown supplyKey " + supplyKey)
	}
	return n, nil
}

// entityAttentionReason 造一条「双方都看过同一实体」的可下发 reason。
// sharedEntityAttention 在注册表中登记了 supplyKey=entity_page_view、阈值 8，
// 是冷启动稀释的典型场景：语料只有 1 个 POI 时人人都命中。
func entityAttentionReason(id string) IntersectionReasonView {
	r := displayReadyFactReason(
		id, "interest", "sharedEntityAttention", westLakeHomepageID,
		"place", "西湖", 1, 0.7,
	)
	r.RelationObjectID = westLakeHomepageID
	return withDisplayStatement(r, "西湖", "林清越", "actor_"+id)
}

// westLakeHomepageID 是实体主页宿主对象：对象页入口用它做 host，
// 保证 host_plain 展示上下文与 reason 对象一致。
const westLakeHomepageID = "homepage_sight_west_lake"

// sharedFolloweesReason 造一条不受闸门约束的 reason（共同关注的人：
// 对象池天然等于用户池，注册表未登记 supplyKey）。
func sharedFolloweesReason(id string) IntersectionReasonView {
	r := displayReadyFactReason(
		id, "relationship", "sharedFollowees", "u_zhou",
		"person", "周屿", 2, 0.9,
	)
	return withDisplayStatement(r, "周屿", "林清越", "actor_"+id)
}

func freshReason(r IntersectionReasonView, now time.Time) IntersectionReasonView {
	r.FreshAt = now.Add(-2 * time.Hour).Format(time.RFC3339)
	r.ExpiresAt = now.Add(14 * 24 * time.Hour).Format(time.RFC3339)
	return r
}

// 供给低于阈值时，该 kind 的交集在三个入口都不展示：
// 语料只有 1 个实体时「你和 TA 都看过西湖」对所有用户都成立，信息量为零。
func TestColdStartSupplyGate_UnderSuppliedKindHiddenOnAllSurfaces(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	probe := newStubSupplyProbe(map[string]int{"entity_page_view": 1})
	src := stubSource{
		facts:  []IntersectionReasonView{freshReason(entityAttentionReason("ix_attention"), now)},
		object: []IntersectionReasonView{freshReason(entityAttentionReason("ix_attention"), now)},
	}
	svc := NewIntersectionService(
		newTestRouter(t),
		WithIntersectionSource(src),
		WithIntersectionSupplyProbe(probe),
	)
	fixedNow(svc, now)
	ctx := context.Background()

	feed, err := svc.Feed(ctx, "u_viewer", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	if len(feed) != 0 {
		t.Fatalf("feed must hide under-supplied kind, got %d reasons", len(feed))
	}

	list, _, _, err := svc.List(ctx, "u_viewer", IntersectionListQuery{})
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(list) != 0 {
		t.Fatalf("inbox must hide under-supplied kind, got %d reasons", len(list))
	}

	object, err := svc.ObjectIntersections(ctx, "u_viewer", westLakeHomepageID, "entity", 10)
	if err != nil {
		t.Fatalf("object intersections: %v", err)
	}
	if len(object) != 0 {
		t.Fatalf("object page must hide under-supplied kind, got %d reasons", len(object))
	}
}

// 供给达到阈值后同一条交集在三个入口都恢复展示：闸门只治稀释，不永久关闭 kind。
// 这一组正向断言同时保证上一组「不展示」不是空跑。
func TestColdStartSupplyGate_SufficientSupplyKeepsReasonOnAllSurfaces(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	probe := newStubSupplyProbe(map[string]int{"entity_page_view": 12})
	src := stubSource{
		facts:  []IntersectionReasonView{freshReason(entityAttentionReason("ix_attention"), now)},
		object: []IntersectionReasonView{freshReason(entityAttentionReason("ix_attention"), now)},
	}
	svc := NewIntersectionService(
		newTestRouter(t),
		WithIntersectionSource(src),
		WithIntersectionSupplyProbe(probe),
	)
	fixedNow(svc, now)
	ctx := context.Background()

	feed, err := svc.Feed(ctx, "u_viewer", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	if len(feed) != 1 {
		t.Fatalf("sufficient supply must keep feed reason, got %d", len(feed))
	}

	list, _, _, err := svc.List(ctx, "u_viewer", IntersectionListQuery{})
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("sufficient supply must keep inbox reason, got %d", len(list))
	}

	object, err := svc.ObjectIntersections(ctx, "u_viewer", westLakeHomepageID, "entity", 10)
	if err != nil {
		t.Fatalf("object intersections: %v", err)
	}
	if len(object) != 1 {
		t.Fatalf("sufficient supply must keep object reason, got %d", len(object))
	}
}

// 未登记 supplyKey 的 kind 不受闸门约束，也不触发探针查询。
func TestColdStartSupplyGate_UngatedKindNeverProbed(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	probe := newStubSupplyProbe(map[string]int{"entity_page_view": 1})
	src := stubSource{
		facts: []IntersectionReasonView{freshReason(sharedFolloweesReason("ix_followees"), now)},
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
	if len(feed) != 1 {
		t.Fatalf("ungated kind must pass, got %d", len(feed))
	}
	if len(probe.calls) != 0 {
		t.Fatalf("ungated kind must not probe supply, calls=%v", probe.calls)
	}
}

// 探针不可用时 fail-open：观测能力缺失不得误杀真实交集。
func TestColdStartSupplyGate_ProbeFailureFailsOpen(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	probe := newStubSupplyProbe(nil)
	probe.err = errors.New("mongo unavailable")
	src := stubSource{
		facts: []IntersectionReasonView{freshReason(entityAttentionReason("ix_attention"), now)},
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
	if len(feed) != 1 {
		t.Fatalf("probe failure must fail open, got %d", len(feed))
	}
}

// 同一请求内同一 supplyKey 只探一次，保证判定一致且成本恒定。
func TestColdStartSupplyGate_ProbesEachSupplyKeyOncePerRequest(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	probe := newStubSupplyProbe(map[string]int{"entity_page_view": 20})
	src := stubSource{
		facts: []IntersectionReasonView{
			freshReason(entityAttentionReason("ix_a"), now),
			freshReason(entityAttentionReason("ix_b"), now),
			freshReason(entityAttentionReason("ix_c"), now),
		},
	}
	svc := NewIntersectionService(
		newTestRouter(t),
		WithIntersectionSource(src),
		WithIntersectionSupplyProbe(probe),
	)
	fixedNow(svc, now)

	if _, err := svc.Feed(context.Background(), "u_viewer", "recommend", 10); err != nil {
		t.Fatalf("feed: %v", err)
	}
	if probe.calls["entity_page_view"] != 1 {
		t.Fatalf("supplyKey must be probed once per request, got %d", probe.calls["entity_page_view"])
	}
}

// 未注入探针时闸门不生效：闸门是可观测能力的增量，不改变既有下发口径。
func TestColdStartSupplyGate_DisabledWithoutProbe(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	src := stubSource{
		facts: []IntersectionReasonView{freshReason(entityAttentionReason("ix_attention"), now)},
	}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)

	feed, err := svc.Feed(context.Background(), "u_viewer", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	if len(feed) != 1 {
		t.Fatalf("gate must be inert without probe, got %d", len(feed))
	}
}
