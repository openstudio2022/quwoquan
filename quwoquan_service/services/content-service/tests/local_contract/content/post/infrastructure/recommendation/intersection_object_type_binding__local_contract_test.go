package recommendation_test

import (
	"os"
	"path/filepath"
	"testing"

	generated "quwoquan_service/services/content-service/generated/content/post"

	"gopkg.in/yaml.v3"
)

// 交集侧的 objectType→objectKind 曾经是一段手写 switch，只认 user / circle /
// homepage 三个值，其余全部落 default 当成人物。结果是 museum、ancient_town 这类
// 主页在交集里被当作「人」：维度算成 identity、称谓说成「同好」、点击跳个人主页。
//
// 现在这层翻译由 intersection_kind_registry.yaml 的 objectTypeBindings 声明，经
// codegen 落成查表。本组测试守住三件事：全枚举有登记、地点类语义正确、未知值
// 查空而不是静默当人。

// formerlyDefaultedPlaceHomepageTypes 是整改前落进 default 的地点类 HomepageType。
// 旧 switch 只认 sight/travel_photo/place/route/photo_spot/gear/homepage 这几个字面量，
// 这 13 个值一个都不在其中：它们被算成 interest 维度、称谓「同好」、objectKind 为空，
// 于是「共同点」既说错了话也点不进主页。现在必须走 place：location + 同游 + 主页详情。
var formerlyDefaultedPlaceHomepageTypes = []string{
	"ancient_town",
	"check_in_spot",
	"city",
	"heritage_site",
	"hot_spring",
	"hotel",
	"museum",
	"natural_landscape",
	"park",
	"religious_site",
	"restaurant",
	"theme_park",
	"transport_hub",
}

func TestFormerlyDefaultedHomepageTypesResolveToPlace(t *testing.T) {
	for _, objectType := range formerlyDefaultedPlaceHomepageTypes {
		kind := generated.IntersectionObjectKindByObjectType[objectType]
		if kind != "place" {
			t.Fatalf("objectType %q: objectKind = %q, want place", objectType, kind)
		}
		if got := generated.IntersectionDimensionByObjectKind[kind]; got != "location" {
			t.Fatalf("objectType %q: dimension = %q, want location", objectType, got)
		}
		if got := generated.IntersectionLabelByObjectKind[kind]; got != "同游" {
			t.Fatalf("objectType %q: label = %q, want 同游", objectType, got)
		}
	}
}

func TestPlaceHomepagesDoNotRouteToUserProfile(t *testing.T) {
	for _, objectType := range formerlyDefaultedPlaceHomepageTypes {
		kind := generated.IntersectionObjectKindByObjectType[objectType]
		route := generated.IntersectionRouteIDByObjectKind[kind]
		if route == "userProfile" {
			t.Fatalf("objectType %q routes to userProfile; a museum is not a person", objectType)
		}
		if route != "homepageDetail" {
			t.Fatalf("objectType %q: routeId = %q, want homepageDetail", objectType, route)
		}
	}
}

func TestPersonAndCircleKeepTheirOwnSemantics(t *testing.T) {
	cases := map[string]struct {
		kind      string
		dimension string
		label     string
		route     string
	}{
		"user":   {kind: "person", dimension: "interest", label: "同好", route: "userProfile"},
		"person": {kind: "person", dimension: "interest", label: "同好", route: "userProfile"},
		"circle": {kind: "circle", dimension: "relationship", label: "同圈", route: "circleDetail"},
	}
	for objectType, want := range cases {
		kind := generated.IntersectionObjectKindByObjectType[objectType]
		if kind != want.kind {
			t.Fatalf("objectType %q: objectKind = %q, want %q", objectType, kind, want.kind)
		}
		if got := generated.IntersectionDimensionByObjectKind[kind]; got != want.dimension {
			t.Fatalf("objectType %q: dimension = %q, want %q", objectType, got, want.dimension)
		}
		if got := generated.IntersectionLabelByObjectKind[kind]; got != want.label {
			t.Fatalf("objectType %q: label = %q, want %q", objectType, got, want.label)
		}
		if got := generated.IntersectionRouteIDByObjectKind[kind]; got != want.route {
			t.Fatalf("objectType %q: routeId = %q, want %q", objectType, got, want.route)
		}
	}
}

