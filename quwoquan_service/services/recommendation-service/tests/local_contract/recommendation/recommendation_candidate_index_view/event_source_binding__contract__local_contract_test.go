// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/premium-stream-recommendation/spec.md#gwt-002
package local_contract

import (
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestRecommendationCandidateProjectionDeclaresProductionConsumers(t *testing.T) {
	object, operations := readCandidateBindings(t)
	wantEvents := []string{
		"content.post.PostPublished", "content.post.PostUpdated",
		"content.post.PostSettingsUpdated", "content.post.PostPromotedToWork",
		"content.post.PostDeleted", "content.post.PostPrivacyRedacted", "content.post.PostPurged",
		"ops.premium_pool_entry.PremiumPoolEntryUpserted",
		"ops.premium_pool_entry.PremiumPoolEntryRolledBack",
		"ops.premium_pool_entry.PremiumPoolEntryTakedownEjected",
		"user.persona_relationship.PersonaFollowStateChanged",
		"user.persona_relationship.PersonaBlocked", "user.persona_relationship.PersonaUnblocked",
		"user.user_account.UserSuspended", "user.user_account.UserRestored",
		"circle.gathering.GatheringPublished", "circle.gathering.GatheringRevisionAppended",
		"circle.gathering.GatheringParticipationChanged",
		"circle.gathering.GatheringAdmissionControlChanged",
		"circle.gathering.GatheringCancelled", "circle.gathering.GatheringCompleted",
	}
	wantConsumers := []consumerBinding{
		{Name: "ProjectRecommendationCandidatePostLifecycle", Facet: "PostLifecycleConsumer", Method: "processOnce"},
		{Name: "ProjectRecommendationPremiumPool", Facet: "PremiumPoolConsumer", Method: "processOnce"},
		{Name: "ProjectRecommendationPersonaRelationship", Facet: "PersonaRelationshipConsumer", Method: "processOnce"},
		{Name: "ProjectRecommendationAccountRestriction", Facet: "UserAccountRestrictionConsumer", Method: "processOnce"},
		{Name: "ProjectRecommendationCandidateGatheringLifecycle", Facet: "GatheringLifecycleConsumer", Method: "processOnce"},
	}
	if !reflect.DeepEqual(object.SourceEvents, wantEvents) ||
		!reflect.DeepEqual(object.EventConsumers, wantConsumers) || len(operations) != 0 {
		t.Fatalf("candidate event binding drifted: object=%+v operations=%+v", object, operations)
	}
}

type consumerBinding struct {
	Name   string `yaml:"name"`
	Facet  string `yaml:"facet"`
	Method string `yaml:"method"`
}

func readCandidateBindings(t *testing.T) (struct {
	SourceEvents   []string          `yaml:"source_events"`
	EventConsumers []consumerBinding `yaml:"event_consumers"`
}, []consumerBinding) {
	t.Helper()
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	objectRaw, err := os.ReadFile(filepath.Join(root, "contracts/recommendation/recommendation_candidate_index_view/object.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var objectDocument struct {
		Lifecycle struct {
			SourceEvents   []string          `yaml:"source_events"`
			EventConsumers []consumerBinding `yaml:"event_consumers"`
		} `yaml:"lifecycle"`
	}
	if err := yaml.Unmarshal(objectRaw, &objectDocument); err != nil {
		t.Fatal(err)
	}
	operationsRaw, err := os.ReadFile(filepath.Join(root, "contracts/recommendation/recommendation_candidate_index_view/operations.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var operationsDocument struct {
		RuntimeEntrypoints []struct {
			Name        string `yaml:"name"`
			Application struct {
				Facet  string `yaml:"facet"`
				Method string `yaml:"method"`
			} `yaml:"application"`
		} `yaml:"runtime_entrypoints"`
	}
	if err := yaml.Unmarshal(operationsRaw, &operationsDocument); err != nil {
		t.Fatal(err)
	}
	bindings := make([]consumerBinding, 0, len(operationsDocument.RuntimeEntrypoints))
	for _, entrypoint := range operationsDocument.RuntimeEntrypoints {
		bindings = append(bindings, consumerBinding{
			Name: entrypoint.Name, Facet: entrypoint.Application.Facet, Method: entrypoint.Application.Method,
		})
	}
	return objectDocument.Lifecycle, bindings
}
