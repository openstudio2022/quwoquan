package application

import "testing"

// WS3 真算覆盖：vertical 三元组正交（§23.4）+ lifecycle 状态机（§21.3）离散化。
// 旅行交集 vertical 由 objectKind（route/photo_spot/gear）或旅行 tag 推导，基 kind 不参与。

func TestVerticalForReason_ObjectKindAndTag(t *testing.T) {
	cases := []struct {
		name       string
		objectKind string
		tagRefs    []string
		want       string
	}{
		{name: "route 主对象归旅行垂类", objectKind: "route", want: "travel_photography"},
		{name: "photo_spot 主对象归旅行垂类", objectKind: "photo_spot", want: "travel_photography"},
		{name: "gear 主对象归旅行垂类", objectKind: "gear", want: "travel_photography"},
		{name: "place + 旅行 tag 命中", objectKind: "place", tagRefs: []string{"tag/travel/place"}, want: "travel_photography"},
		{name: "person + landscape tag 命中", objectKind: "person", tagRefs: []string{"tag/interest/landscape"}, want: "travel_photography"},
		{name: "person 无旅行信号归 general", objectKind: "person", tagRefs: []string{"tag/relationship/shared_follow"}, want: "general"},
		{name: "circle 无 tag 归 general", objectKind: "circle", want: "general"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := verticalForReason(IntersectionReasonView{ObjectKind: tc.objectKind, TagRefs: tc.tagRefs})
			if got != tc.want {
				t.Fatalf("verticalForReason(%q,%v) = %q, want %q", tc.objectKind, tc.tagRefs, got, tc.want)
			}
		})
	}
}

func TestLifecycleStateForReason_StateMachine(t *testing.T) {
	cases := []struct {
		name             string
		previousStrength float64
		strengthDelta    float64
		strength         float64
		edgeWeight       float64
		want             string
	}{
		{name: "无任何强度信号→空（不造假）", want: ""},
		{name: "首次成边→new", previousStrength: 0, strength: 0.4, edgeWeight: 0.4, want: "new"},
		{name: "健康基线上升→strengthened", previousStrength: 0.7, strengthDelta: 0.2, want: "strengthened"},
		{name: "低位回升→reactivated", previousStrength: 0.3, strengthDelta: 0.2, want: "reactivated"},
		{name: "衰减→weakened", previousStrength: 0.8, strengthDelta: -0.2, want: "weakened"},
		{name: "微小波动→stable", previousStrength: 0.6, strengthDelta: 0.01, want: "stable"},
		{name: "仅 previous+current 推 delta→strengthened", previousStrength: 0.6, strength: 0.8, want: "strengthened"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := lifecycleStateForReason(IntersectionReasonView{
				PreviousStrength: tc.previousStrength,
				StrengthDelta:    tc.strengthDelta,
				Strength:         tc.strength,
				EdgeWeight:       tc.edgeWeight,
			})
			if got != tc.want {
				t.Fatalf("lifecycleStateForReason(prev=%v,delta=%v,str=%v,edge=%v) = %q, want %q",
					tc.previousStrength, tc.strengthDelta, tc.strength, tc.edgeWeight, got, tc.want)
			}
		})
	}
}

func TestRouteAndAssetForTravelObjectKinds(t *testing.T) {
	for _, kind := range []string{"route", "photo_spot", "gear"} {
		if got := routeIDForObjectKind(kind); got != "homepageDetail" {
			t.Fatalf("routeIDForObjectKind(%q) = %q, want homepageDetail", kind, got)
		}
		if got := assetKindForObjectKind(kind); got != "coverImage" {
			t.Fatalf("assetKindForObjectKind(%q) = %q, want coverImage", kind, got)
		}
	}
}
