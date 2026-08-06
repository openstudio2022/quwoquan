// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/domain-service-directory-ownership/spec.md#gwt-001
package load

import (
	"reflect"
	"testing"

	"gopkg.in/yaml.v3"

	"quwoquan_service/internal/metadata/ast"
)

func TestDecodeLifecycleOwnsCanonicalEventConsumerEdge(t *testing.T) {
	t.Parallel()

	var node yaml.Node
	if err := yaml.Unmarshal([]byte(`
source_events:
  - content.post.PostPublished
checkpoint: aggregate_version
rebuild: replay_authoritative_events
tombstone: retain_checkpoint
event_consumers:
  - name: ProjectPublishedPost
    kind: projector
    facet: PublishedPostProjector
    method: apply
    idempotency: aggregate_version
`), &node); err != nil {
		t.Fatal(err)
	}
	got, err := decodeLifecycle(node.Content[0], "content/feed/published_post/object.yaml")
	if err != nil {
		t.Fatal(err)
	}
	wantConsumers := []ast.LifecycleEventConsumer{{
		Name:        "ProjectPublishedPost",
		Kind:        "projector",
		Facet:       "PublishedPostProjector",
		Method:      "apply",
		Idempotency: "aggregate_version",
	}}
	if !reflect.DeepEqual(got.SourceEvents, []string{"content.post.PostPublished"}) ||
		!reflect.DeepEqual(got.EventConsumers, wantConsumers) ||
		got.Checkpoint != "aggregate_version" || got.Rebuild != "replay_authoritative_events" ||
		got.Tombstone != "retain_checkpoint" {
		t.Fatalf("lifecycle=%+v", got)
	}
}

func TestDecodeLifecycleRejectsSecondConsumerEdgeVocabulary(t *testing.T) {
	t.Parallel()

	var node yaml.Node
	if err := yaml.Unmarshal([]byte(`
source_events: [content.post.PostPublished]
event_consumers:
  - name: ProjectPublishedPost
    kind: projector
    facet: PublishedPostProjector
    method: apply
    idempotency: aggregate_version
    events: [content.post.PostPublished]
`), &node); err != nil {
		t.Fatal(err)
	}
	if _, err := decodeLifecycle(node.Content[0], "content/feed/published_post/object.yaml"); err == nil {
		t.Fatal("consumer-local events alias must be rejected; lifecycle.source_events is the only edge")
	}
}
