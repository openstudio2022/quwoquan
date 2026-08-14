// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-object-taxonomy-and-provider-registry/spec.md#gwt-001
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-object-taxonomy-and-provider-registry/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-object-taxonomy-and-provider-registry/spec.md#gwt-001.t3
package search

import "testing"

// TestLocationTargetWiring pins the additive R-S05e location target: the
// first-party place object (location.place) round-trips to/from TargetLocation
// and is part of the AI-facing allowlist. It is the runtime counterpart of the
// metadata ai_targets.location entry (TestAITargetsMatchRuntimeAllowlist pins
// the metadata side).
func TestLocationTargetWiring(t *testing.T) {
	if got := TargetForDocument(Document{ObjectType: ObjectTypeLocation}); got != TargetLocation {
		t.Fatalf("TargetForDocument(location.place)=%q want %q", got, TargetLocation)
	}
	mapped := ObjectTypesForTargets([]Target{TargetLocation})
	if len(mapped) != 1 || mapped[0] != ObjectTypeLocation {
		t.Fatalf("ObjectTypesForTargets([location])=%v want [%q]", mapped, ObjectTypeLocation)
	}
	if !targetAllowed(TargetLocation) {
		t.Fatalf("TargetLocation must be in AllTargets allowlist")
	}
}

// TestGeoDimensionSymbolsPreserved is a compile+behavior guard that the reused
// cross-object geo dimension was not removed while layering location on top: a
// place object carries its location via Document.Geo and surfaces PlaceName +
// DistanceKm on a hit under an active Near filter (single geo mechanism).
func TestGeoDimensionSymbolsPreserved(t *testing.T) {
	near := &GeoNear{Lat: 30.0, Lng: 120.0, RadiusKm: 5}
	if !near.Active() {
		t.Fatalf("GeoNear.Active must report true for a positive radius")
	}
	doc := Document{
		ObjectType: ObjectTypeLocation,
		ObjectID:   "place_x",
		Geo:        &GeoPoint{Lat: 30.0, Lng: 120.0},
		Fields:     map[string]string{"placeName": "西湖"},
	}
	pass, distKm, _ := nearMatch(near, doc)
	if !pass {
		t.Fatalf("a place at the pin must pass the near filter")
	}
	if distKm < 0 {
		t.Fatalf("distanceKm must be non-negative, got %v", distKm)
	}
	// The hit projection surfaces the geo dimension fields.
	hit := RetrieveHit{Geo: doc.Geo, PlaceName: doc.Fields["placeName"], DistanceKm: distKm}
	m := RetrieveHitMap(hit)
	if _, ok := m["geo"]; !ok {
		t.Fatalf("RetrieveHitMap must surface geo when present: %#v", m)
	}
	if m["placeName"] != "西湖" {
		t.Fatalf("RetrieveHitMap must surface placeName: %#v", m)
	}
}
