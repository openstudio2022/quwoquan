package application

import (
	"reflect"
	"testing"

	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

func TestNormalizePostObjectAnchorsPrefersCanonicalAndDropsRetiredRefs(t *testing.T) {
	post := &postmodel.Post{
		PrimaryHomepageId:   "homepage_sight_west_lake",
		PrimaryHomepageType: "sight",
		EntityRefs: []string{
			"sight/homepage_sight_west_lake",
			"/entity/地点/景区/西湖",
			"entity:sight:west_lake",
			"entity:sight:west_lake",
		},
	}

	normalizePostObjectAnchors(post, map[string]any{
		"primaryHomepageId":   "homepage_sight_west_lake",
		"primaryHomepageType": "sight",
		"primaryHomepageSnapshot": map[string]any{
			"title":             "西湖景区",
			"canonicalEntityId": "entity:sight:west_lake",
		},
		"entityRefs": []any{
			"sight/homepage_sight_west_lake",
			"/entity/地点/景区/西湖",
			"entity:sight:west_lake",
			"entity:sight:west_lake",
		},
	})

	if got, want := post.CanonicalEntityId, "entity:sight:west_lake"; got != want {
		t.Fatalf("CanonicalEntityId = %q, want %q", got, want)
	}
	wantRefs := []string{"entity:sight:west_lake"}
	if !reflect.DeepEqual(post.EntityRefs, wantRefs) {
		t.Fatalf("EntityRefs = %#v, want %#v", post.EntityRefs, wantRefs)
	}
}

func TestCanonicalEntityIDFromHomepageInfersFromHomepageID(t *testing.T) {
	if got, want := canonicalEntityIDFromHomepage("homepage_sight_west_lake", ""), "entity:sight:west_lake"; got != want {
		t.Fatalf("canonicalEntityIDFromHomepage inferred %q, want %q", got, want)
	}
	if got := canonicalEntityIDFromHomepage("homepage_unknown_demo", ""); got != "" {
		t.Fatalf("canonicalEntityIDFromHomepage should stay empty for unknown type, got %q", got)
	}
}
