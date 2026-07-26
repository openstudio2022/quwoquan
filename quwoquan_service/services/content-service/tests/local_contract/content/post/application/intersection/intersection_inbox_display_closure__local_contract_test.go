package intersection_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/post/application/intersection"
	"strings"
	"testing"
	"time"
)

// V2 收口合同：收件箱（List/Summary）与 Feed/Object 同一 fail-closed 展示合同——
// Explain 证据不足被 hideDisplayStatement 清空的 reason 必须在云侧淘汰，
// summary 红点计数必须与 List 可见条目同源（禁止「有红点、点进去空列表」）。
func TestIntersectionService_ListAndSummaryDropHiddenReasons(t *testing.T) {
	now := time.Date(2026, 7, 20, 12, 0, 0, 0, time.UTC)
	visible := displayReadyFactReason("visible", "relationship", "sharedFollowees", "u1", "person", "陆衡", 2, 0.9)
	visible.FreshAt = now.Add(-time.Hour).Format(time.RFC3339)
	// 裸 reason：无对象名可证、无代表人 → Explain 产不出结论句 → hidden。
	bare := IntersectionReasonView{
		IntersectionID:    "bare",
		IntersectionClass: "fact",
		Dimension:         "relationship",
		ObjectKind:        "person",
		ActionTargetID:    "u_bare",
		FreshAt:           now.Add(-time.Hour).Format(time.RFC3339),
	}
	src := stubSource{facts: []IntersectionReasonView{visible, bare}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)
	ctx := context.Background()

	page, _, _, err := svc.List(ctx, "viewer1", IntersectionListQuery{Limit: 10})
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(page) != 1 || page[0].IntersectionID != "visible" {
		t.Fatalf("hidden reason must be dropped server-side, got %+v", page)
	}
	for _, r := range page {
		if strings.TrimSpace(r.PrimaryText) == "" || len(r.PrimarySpans) == 0 {
			t.Fatalf("delivered reason must be display complete: %+v", r)
		}
	}

	sum, err := svc.Summary(ctx, "viewer1")
	if err != nil {
		t.Fatalf("summary: %v", err)
	}
	wantTotal := len(visible.IntersectionPoints)
	if sum.TotalCount != wantTotal {
		t.Fatalf("summary must count only displayable reasons: total=%d want=%d", sum.TotalCount, wantTotal)
	}
	if sum.TotalNewCount != wantTotal {
		t.Fatalf("summary new count drifted: new=%d want=%d", sum.TotalNewCount, wantTotal)
	}

	// tally 维度下钻与 List 同源：summary 出现的每个维度，List 按该维度过滤必须非空。
	for _, dim := range sum.Dimensions {
		dimPage, _, _, err := svc.List(ctx, "viewer1", IntersectionListQuery{
			Dimension: dim.Dimension,
			Limit:     10,
		})
		if err != nil {
			t.Fatalf("list dimension %s: %v", dim.Dimension, err)
		}
		if len(dimPage) == 0 {
			t.Fatalf("summary dimension %q counts %d but list drilldown is empty", dim.Dimension, dim.Count)
		}
	}
}

// V2 补充合同：多维度 point 的 reason，Summary 按 point 维度分桶计数，
// List 按同一谓词下钻——「地点 1」红点点进地点维度必须能看到该 reason。
// fixture 形态对齐 gamma 真实链路：person reason 的代表人=对象本人
// （fallback actor target==reason target，计数降级句才满足 explicit_link 对象链接合同）。
func TestIntersectionService_DimensionDrilldownMatchesSummaryTally(t *testing.T) {
	now := time.Date(2026, 7, 20, 12, 0, 0, 0, time.UTC)
	reason := IntersectionReasonView{
		IntersectionID:    "multi",
		IntersectionClass: "fact",
		Dimension:         "relationship",
		ObjectKind:        "person",
		ActionTargetID:    "u_person",
		DisplayName:       "交集约伴体验号",
		Strength:          0.9,
		FreshAt:           now.Add(-time.Hour).Format(time.RFC3339),
		IntersectionPoints: []IntersectionPointView{
			{PointID: "p_rel", PointClass: "fact", Dimension: "relationship", SourceRef: "sharedCircle", Visibility: "public", Count: 1},
			{PointID: "p_loc", PointClass: "fact", Dimension: "location", SourceRef: "coVisitedEntity", Visibility: "public", Count: 1},
			{PointID: "p_con", PointClass: "fact", Dimension: "content", SourceRef: "coCommented", Visibility: "public", Count: 1},
		},
	}
	src := stubSource{facts: []IntersectionReasonView{reason}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)
	ctx := context.Background()

	sum, err := svc.Summary(ctx, "viewer1")
	if err != nil {
		t.Fatalf("summary: %v", err)
	}
	if len(sum.Dimensions) != 3 {
		t.Fatalf("want 3 dimension tallies, got %+v", sum.Dimensions)
	}
	for _, dim := range sum.Dimensions {
		page, _, _, err := svc.List(ctx, "viewer1", IntersectionListQuery{Dimension: dim.Dimension, Limit: 10})
		if err != nil {
			t.Fatalf("list %s: %v", dim.Dimension, err)
		}
		if len(page) != 1 || page[0].IntersectionID != "multi" {
			t.Fatalf("dimension %q drilldown must surface the multi-point reason, got %+v", dim.Dimension, page)
		}
	}
}

