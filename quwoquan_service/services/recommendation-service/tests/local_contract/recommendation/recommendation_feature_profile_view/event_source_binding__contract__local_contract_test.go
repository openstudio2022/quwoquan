// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/spec.md#sit-001
package local_contract

import (
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestRecommendationFeatureProjectionDeclaresActualStreamInputs(t *testing.T) {
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	raw, err := os.ReadFile(filepath.Join(root, "contracts/recommendation/recommendation_feature_profile_view/object.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Lifecycle struct {
			SourceEvents   []string `yaml:"source_events"`
			EventConsumers []struct {
				Name   string `yaml:"name"`
				Facet  string `yaml:"facet"`
				Method string `yaml:"method"`
			} `yaml:"event_consumers"`
		} `yaml:"lifecycle"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	want := []string{
		"content.content_behavior_fact.ContentBehaviorRecorded", "tag.tag_feedback_fact.TagFeedbackRecorded",
		"user.persona_relationship.PersonaFollowStateChanged", "user.persona_relationship.PersonaBlocked",
		"user.persona_relationship.PersonaUnblocked",
		"circle.circle_membership.CircleMembershipRequested", "circle.circle_membership.CircleMembershipJoined",
		"circle.circle_membership.CircleMembershipApproved", "circle.circle_membership.CircleMembershipLeft",
		"circle.circle_membership.CircleMembershipRoleChanged", "circle.circle_membership.CircleMembershipRejected",
		"content.post.PostPublished", "content.post.PostUpdated", "content.post.PostSettingsUpdated",
		"content.post.PostPromotedToWork", "content.post.PostDeleted",
		"content.post.PostPrivacyRedacted", "content.post.PostPurged",
	}
	wantConsumers := [][3]string{
		{"ProjectRecommendationFeatureBehavior", "ContentBehaviorConsumer", "processOnce"},
		{"ProjectRecommendationTagFeedback", "TagFeedbackConsumer", "processOnce"},
		{"ProjectRecommendationPersonaRelationship", "PersonaRelationshipConsumer", "processOnce"},
		{"ProjectRecommendationCircleMembership", "CircleMembershipConsumer", "processOnce"},
		{"ProjectRecommendationPostLifecycle", "PostLifecycleConsumer", "processOnce"},
	}
	gotConsumers := make([][3]string, 0, len(document.Lifecycle.EventConsumers))
	for _, consumer := range document.Lifecycle.EventConsumers {
		gotConsumers = append(gotConsumers, [3]string{consumer.Name, consumer.Facet, consumer.Method})
	}
	if !reflect.DeepEqual(document.Lifecycle.SourceEvents, want) ||
		!reflect.DeepEqual(gotConsumers, wantConsumers) {
		t.Fatalf("feature profile event binding drifted: %+v", document.Lifecycle)
	}
	operationsRaw, err := os.ReadFile(filepath.Join(root, "contracts/recommendation/recommendation_feature_profile_view/operations.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var operations struct {
		RuntimeEntrypoints []map[string]any `yaml:"runtime_entrypoints"`
	}
	if err := yaml.Unmarshal(operationsRaw, &operations); err != nil {
		t.Fatal(err)
	}
	if len(operations.RuntimeEntrypoints) != 0 {
		t.Fatalf("HTTP-owned feature profile duplicates lifecycle in runtime_entrypoints: %+v", operations.RuntimeEntrypoints)
	}
}
