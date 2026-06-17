package application

import (
	"testing"
)

func TestProjectHomepageFillsGeoFromRealLocation(t *testing.T) {
	hp := Homepage{
		ID:                "hp_1",
		Title:             "西湖游船主页",
		CanonicalEntityID: "entity:sight:xihu",
		City:              "杭州",
		Address:           "龙井路",
		Location:          &GeoPoint{Latitude: 30.2431, Longitude: 120.1505},
		RatingCount:       42,
	}
	got := ProjectHomepageToSearchDocument(hp)
	if got.Geo == nil {
		t.Fatalf("geo must be filled from Homepage.location")
	}
	if got.Geo.Lat != 30.2431 || got.Geo.Lng != 120.1505 {
		t.Fatalf("geo coords wrong: %#v", got.Geo)
	}
	// placeName is the administrative place (city); entity itself IS the place so
	// no synthetic placeId is set.
	if got.Fields["placeName"] != "杭州" {
		t.Fatalf("placeName=%q want 杭州", got.Fields["placeName"])
	}
	if _, ok := got.Fields["placeId"]; ok {
		t.Fatalf("entity must not synthesize a placeId: %#v", got.Fields)
	}
	// entityId anchor still flows for reverse lookup.
	if got.Fields["entityId"] != "entity:sight:xihu" {
		t.Fatalf("entityId anchor missing: %#v", got.Fields)
	}
}

func TestProjectHomepageWithoutLocationLeavesGeoNil(t *testing.T) {
	hp := Homepage{
		ID:                "hp_2",
		Title:             "无坐标主页",
		CanonicalEntityID: "entity:topic:none",
		City:              "成都",
	}
	got := ProjectHomepageToSearchDocument(hp)
	if got.Geo != nil {
		t.Fatalf("missing location must leave Geo nil (no fabricated coords), got %#v", got.Geo)
	}
	if got.Fields["placeName"] != "成都" {
		t.Fatalf("placeName should still carry the city: %#v", got.Fields)
	}
}