func TestSchoolHomepagesKeepTheAlumniReading(t *testing.T) {
	// 学校既不是人也不是纯地点：维度仍是 identity（同校是身份共同点），
	// 但落点是主页详情，不能借道个人主页。
	for _, objectType := range []string{"university", "school"} {
		kind := generated.IntersectionObjectKindByObjectType[objectType]
		if kind != "school" {
			t.Fatalf("objectType %q: objectKind = %q, want school", objectType, kind)
		}
		if got := generated.IntersectionLabelByObjectKind[kind]; got != "同校" {
			t.Fatalf("objectType %q: label = %q, want 同校", objectType, got)
		}
		if got := generated.IntersectionRouteIDByObjectKind[kind]; got != "homepageDetail" {
			t.Fatalf("objectType %q: routeId = %q, want homepageDetail", objectType, got)
		}
	}
}

func TestPortableGearReadsAsSharedInterestNotSharedPlace(t *testing.T) {
	// 车型主页与相机机身一样是「带着走的装备」：共用一台是兴趣事实，不是同地事实，
	// 所以维度是 interest / 同好。旧实现里 vehicle 落 default 也得到同好，但 objectKind
	// 为空、点不进主页；现在语义相同而落点补齐。
	for _, objectType := range []string{"vehicle", "gear"} {
		kind := generated.IntersectionObjectKindByObjectType[objectType]
		if kind != "gear" {
			t.Fatalf("objectType %q: objectKind = %q, want gear", objectType, kind)
		}
		if got := generated.IntersectionDimensionByObjectKind[kind]; got != "interest" {
			t.Fatalf("objectType %q: dimension = %q, want interest", objectType, got)
		}
		if got := generated.IntersectionRouteIDByObjectKind[kind]; got != "homepageDetail" {
			t.Fatalf("objectType %q: routeId = %q, want homepageDetail", objectType, got)
		}
	}
}

func TestEveryDeclaredHomepageTypeIsBound(t *testing.T) {
	for _, objectType := range declaredHomepageTypes(t) {
		kind := generated.IntersectionObjectKindByObjectType[objectType]
		if kind == "" {
			t.Fatalf("HomepageType %q has no objectTypeBindings entry; the intersection surface would silently treat it as a person", objectType)
		}
		if generated.IntersectionDimensionByObjectKind[kind] == "" {
			t.Fatalf("HomepageType %q resolves to objectKind %q without a dimension", objectType, kind)
		}
		if generated.IntersectionLabelByObjectKind[kind] == "" {
			t.Fatalf("HomepageType %q resolves to objectKind %q without a label", objectType, kind)
		}
	}
}

func TestUnknownObjectTypeResolvesToNothing(t *testing.T) {
	// 查不到时必须落空串，让上游降级为不可导航；旧 switch 的 default 会把它当人物，
	// 于是一个拼错的 objectType 也能生成「同好」并跳到个人主页。
	for _, objectType := range []string{"", "  ", "musuem", "not_a_type"} {
		if kind := generated.IntersectionObjectKindByObjectType[objectType]; kind != "" {
			t.Fatalf("objectType %q: objectKind = %q, want empty", objectType, kind)
		}
	}
}

func declaredHomepageTypes(t *testing.T) []string {
	t.Helper()
	path := filepath.Join(repoRootForBindings(t), "quwoquan_service/contracts/metadata/_shared/types.yaml")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read shared types: %v", err)
	}
	var document struct {
		Enums map[string][]string `yaml:"enums"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatalf("parse shared types: %v", err)
	}
	values := document.Enums["HomepageType"]
	if len(values) == 0 {
		t.Fatalf("shared types declare no HomepageType values")
	}
	return values
}

func repoRootForBindings(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "quwoquan_service/contracts/metadata/_shared/types.yaml")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatalf("repository root not found from test working directory")
		}
		dir = parent
	}
}
