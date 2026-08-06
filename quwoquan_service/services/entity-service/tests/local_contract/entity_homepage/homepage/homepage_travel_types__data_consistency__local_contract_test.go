package local_contract

import (
	"testing"

	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
)

// 旅行垂类下钻宾语进入 HomepageType 后，准入、模板与身份三件事必须同时成立：
// 准入决定主页能否建立，模板决定页面长什么样，canonicalEntityId 决定它是不是同一个对象。
func TestTravelDrilldownHomepageTypesAreAdmitted(t *testing.T) {
	// gear 在这里的意义与其他三个不同：交集 registry 已把 gear 登记为 objectKind，
	// 但在它成为 HomepageType 之前，器材主页建不出来，「用过同一台机身」无处落点。
	for _, value := range []string{"transport_hub", "city", "route", "photo_spot", "gear"} {
		if !homepagemodel.ValidHomepageType(value) {
			t.Fatalf("homepage type %q must be admitted", value)
		}
	}
}

func TestHomepageTypesMatchTheDeclaredClosedSet(t *testing.T) {
	types := homepagemodel.HomepageTypes()
	seen := make(map[string]struct{}, len(types))
	for _, value := range types {
		if _, duplicate := seen[value]; duplicate {
			t.Fatalf("homepage type %q is declared twice", value)
		}
		seen[value] = struct{}{}
		if !homepagemodel.ValidHomepageType(value) {
			t.Fatalf("declared homepage type %q is not admitted", value)
		}
	}
	if homepagemodel.ValidHomepageType("photo_spots") {
		t.Fatal("unknown homepage type must be rejected rather than coerced")
	}

	// 返回的是副本：调用方改写不得污染准入闭集。
	types[0] = "mutated"
	if !homepagemodel.ValidHomepageType(homepagemodel.HomepageTypes()[0]) {
		t.Fatal("HomepageTypes must return a defensive copy")
	}
}

func TestSchoolHomepageTypeIsAdmittedAsItsOwnCampusIdentity(t *testing.T) {
	if !homepagemodel.ValidHomepageType("school") {
		t.Fatal("metadata-declared school homepage type must be admitted")
	}
	if got := homepagemodel.ObjectPageTemplate("school", ""); got != "campus" {
		t.Fatalf("school template = %q, want campus", got)
	}
	if got := homepagemodel.CanonicalEntityID("school", "新东方学校"); got != "entity:school:新东方学校" {
		t.Fatalf("school canonical entity id = %q", got)
	}
	if school, university := homepagemodel.CanonicalEntityID("school", "示例"), homepagemodel.CanonicalEntityID("university", "示例"); school == university {
		t.Fatal("school and university must remain distinct canonical homepage identities")
	}
}

func TestObjectPageTemplateSeparatesPlacesFromRoutes(t *testing.T) {
	for _, value := range []string{"transport_hub", "city", "photo_spot"} {
		if got := homepagemodel.ObjectPageTemplate(value, ""); got != "travel_photo" {
			t.Fatalf("homepage type %q template = %q, want travel_photo", value, got)
		}
	}
	// route 是多站点序列、gear 是器材而非地点；两者都不该套用以封面为主的 travel_photo。
	for _, value := range []string{"route", "gear"} {
		if got := homepagemodel.ObjectPageTemplate(value, ""); got != "standard" {
			t.Fatalf("homepage type %q template = %q, want standard", value, got)
		}
	}
	for _, value := range []string{"university", "school"} {
		if got := homepagemodel.ObjectPageTemplate(value, ""); got != "campus" {
			t.Fatalf("%s template = %q, want campus", value, got)
		}
	}
	// 显式模板优先，避免类型映射覆盖数据侧已声明的版式。
	if got := homepagemodel.ObjectPageTemplate("route", "campus"); got != "campus" {
		t.Fatalf("explicit template must win, got %q", got)
	}
}

func TestPhotoSpotIdentityIsDistinctFromTravelPhoto(t *testing.T) {
	spot := homepagemodel.CanonicalEntityID("photo_spot", "断桥残雪")
	album := homepagemodel.CanonicalEntityID("travel_photo", "断桥残雪")
	if spot == album {
		t.Fatal("photo_spot and travel_photo must not collapse into one canonical entity")
	}
	if spot == "" || album == "" {
		t.Fatalf("canonical entity id must be derivable, got %q and %q", spot, album)
	}
}
