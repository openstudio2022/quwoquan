// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
package local_contract

import (
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestProfileInteractionActivityDeclaresEveryComposedOutboxSource(t *testing.T) {
	_, sourcePath, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(sourcePath), "../../../.."))
	data, err := os.ReadFile(filepath.Join(root, "contracts", "content", "profile_interaction_activity_view", "object.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Lifecycle struct {
			SourceEvents []string `yaml:"source_events"`
			Checkpoint   string   `yaml:"checkpoint"`
			Rebuild      string   `yaml:"rebuild"`
			Tombstone    string   `yaml:"tombstone"`
			Idempotency  string   `yaml:"idempotency"`
			Consumers    []struct {
				Name        string `yaml:"name"`
				Kind        string `yaml:"kind"`
				Facet       string `yaml:"facet"`
				Method      string `yaml:"method"`
				Idempotency string `yaml:"idempotency"`
			} `yaml:"event_consumers"`
		} `yaml:"lifecycle"`
	}
	if err := yaml.Unmarshal(data, &document); err != nil {
		t.Fatal(err)
	}
	want := []string{
		"content.content_reaction.ContentReactionSet",
		"content.content_reaction.ContentReactionCleared",
		"content.comment.CommentCreated",
		"content.comment.CommentDeleted",
		"content.outbound_share_fact.OutboundShareRecorded",
		"content.post.PostDeleted",
		"content.profile_interaction_read_fact.ProfileInteractionReadFactAppended",
	}
	if !reflect.DeepEqual(document.Lifecycle.SourceEvents, want) {
		t.Fatalf("profile interaction lifecycle sources drifted: %#v", document.Lifecycle.SourceEvents)
	}
	if document.Lifecycle.Checkpoint != "per_source_outbox_publication_state" ||
		document.Lifecycle.Rebuild != "replay_reaction_comment_share_post_and_read_fact_outboxes" ||
		document.Lifecycle.Tombstone != "deactivate_source_activity_or_mark_target_unavailable" ||
		document.Lifecycle.Idempotency != "aggregate_version" {
		t.Fatalf("profile interaction lifecycle policy drifted: %#v", document.Lifecycle)
	}
	if len(document.Lifecycle.Consumers) != 1 {
		t.Fatalf("profile interaction lifecycle consumers = %#v, want one", document.Lifecycle.Consumers)
	}
	consumer := document.Lifecycle.Consumers[0]
	if consumer.Name != "ProjectProfileInteractionActivity" || consumer.Kind != "projector" ||
		consumer.Facet != "ProfileInteractionActivityViewProjector" || consumer.Method != "apply" ||
		consumer.Idempotency != "aggregate_version" {
		t.Fatalf("profile interaction lifecycle consumer drifted: %#v", consumer)
	}
}
