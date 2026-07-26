package authorimpact_test

import (
	. "quwoquan_service/services/content-service/internal/content/post/application/authorimpact"
	"testing"

	"quwoquan_service/services/content-service/internal/content/post/application/ports"
)

// WS3 旅行影响力真算覆盖（§22.5 / §23.4 三元组正交）：旅行影响力「类型」由真实聚合的
// IntersectionTagRef 派生下钻目标对象（route/photo_spot/gear/place），被计数对象恒为 person，
// 而非仅靠 seed 直出。非旅行信号不造假（CountTarget 留空）。

func TestTravelImpactObjectKindForTag(t *testing.T) {
	cases := []struct {
		name   string
		tagRef string
		want   string
	}{
		{name: "route 命名空间", tagRef: "tag/travel/route", want: "route"},
		{name: "photo_spot 命名空间优先于 route 词", tagRef: "tag/travel/photo_spot", want: "photo_spot"},
		{name: "spot 简写", tagRef: "tag/travel/spot/duanqiao", want: "photo_spot"},
		{name: "gear 命名空间", tagRef: "tag/gear/tripod", want: "gear"},
		{name: "place 旅行 tag", tagRef: "tag/travel/place", want: "place"},
		{name: "通用 travel tag 归 place", tagRef: "Topic/travel", want: "place"},
		{name: "非旅行 tag 留空", tagRef: "Audience/学生", want: ""},
		{name: "空 tag 留空", tagRef: "", want: ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := TravelImpactObjectKindForTag(tc.tagRef); got != tc.want {
				t.Fatalf("travelImpactObjectKindForTag(%q) = %q, want %q", tc.tagRef, got, tc.want)
			}
		})
	}
}

func TestDecorateAuthorImpact_TravelCountTargetFromAggregatedTag(t *testing.T) {
	summary := ports.AuthorImpactSummary{
		AuthorID: "fixture_user_travel_curator",
		Items: []ports.AuthorImpactItem{
			{HelpType: "decision", Action: "entity_page_view", IntersectionDimension: "location", TagRef: "tag/travel/route", Count: 12},
			{HelpType: "decision", Action: "entity_page_view", IntersectionDimension: "location", TagRef: "tag/travel/photo_spot", Count: 9},
			{HelpType: "relationship", Action: "follow", IntersectionDimension: "relationship", TagRef: "Audience/学生", Count: 3},
		},
	}

	got := DecorateAuthorImpact(summary, false)
	if len(got.Items) != 3 {
		t.Fatalf("decorated items = %d, want 3", len(got.Items))
	}

	// 旅行 route 影响：下钻目标对象类型 route + homepageDetail，被计数对象 person。
	route := got.Items[0]
	if route.CountTarget == nil || route.CountTarget.ObjectKind != "route" {
		t.Fatalf("route impact countTarget = %+v, want objectKind=route", route.CountTarget)
	}
	if route.CountTarget.RouteID != "homepageDetail" {
		t.Fatalf("route impact countTarget routeId = %q, want homepageDetail", route.CountTarget.RouteID)
	}
	if route.CountObjectKind != "person" {
		t.Fatalf("route impact countObjectKind = %q, want person", route.CountObjectKind)
	}

	// 旅行 photo_spot 影响：下钻目标对象类型 photo_spot。
	spot := got.Items[1]
	if spot.CountTarget == nil || spot.CountTarget.ObjectKind != "photo_spot" {
		t.Fatalf("spot impact countTarget = %+v, want objectKind=photo_spot", spot.CountTarget)
	}
	if spot.CountObjectKind != "person" {
		t.Fatalf("spot impact countObjectKind = %q, want person", spot.CountObjectKind)
	}

	// 非旅行影响：不造假目标（CountTarget 留空、CountObjectKind 不强加）。
	generic := got.Items[2]
	if generic.CountTarget != nil {
		t.Fatalf("non-travel impact countTarget = %+v, want nil", generic.CountTarget)
	}
	if generic.CountObjectKind != "" {
		t.Fatalf("non-travel impact countObjectKind = %q, want empty", generic.CountObjectKind)
	}
	for _, item := range got.Items {
		if item.PrimaryText == "" {
			t.Fatalf("impact item must carry server-generated primaryText: %+v", item)
		}
	}
}

// 预置 countTarget（如 seed/读模型已物化）时尊重不覆盖（真算仅补缺）。
func TestDecorateAuthorImpact_RespectsPreseededCountTarget(t *testing.T) {
	summary := ports.AuthorImpactSummary{
		AuthorID: "fixture_user_travel_curator",
		Items: []ports.AuthorImpactItem{
			{
				HelpType:        "decision",
				Action:          "entity_page_view",
				TagRef:          "tag/travel/route",
				Count:           5,
				CountObjectKind: "person",
				CountTarget: &ports.ImpactTarget{
					ObjectID:   "fixture_homepage_travel_route_erhai",
					ObjectKind: "route",
					RouteID:    "homepageDetail",
				},
			},
		},
	}
	got := DecorateAuthorImpact(summary, true)
	if got.Items[0].CountTarget.ObjectID != "fixture_homepage_travel_route_erhai" {
		t.Fatalf("preseeded countTarget overwritten: %+v", got.Items[0].CountTarget)
	}
}
