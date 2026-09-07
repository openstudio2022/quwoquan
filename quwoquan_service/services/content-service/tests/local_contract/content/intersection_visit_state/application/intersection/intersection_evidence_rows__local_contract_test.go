// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/home-recommend-intersection-redesign/spec.md#gwt-001
package intersection_test

import (
	"context"
	"reflect"
	"testing"
	"time"

	. "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
)

// evidenceRowsFixture 与 statement_template 合约测试同形（只给事实点 + 人名，让水合管线产出主句），
// 再补齐证据半屏会消费的 typed 字段。
func evidenceRowsFixture(now time.Time) IntersectionReasonView {
	return IntersectionReasonView{
		IntersectionID:    "rel_shared_followees_rows",
		IntersectionClass: "fact",
		Dimension:         "relationship",
		ObjectKind:        "person",
		ActionTargetID:    "u_other",
		DisplayName:       "陆衡",
		Strength:          0.9,
		FreshAt:           now.Add(-time.Hour).Format(time.RFC3339),
		SecondaryText:     "你们还有 3 位共同关注",
		ConnectionSummary: "摄影把你们连在一起",
		ActorEvidence: []IntersectionActorEvidenceView{
			{ActorID: "u_lin", DisplayName: "林清越", RelationLabel: "联系人", ActionSummaryText: "赞过这条记录", LikeCount: 1, EvidenceRank: 1},
			{ActorID: "u_zhou", DisplayName: "周屿", RelationLabel: "你关注的人", ActionSummaryText: "摄影把你们连在一起", CommentCount: 1, EvidenceRank: 2},
			{ActorID: "u_wu", DisplayName: "吴一", RelationLabel: "你关注的人", ActionSummaryText: "评论过这条记录", CommentCount: 1, EvidenceRank: 3},
		},
		IntersectionPoints: []IntersectionPointView{
			{
				PointID: "p_shared", PointClass: "fact", Dimension: "relationship",
				SourceRef: "sharedFollowees", Label: "共同关注", Count: 3,
				DisplayText: "3 位共同关注", SampleText: "林清越、周屿、吴一", Visibility: "public",
			},
		},
	}
}

func hydratedThroughFeed(t *testing.T, now time.Time, reason IntersectionReasonView) IntersectionReasonView {
	t.Helper()
	src := stubSource{facts: []IntersectionReasonView{reason}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)
	feed, err := svc.Feed(context.Background(), "u_viewer", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	if len(feed) != 1 {
		t.Fatalf("want 1 visible reason, got %d", len(feed))
	}
	return feed[0]
}

// 证据半屏的证据行由水合出口按 IntersectionEvidenceRow 契约闭集与顺序实例化：
// secondaryText → connectionSummary → actorEvidence.actionSummaryText → point.displayText → point.sampleText，
// 与主句及彼此去重、上限 4 行；端只按序渲染。
func TestHydrationInstantiatesEvidenceRowsFromTypedFieldsInContractOrder(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	got := hydratedThroughFeed(t, now, evidenceRowsFixture(now))
	want := []IntersectionEvidenceRowView{
		{Text: "你们还有 3 位共同关注", Source: "secondary_text"},
		{Text: "摄影把你们连在一起", Source: "connection_summary"},
		{Text: "赞过这条记录", Source: "actor_action"},
		{Text: "评论过这条记录", Source: "actor_action"},
	}
	if !reflect.DeepEqual(got.EvidenceRows, want) {
		t.Fatalf("evidenceRows drifted from contract order/dedupe/limit:\n got=%+v\nwant=%+v", got.EvidenceRows, want)
	}
	if len(got.EvidenceRows) != MaxIntersectionEvidenceRows {
		t.Fatalf("contract limit is %d rows, got %d", MaxIntersectionEvidenceRows, len(got.EvidenceRows))
	}
}

func TestEvidenceRowsSkipPrimaryTextDuplicatesAndFallThroughToPointSamples(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	reason := evidenceRowsFixture(now)
	reason.ActorEvidence = nil
	reason.ConnectionSummary = ""
	hydrated := HydratePointSummary(reason)
	// 与主句相同的副句必须被丢弃；点位 displayText / sampleText 依序补位。
	reason.SecondaryText = hydrated.PrimaryText
	got := hydratedThroughFeed(t, now, reason)
	want := []IntersectionEvidenceRowView{
		{Text: "3 位共同关注", Source: "point_display"},
		{Text: "林清越、周屿、吴一", Source: "point_sample"},
	}
	if !reflect.DeepEqual(got.EvidenceRows, want) {
		t.Fatalf("primaryText duplicate must be dropped and point rows kept in order: %+v (primary=%q)", got.EvidenceRows, got.PrimaryText)
	}

	hidden := ApplyDisplayContext(got, DisplayContext{
		Surface:    DisplaySurfaceFeed,
		HostTarget: &IntersectionTargetView{ObjectType: "post", ObjectID: "post_1", ObjectKind: "content", RouteID: "contentDetail"},
		Binding:    DisplayBindingHostImplicit,
	})
	if hidden.DisplayBinding != DisplayBindingHidden {
		t.Fatalf("person-object statement cannot bind host_implicit to a post host; expected hidden, got %+v", hidden)
	}
	if hidden.EvidenceRows == nil || len(hidden.EvidenceRows) != 0 {
		t.Fatalf("hidden statement must carry an empty (non-null) evidenceRows list for the wire contract: %#v", hidden.EvidenceRows)
	}
}
