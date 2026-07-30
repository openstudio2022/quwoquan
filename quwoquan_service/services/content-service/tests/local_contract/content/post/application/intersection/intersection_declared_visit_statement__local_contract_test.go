// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-007
package intersection_test

import (
	"context"
	"strings"
	"testing"
	"time"

	generated "quwoquan_service/services/content-service/generated/content/post"
	. "quwoquan_service/services/content-service/internal/content/post/application/intersection"
)

// 到访类交集的三条口径必须彼此正交且都能下发：
// 都去过（coVisitedEntity，作者声明 visitedAt）、都想去（coWishlistedEntity，wishlist 意图）、
// 也看过（sharedEntityAttention，页面浏览）。任一条被当成另一条就是把弱事实说强。
func TestDeclaredVisitKindsAreServable(t *testing.T) {
	for _, kind := range []string{"coVisitedEntity", "followeeVisited"} {
		if _, deferred := generated.IntersectionDeferredKinds[kind]; deferred {
			t.Fatalf("%s 已有可证到访 producer（posts.visitedAt），不应仍被 deferred 闸门丢弃", kind)
		}
	}
	// 到访供给与浏览供给不同源：到访池远小于浏览池，用浏览池当分母会高估区分度。
	if key := generated.IntersectionColdStartSupplyKeyByKind["coVisitedEntity"]; key != "post_declared_visit" {
		t.Fatalf("coVisitedEntity supplyKey = %q, want post_declared_visit", key)
	}
	if key := generated.IntersectionColdStartSupplyKeyByKind["followeeVisited"]; key != "post_declared_visit" {
		t.Fatalf("followeeVisited supplyKey = %q, want post_declared_visit", key)
	}
	if key := generated.IntersectionColdStartSupplyKeyByKind["sharedEntityAttention"]; key != "entity_page_view" {
		t.Fatalf("浏览类必须继续用浏览池计量, got %q", key)
	}
}

// 人级到访交集：对象页宿主是人，地点是点级证据，结论句必须命名地点并保持对方可点。
func TestExplainCoVisitedEntityNamesPlaceOnPersonSurface(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	reason := displayReadyFactReason(
		"loc_co_visited", "location", "coVisitedEntity", "u_other",
		"person", "陆衡", 2, 0.8,
	)
	reason.FreshAt = now.Add(-48 * time.Hour).Format(time.RFC3339)
	reason.IntersectionPoints[0].Label = "共同去过"
	reason.IntersectionPoints[0].SampleText = "老君山观景台、洱海环线"
	reason.IntersectionPoints[0].DisplayText = "你和陆衡都去过老君山观景台"
	src := stubSource{facts: []IntersectionReasonView{reason}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)

	feed, err := svc.Feed(context.Background(), "u_viewer", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	if len(feed) != 1 {
		t.Fatalf("want 1 reason, got %d", len(feed))
	}
	got := feed[0]
	if got.PrimaryText != "你和「陆衡」都去过老君山观景台" {
		t.Fatalf("declared-visit statement drifted: %q", got.PrimaryText)
	}
	// 「都去过」不得升级为时间断言：同地不等于同期。
	for _, forbidden := range []string{"同期", "同一天", "一起去", "同行过"} {
		if strings.Contains(got.PrimaryText, forbidden) {
			t.Fatalf("visit fact must not claim co-timing or company: %q", got.PrimaryText)
		}
	}
	if JoinedSpanText(got.PrimarySpans) != got.PrimaryText {
		t.Fatalf("join(primarySpans) must equal primaryText: %q vs %q",
			JoinedSpanText(got.PrimarySpans), got.PrimaryText)
	}
	var personSpan *IntersectionTextSpanView
	for i := range got.PrimarySpans {
		if strings.TrimSpace(got.PrimarySpans[i].Role) == "object" {
			personSpan = &got.PrimarySpans[i]
		}
	}
	if personSpan == nil || personSpan.Target == nil || personSpan.Target.ObjectID != "u_other" {
		t.Fatalf("person must stay the navigable object of the sentence: %+v", got.PrimarySpans)
	}
	// 地名是分类/实体证据，不是本句的可导航对象：不得挂 target 造出死链。
	for _, span := range got.PrimarySpans {
		if strings.Contains(span.Text, "老君山观景台") &&
			strings.TrimSpace(span.Role) == "object" {
			t.Fatalf("place sample must render as plain text on the person surface: %+v", span)
		}
	}
}

// 地名缺失时不得造名：要么降级成纯计数句，要么整条不下发，绝不能凭空说出一个地点。
func TestExplainCoVisitedEntityNeverInventsPlaceName(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	reason := displayReadyFactReason(
		"loc_co_visited_unnamed", "location", "coVisitedEntity", "u_other",
		"person", "陆衡", 3, 0.8,
	)
	reason.FreshAt = now.Add(-time.Hour).Format(time.RFC3339)
	// 点级没有可证地名（只有计数）：producer 不造名，展示层也不许造名。
	reason.IntersectionPoints[0].SampleText = ""
	src := stubSource{facts: []IntersectionReasonView{reason}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)

	feed, err := svc.Feed(context.Background(), "u_viewer", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	for _, got := range feed {
		if strings.Contains(got.PrimaryText, "都去过") &&
			!strings.Contains(got.PrimaryText, "个相同的地方") {
			t.Fatalf("no provable place name may still yield a named visit claim: %q", got.PrimaryText)
		}
		if JoinedSpanText(got.PrimarySpans) != got.PrimaryText {
			t.Fatalf("join(primarySpans) must equal primaryText: %q vs %q",
				JoinedSpanText(got.PrimarySpans), got.PrimaryText)
		}
	}
}
