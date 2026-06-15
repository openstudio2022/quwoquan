package application

import (
	"reflect"
	"testing"
)

func TestCanonicalEntityIDInfersSemanticSlug(t *testing.T) {
	if got, want := canonicalEntityID("homepage_sight_west_lake", ""), "entity:sight:west_lake"; got != want {
		t.Fatalf("canonicalEntityID = %q, want %q", got, want)
	}
	if got := canonicalEntityID("homepage_unknown_demo", ""); got != "" {
		t.Fatalf("canonicalEntityID should stay empty for unknown type, got %q", got)
	}
}

func TestHomepageSourceRefsSkipsRetiredHomepageFallback(t *testing.T) {
	homepage := &Homepage{
		ID:                "homepage_sight_west_lake",
		CanonicalEntityID: "",
	}
	got := homepageSourceRefs(homepage)
	want := []string{"entity-service/homepage/homepage_sight_west_lake"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("homepageSourceRefs = %#v, want %#v", got, want)
	}
}
