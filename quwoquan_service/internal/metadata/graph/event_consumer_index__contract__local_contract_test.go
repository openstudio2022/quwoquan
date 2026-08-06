package graph

import (
	"reflect"
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

func TestEventConsumerIndexUsesObjectLifecycleEdges(t *testing.T) {
	t.Parallel()

	index := BuildEventConsumerIndex([]ast.Object{
		{
			ID: "recommendation.recommendation_candidate_index_view",
			Lifecycle: &ast.LifecycleDefinition{
				SourceEvents: []string{
					"content.post.PostPublished",
					"content.post.PostPublished",
				},
				EventConsumers: []ast.LifecycleEventConsumer{{
					Name: "ProjectCandidateIndex", Kind: "projector",
					Facet: "CandidateIndexProjector", Method: "apply", Idempotency: "event_id",
				}},
			},
		},
		{
			ID: "search.post_index_view",
			Lifecycle: &ast.LifecycleDefinition{
				SourceEvents: []string{"content.post.PostPublished"},
				EventConsumers: []ast.LifecycleEventConsumer{{
					Name: "ProjectPostIndex", Kind: "projector",
					Facet: "PostIndexProjector", Method: "apply", Idempotency: "event_id",
				}},
			},
		},
	})
	want := []string{
		"recommendation.recommendation_candidate_index_view",
		"search.post_index_view",
	}
	if !reflect.DeepEqual(index["content.post.PostPublished"], want) {
		t.Fatalf("reverse consumers = %v, want %v", index["content.post.PostPublished"], want)
	}
}
