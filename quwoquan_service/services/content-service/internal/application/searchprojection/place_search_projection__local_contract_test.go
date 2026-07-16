package searchprojection

import (
	"testing"

	rtsearch "quwoquan_service/runtime/search"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

func TestGeohashEncodeKnownVector(t *testing.T) {
	// Classic geohash reference point: (57.64911, 10.40744) -> "u4pruydqqvj8...".
	if got := geohashEncode(57.64911, 10.40744, 5); got != "u4pru" {
		t.Fatalf("geohashEncode precision5 = %q want %q", got, "u4pru")
	}
}

func TestCanonicalPlaceIDStability(t *testing.T) {
	geo := &rtsearch.GeoPoint{Lat: 30.6571, Lng: 104.0648}
	a := CanonicalPlaceID("宽窄巷子", geo)
	// Same name + a coordinate inside the same coarse cell => same identity.
	b := CanonicalPlaceID(" 宽窄巷子 ", &rtsearch.GeoPoint{Lat: 30.6580, Lng: 104.0650})
	if a == "" || a != b {
		t.Fatalf("same place must converge: a=%q b=%q", a, b)
	}
	// A different name => different identity.
	if c := CanonicalPlaceID("锦里", geo); c == a {
		t.Fatalf("different names must not collide: %q", c)
	}
	// Empty name => no identity.
	if got := CanonicalPlaceID("   ", nil); got != "" {
		t.Fatalf("empty name must yield empty id, got %q", got)
	}
	// Stable prefix + length for downstream ids.
	if len(a) != len("place_")+16 {
		t.Fatalf("unexpected id shape: %q", a)
	}
}

func TestDerivePlaceRefEligibility(t *testing.T) {
	base := postmodel.Post{
		ID: "p1", Status: "published", Visibility: "public",
		LocationName: "洱海", Location: postmodel.GeoPoint{Latitude: 25.9, Longitude: 100.2},
	}
	if ref, ok := DerivePlaceRef(base); !ok || ref.PlaceID == "" || ref.Name != "洱海" || ref.Geo == nil {
		t.Fatalf("eligible free-text place must derive a ref: ok=%v ref=%#v", ok, ref)
	}

	bound := base
	bound.PrimaryHomepageId = "homepage_123"
	if _, ok := DerivePlaceRef(bound); ok {
		t.Fatalf("a place bound to a canonical entity must NOT derive a place (entity.homepage carries it)")
	}

	homed := base
	homed.PrimaryHomepageId = "homepage_456"
	if _, ok := DerivePlaceRef(homed); ok {
		t.Fatalf("a place bound to a primary homepage must NOT derive a place")
	}

	for _, tc := range []struct {
		name string
		post postmodel.Post
	}{
		{"draft", func() postmodel.Post { p := base; p.Status = "draft"; return p }()},
		{"private", func() postmodel.Post { p := base; p.Visibility = "private"; return p }()},
		{"no-name", func() postmodel.Post { p := base; p.LocationName = "  "; return p }()},
	} {
		if _, ok := DerivePlaceRef(tc.post); ok {
			t.Fatalf("%s post must not derive a place", tc.name)
		}
	}
}

func TestProjectPlaceToSearchDocument(t *testing.T) {
	snap := PlaceSnapshot{
		PlaceID:    "place_abc",
		Name:       "洱海",
		Geo:        &rtsearch.GeoPoint{Lat: 25.9, Lng: 100.2},
		RefPostIDs: []string{"p1", "p2"},
	}
	doc := ProjectPlaceToSearchDocument(snap)
	if doc.ObjectType != rtsearch.ObjectTypeLocation || doc.ObjectID != "place_abc" {
		t.Fatalf("bad object identity: %#v", doc)
	}
	if rtsearch.TargetForDocument(doc) != rtsearch.TargetLocation {
		t.Fatalf("place doc must resolve to TargetLocation")
	}
	if doc.Title != "洱海" || doc.Fields["placeName"] != "洱海" {
		t.Fatalf("name must drive Title + placeName: %#v", doc)
	}
	if doc.Geo == nil || doc.Geo.Lat != 25.9 {
		t.Fatalf("geo dimension must be reused: %#v", doc.Geo)
	}
	if doc.Popularity != 2 {
		t.Fatalf("popularity must reflect reference count, got %v", doc.Popularity)
	}
}
