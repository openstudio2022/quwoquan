package search

import (
	"context"
	"testing"
)

// nearbyDocs places three entity homepages around a West Lake (杭州) pin: one very
// close, one ~16km away, and one with NO geo dimension at all.
func nearbyDocs() []Document {
	return []Document{
		{
			ObjectType: ObjectTypeEntityHomepage, ObjectID: "hp_close",
			Title: "西湖游船主页", Visibility: "public",
			Geo:    &GeoPoint{Lat: 30.2431, Lng: 120.1505},
			Fields: map[string]string{"placeName": "杭州"},
		},
		{
			ObjectType: ObjectTypeEntityHomepage, ObjectID: "hp_mid",
			Title: "湘湖露营主页", Visibility: "public",
			Geo:    &GeoPoint{Lat: 30.1700, Lng: 120.2200},
			Fields: map[string]string{"placeName": "萧山"},
		},
		{
			ObjectType: ObjectTypeEntityHomepage, ObjectID: "hp_far",
			Title: "千岛湖主页", Visibility: "public",
			Geo:    &GeoPoint{Lat: 29.6050, Lng: 119.0300},
			Fields: map[string]string{"placeName": "淳安"},
		},
		{
			ObjectType: ObjectTypeEntityHomepage, ObjectID: "hp_nogeo",
			Title: "无坐标主页", Visibility: "public",
		},
	}
}

// pin is the West Lake reference point used by the nearby tests.
var pinLat, pinLng = 30.2500, 120.1500

func TestRetrieveNearHardFilterExcludesOutsideRadiusAndNonGeo(t *testing.T) {
	resp, err := Retrieve(context.Background(), RetrieveRequest{
		Targets: []Target{TargetEntity},
		Filters: RetrieveFilters{Near: &GeoNear{Lat: pinLat, Lng: pinLng, RadiusKm: 5}},
	}, NewSliceBackend(nearbyDocs()), Viewer{})
	if err != nil {
		t.Fatalf("retrieve err=%v", err)
	}
	if len(resp.Hits) != 1 {
		t.Fatalf("near=5km must keep only hp_close, got %#v", resp.Hits)
	}
	hit := resp.Hits[0]
	if hit.ObjectID != "hp_close" {
		t.Fatalf("top=%q want hp_close", hit.ObjectID)
	}
	// Distance + place dimension must surface on the hit (read-only, never synthesized client-side).
	if hit.DistanceKm <= 0 || hit.DistanceKm > 5 {
		t.Fatalf("hp_close distanceKm=%v want (0,5]", hit.DistanceKm)
	}
	if hit.Geo == nil || hit.PlaceName != "杭州" {
		t.Fatalf("location dimension missing on hit: geo=%#v place=%q", hit.Geo, hit.PlaceName)
	}
}

func TestRetrieveNearProximityRanksCloserHigher(t *testing.T) {
	// A wide radius keeps both geo candidates; the closer one must outrank the
	// farther one purely on proximity (no terms, equal popularity/freshness).
	resp, err := Retrieve(context.Background(), RetrieveRequest{
		Targets: []Target{TargetEntity},
		Filters: RetrieveFilters{Near: &GeoNear{Lat: pinLat, Lng: pinLng, RadiusKm: 30}},
	}, NewSliceBackend(nearbyDocs()), Viewer{})
	if err != nil {
		t.Fatalf("retrieve err=%v", err)
	}
	// hp_close (~0.8km) and hp_mid (~10km) are inside 30km; hp_far (~110km) and
	// hp_nogeo are excluded.
	if len(resp.Hits) != 2 {
		t.Fatalf("near=30km must keep hp_close+hp_mid only, got %#v", resp.Hits)
	}
	if resp.Hits[0].ObjectID != "hp_close" || resp.Hits[1].ObjectID != "hp_mid" {
		t.Fatalf("proximity order wrong: %#v", resp.Hits)
	}
	if !(resp.Hits[0].DistanceKm < resp.Hits[1].DistanceKm) {
		t.Fatalf("closer hit must have smaller distance: %v vs %v", resp.Hits[0].DistanceKm, resp.Hits[1].DistanceKm)
	}
	if !(resp.Hits[0].Score > resp.Hits[1].Score) {
		t.Fatalf("closer hit must score higher: %v vs %v", resp.Hits[0].Score, resp.Hits[1].Score)
	}
}

func TestRetrieveNearCombinesWithTerms(t *testing.T) {
	// "露营" + 附近: only the nearby camping homepage qualifies (term AND radius).
	resp, err := Retrieve(context.Background(), RetrieveRequest{
		Targets: []Target{TargetEntity},
		Terms:   []string{"露营"},
		Filters: RetrieveFilters{Near: &GeoNear{Lat: pinLat, Lng: pinLng, RadiusKm: 30}},
	}, NewSliceBackend(nearbyDocs()), Viewer{})
	if err != nil {
		t.Fatalf("retrieve err=%v", err)
	}
	if len(resp.Hits) != 1 || resp.Hits[0].ObjectID != "hp_mid" {
		t.Fatalf("term+near must keep only the nearby camping homepage, got %#v", resp.Hits)
	}
}

func TestRetrieveWithoutNearKeepsNonGeoCandidates(t *testing.T) {
	// Regression guard: when Near is absent, non-geo candidates are NOT excluded.
	resp, err := Retrieve(context.Background(), RetrieveRequest{
		Targets: []Target{TargetEntity},
		Terms:   []string{"主页"},
	}, NewSliceBackend(nearbyDocs()), Viewer{})
	if err != nil {
		t.Fatalf("retrieve err=%v", err)
	}
	sawNoGeo := false
	for _, h := range resp.Hits {
		if h.ObjectID == "hp_nogeo" {
			sawNoGeo = true
		}
		if h.DistanceKm != 0 {
			t.Fatalf("no Near query must not set distanceKm, got %v on %s", h.DistanceKm, h.ObjectID)
		}
	}
	if !sawNoGeo {
		t.Fatalf("non-geo candidate must survive when Near is absent, got %#v", resp.Hits)
	}
}

func TestRetrieveNearInactiveRadiusIsNoOp(t *testing.T) {
	// A zero radius is "no nearby constraint": all matching candidates remain.
	resp, err := Retrieve(context.Background(), RetrieveRequest{
		Targets: []Target{TargetEntity},
		Terms:   []string{"主页"},
		Filters: RetrieveFilters{Near: &GeoNear{Lat: pinLat, Lng: pinLng, RadiusKm: 0}},
	}, NewSliceBackend(nearbyDocs()), Viewer{})
	if err != nil {
		t.Fatalf("retrieve err=%v", err)
	}
	if len(resp.Hits) != 4 {
		t.Fatalf("inactive near must keep all 4 homepages, got %#v", resp.Hits)
	}
}
