// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
package recommendation_test

import (
	"reflect"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

func TestDiscoveryFeedCandidateProjectionIsMinimalAndReleaseBound(t *testing.T) {
	projection := recinfra.DiscoveryFeedCandidateProjection()
	keys := make(map[string]any, len(projection))
	for _, element := range projection {
		keys[element.Key] = element.Value
	}
	for _, required := range []string{
		"postId", "contentType", "authorId", "publishedAt", "recScore",
		"qualityScore", "supplySource", "sourceOwner", "releaseId",
		"manifestDigest", "lifecycleStatus",
	} {
		if keys[required] != 1 {
			t.Fatalf("candidate projection missing %s: %#v", required, projection)
		}
	}
	for _, forbidden := range []string{
		"body", "summary", "mediaItems", "mediaUrls", "videoUrl",
		"articleMarkdown", "articleAssetManifest", "semanticMentions",
	} {
		if _, ok := keys[forbidden]; ok {
			t.Fatalf("candidate projection must not fetch %s: %#v", forbidden, projection)
		}
	}
}

func TestDiscoveryFeedIndexModelsMatchStableReadOrders(t *testing.T) {
	models := recinfra.DiscoveryFeedIndexModels()
	actual := make(map[string]bson.D, len(models))
	unique := make(map[string]bool, len(models))
	for _, model := range models {
		resolved := &options.IndexOptions{}
		for _, apply := range model.Options.List() {
			if err := apply(resolved); err != nil {
				t.Fatalf("resolve index options: %v", err)
			}
		}
		if resolved.Name == nil {
			t.Fatalf("index is missing canonical name: %#v", model)
		}
		keys, ok := model.Keys.(bson.D)
		if !ok {
			t.Fatalf("index %s keys type = %T, want bson.D", *resolved.Name, model.Keys)
		}
		actual[*resolved.Name] = keys
		unique[*resolved.Name] = resolved.Unique != nil && *resolved.Unique
	}

	wantCanonical := bson.D{
		{Key: "status", Value: 1},
		{Key: "visibility", Value: 1},
		{Key: "sourceOwner", Value: 1},
		{Key: "releaseId", Value: 1},
		{Key: "manifestDigest", Value: 1},
		{Key: "lifecycleStatus", Value: 1},
		{Key: "recScore", Value: -1},
		{Key: "publishedAt", Value: -1},
		{Key: "postId", Value: -1},
	}
	if !reflect.DeepEqual(actual["idx_df_active_release_recency"], wantCanonical) {
		t.Fatalf(
			"active release index drift: got=%#v want=%#v",
			actual["idx_df_active_release_recency"],
			wantCanonical,
		)
	}
	if !unique["uq_df_post_id"] {
		t.Fatal("postId projection identity must be unique")
	}
	for _, name := range []string{
		"idx_df_recommend_recency",
		"idx_df_recommend_vertical_recency",
		"idx_df_active_release_vertical_recency",
		"idx_df_type_recency",
		"idx_df_author_recency",
	} {
		if len(actual[name]) == 0 {
			t.Fatalf("missing declared read-path index %s", name)
		}
	}
}
