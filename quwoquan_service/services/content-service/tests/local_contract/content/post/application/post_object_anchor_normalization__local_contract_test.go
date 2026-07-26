package post_test

import (
	. "quwoquan_service/services/content-service/internal/content/post/application"
	"reflect"
	"testing"

	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
)

func TestNormalizePostObjectAnchorsKeepsOnlyExplicitRegisteredReferences(t *testing.T) {
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

	NormalizePostObjectAnchors(post, map[string]any{
		"primaryHomepageId":   "homepage_sight_west_lake",
		"primaryHomepageType": "sight",
		"primaryHomepageSnapshot": map[string]any{
			"title": "西湖景区",
		},
		"entityRefs": []any{
			"sight/homepage_sight_west_lake",
			"/entity/地点/景区/西湖",
			"entity:sight:west_lake",
			"entity:sight:west_lake",
		},
	})

	wantRefs := []string{"entity:sight:west_lake"}
	if !reflect.DeepEqual(post.EntityRefs, wantRefs) {
		t.Fatalf("EntityRefs = %#v, want %#v", post.EntityRefs, wantRefs)
	}
}

func TestNormalizePostObjectAnchorsDoesNotInferCrossContextReferences(t *testing.T) {
	post := &postmodel.Post{}
	NormalizePostObjectAnchors(post, map[string]any{
		"primaryHomepageId":   "homepage_sight_west_lake",
		"primaryHomepageType": "sight",
	})
	if len(post.EntityRefs) != 0 {
		t.Fatalf("cross-context references must be explicit, got %#v", post.EntityRefs)
	}
}
