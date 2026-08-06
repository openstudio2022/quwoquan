// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
package moderation_test

import (
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestContentModerationEventHandlersMatchComposedRelays(t *testing.T) {
	root := contentServiceRoot(t)
	assertContentLifecycleConsumers(t, root, "trust_safety", "post_moderation_case",
		[]string{"content.post.PostSubmittedForReview", "content.report.ReportCreated"},
		[]eventConsumerContract{
			{Name: "OpenCaseFromPostSubmission", Kind: "event_handler", Facet: "PostSubmissionModerationHandler", Method: "openPostModerationCase", Idempotency: "event_id"},
			{Name: "OpenCaseFromReport", Kind: "event_handler", Facet: "ReportModerationHandler", Method: "openPostModerationCase", Idempotency: "event_id"},
		})
	assertContentLifecycleConsumers(t, root, "content", "post",
		[]string{
			"content.comment.CommentCreated",
			"content.comment.CommentDeleted",
			"content.comment.CommentModerated",
			"content.comment.CommentsTombstoned",
			"content.post_moderation_case.PostModerationCaseDecided",
		},
		[]eventConsumerContract{
			{Name: "ProjectCommentCount", Kind: "event_handler", Facet: "CommentCountProjectionHandler", Method: "apply", Idempotency: "event_id"},
			{Name: "ApplyPostModerationDecision", Kind: "event_handler", Facet: "PostModerationDecisionHandler", Method: "applyPostModerationDecision", Idempotency: "event_id"},
		})
	assertContentLifecycleConsumers(t, root, "content", "comment",
		[]string{
			"content.comment.CommentCreated",
			"content.comment.CommentDeleted",
			"content.comment.CommentModerated",
			"content.content_reaction.ContentReactionSet",
			"content.content_reaction.ContentReactionCleared",
			"content.report.ReportResolved",
		},
		[]eventConsumerContract{
			{Name: "RecomputeCommentHotScore", Kind: "event_handler", Facet: "CommentHotScoreProjectionHandler", Method: "apply", Idempotency: "event_id"},
			{Name: "ApplyResolvedReportModeration", Kind: "event_handler", Facet: "CommentReportResolutionHandler", Method: "hideComment", Idempotency: "event_id"},
		})
}

type eventConsumerContract struct {
	Name        string `yaml:"name"`
	Kind        string `yaml:"kind"`
	Facet       string `yaml:"facet"`
	Method      string `yaml:"method"`
	Idempotency string `yaml:"idempotency"`
}

func contentServiceRoot(t *testing.T) string {
	t.Helper()
	_, path, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(path), "../../../../../"))
}

func assertContentLifecycleConsumers(t *testing.T, root, contextName, object string, wantSources []string, wantConsumers []eventConsumerContract) {
	t.Helper()
	data, err := os.ReadFile(filepath.Join(root, "contracts", contextName, object, "object.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Lifecycle struct {
			SourceEvents   []string                `yaml:"source_events"`
			EventConsumers []eventConsumerContract `yaml:"event_consumers"`
		} `yaml:"lifecycle"`
	}
	if err := yaml.Unmarshal(data, &document); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(document.Lifecycle.SourceEvents, wantSources) {
		t.Fatalf("%s.%s lifecycle sources = %#v, want %#v", contextName, object, document.Lifecycle.SourceEvents, wantSources)
	}
	if !reflect.DeepEqual(document.Lifecycle.EventConsumers, wantConsumers) {
		t.Fatalf("%s.%s lifecycle consumers = %#v, want %#v", contextName, object, document.Lifecycle.EventConsumers, wantConsumers)
	}
}
