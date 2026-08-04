// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
package local_contract

import (
	"reflect"
	"testing"

	catalogapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

func TestContextConsentScopePolicySeparatesOptionalLabelsFromRequiredGate(t *testing.T) {
	t.Parallel()
	profile := skillpkg.ContextProfile{Requirements: []skillpkg.ContextRequirement{
		{
			SlotID:        "optional_memory",
			Required:      false,
			ConsentScopes: []string{"assistant.memory.preferences.read"},
		},
		{
			SlotID:        "required_trip",
			Required:      true,
			ConsentScopes: []string{"travel.trip.read", "assistant.memory.preferences.read"},
		},
		{
			SlotID:        "optional_feedback",
			Required:      false,
			ConsentScopes: []string{"assistant.learning.feedback_context.read"},
		},
	}}

	all := catalogapplication.AllContextConsentScopes(profile)
	if want := []string{
		"assistant.learning.feedback_context.read",
		"assistant.memory.preferences.read",
		"travel.trip.read",
	}; !reflect.DeepEqual(all, want) {
		t.Fatalf("all consent scopes=%v, want %v", all, want)
	}
	required := catalogapplication.RequiredContextConsentScopes(profile)
	if want := []string{
		"assistant.memory.preferences.read",
		"travel.trip.read",
	}; !reflect.DeepEqual(required, want) {
		t.Fatalf("required consent scopes=%v, want %v", required, want)
	}
}