// V3 收口合同：person reason 的 DisplayName（人名）禁止冒充圈子/地点/内容等
// 容器对象名（曾产出「…都加入了『<人名>』」错句）；无可证容器名时按 §20.4
// 降级为纯计数句，且 join(primarySpans)==primaryText 不变量在降级形态下成立。
func TestExplainRejectsPersonNameAsContainerObject(t *testing.T) {
	now := time.Date(2026, 7, 20, 12, 0, 0, 0, time.UTC)
	reason := IntersectionReasonView{
		IntersectionID:    "person_circle",
		IntersectionClass: "fact",
		Dimension:         "relationship",
		ObjectKind:        "person",
		ActionTargetID:    "u_person",
		DisplayName:       "交集约伴体验号",
		FreshAt:           now.Add(-time.Hour).Format(time.RFC3339),
		IntersectionPoints: []IntersectionPointView{{
			PointID:    "p_circle",
			PointClass: "fact",
			Dimension:  "relationship",
			SourceRef:  "sharedCircle",
			Visibility: "public",
			Count:      2,
		}},
	}
	r := HydratePointSummary(reason)
	primary := strings.TrimSpace(r.PrimaryText)
	if primary == "" {
		t.Fatalf("sharedCircle with count must degrade to counted statement, got hidden: %+v", r)
	}
	if strings.Contains(primary, "都加入了「交集约伴体验号」") {
		t.Fatalf("person display name must not pose as circle name: %q", primary)
	}
	if !strings.Contains(primary, "2个共同圈子") {
		t.Fatalf("counted fallback object expected, got %q", primary)
	}
	if joined := JoinedSpanText(r.PrimarySpans); joined != primary {
		t.Fatalf("spans invariant broken: joined=%q primary=%q", joined, primary)
	}
	if !ValidateDisplayStatement(r) {
		t.Fatalf("degraded counted statement must stay displayable: %+v", r)
	}

	// 圈子对象页 reason（objectKind=circle）仍允许具名圈子句，不受降级影响
	// （多人句必须有真实 user 代表人：补 actorEvidence，对齐真实链路形态 §17.1.1）。
	circleReason := reason
	circleReason.ObjectKind = "circle"
	circleReason.ActionTargetID = "c_photo"
	circleReason.DisplayName = "城市漫游圈"
	circleReason.ActorEvidenceTotalCount = 2
	circleReason.ActorEvidenceCompleteness = "complete"
	circleReason.ActorEvidence = []IntersectionActorEvidenceView{{
		ActorID:       "u_lin",
		DisplayName:   "林清越",
		RelationLabel: "同圈成员",
		SourceRef:     "sharedCircle",
		PrivacyState:  "visible",
		Target: &IntersectionTargetView{
			ObjectType: "user",
			ObjectID:   "u_lin",
			ObjectKind: "person",
			RouteID:    "userProfile",
		},
	}}
	circleReason.IntersectionPoints = []IntersectionPointView{{
		PointID:    "p_circle_named",
		PointClass: "fact",
		Dimension:  "relationship",
		SourceRef:  "sharedCircle",
		Visibility: "public",
		Count:      2,
		SampleText: "林清越",
	}}
	cr := HydratePointSummary(circleReason)
	if !strings.Contains(cr.PrimaryText, "都加入了「城市漫游圈」") {
		t.Fatalf("circle reason must keep named statement, got %q", cr.PrimaryText)
	}
}
