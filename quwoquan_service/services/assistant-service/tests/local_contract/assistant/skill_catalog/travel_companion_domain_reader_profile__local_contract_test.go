// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/domain-reader-connector-grant/spec.md#gwt-001
package local_contract

import (
	"reflect"
	"testing"

	resourcebuilder "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

func TestTravelCompanionUsesGatheringToolsAndDropsLegacyTripReader(
	t *testing.T,
) {
	bundle, err := resourcebuilder.NewSourceBuilder().Compile(t.Context())
	if err != nil {
		t.Fatalf("compile official Skill source: %v", err)
	}
	var travel skillpkg.Manifest
	for _, manifest := range bundle.ResolvedManifests {
		if manifest.SkillID == "travel_companion" {
			travel = manifest
			break
		}
	}
	if travel.SkillID == "" {
		t.Fatal("travel_companion is absent from official Skill source")
	}

	expected := map[string]string{
		"circle.current_context":  "circle_context",
		"content.current_context": "content_context",
		"entity.current_context":  "entity_context",
	}
	allowedResolvers := map[string]bool{
		"turn.slot":                    true,
		"turn.preferences":             true,
		"run.feedback_context":         true,
		"conversation.current_context": true,
		"circle.current_context":       true,
		"content.current_context":      true,
		"entity.current_context":       true,
		"trigger.envelope":             true,
		"subscription.plan":            true,
	}
	for _, requirement := range travel.ContextProfile.Requirements {
		if !allowedResolvers[requirement.ResolverRef] {
			t.Fatalf(
				"travel_companion retained an unsupported context resolver %q",
				requirement.ResolverRef,
			)
		}
		slotID, found := expected[requirement.ResolverRef]
		if !found {
			continue
		}
		if requirement.SlotID != slotID ||
			requirement.Authority != "domain_canonical" ||
			requirement.Sensitivity != "public" ||
			!reflect.DeepEqual(requirement.AcceptedSourceKinds, []string{"domain"}) ||
			len(requirement.ConsentScopes) != 0 ||
			requirement.TokenBudget <= 0 || requirement.FreshnessSeconds <= 0 ||
			requirement.FallbackPolicy != "omit" {
			t.Fatalf(
				"resolver %s is not a bounded public domain requirement: %+v",
				requirement.ResolverRef,
				requirement,
			)
		}
		delete(expected, requirement.ResolverRef)
	}
	if len(expected) != 0 {
		t.Fatalf("travel_companion misses canonical domain resolvers: %v", expected)
	}
	requiredGatheringTools := map[string]bool{
		"gathering.search_public":        false,
		"gathering.read_public":          false,
		"gathering.read_private":         false,
		"gathering.propose_create_draft": false,
		"gathering.propose_update":       false,
		"gathering.watch_availability":   false,
		"gathering.propose_plan":         false,
	}
	for _, toolName := range travel.ToolPolicy.AllowedTools {
		if _, required := requiredGatheringTools[toolName]; required {
			requiredGatheringTools[toolName] = true
		}
	}
	for toolName, present := range requiredGatheringTools {
		if !present {
			t.Fatalf("travel_companion misses canonical Gathering tool %q", toolName)
		}
	}
}
