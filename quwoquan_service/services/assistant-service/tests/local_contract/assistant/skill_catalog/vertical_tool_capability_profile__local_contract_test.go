// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-004
package local_contract

import (
	"reflect"
	"testing"

	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	resourcebuilder "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
)

func TestOfficialVerticalSkillsComposeTypedToolsOnlyThroughCapabilityProfiles(
	t *testing.T,
) {
	bundle, err := resourcebuilder.NewSourceBuilder().Compile(t.Context())
	if err != nil {
		t.Fatalf("compile official Skill source: %v", err)
	}
	manifests := map[string][]string{}
	for _, manifest := range bundle.ResolvedManifests {
		manifests[manifest.SkillID] = append(
			[]string(nil),
			manifest.ToolPolicy.AllowedTools...,
		)
	}
	want := map[string][]string{
		"weather": {
			"weather_lookup", "web_search", "web_open", "web_find",
		},
		"finance_consumer": {
			"finance_quote", "web_search", "web_open", "web_find",
		},
		"stock_sentinel": {
			"finance_quote", "web_search", "web_open", "web_find",
		},
		"travel_companion": {
			"app_search", "weather_lookup", "web_search", "web_open",
			"web_find", "calendar_create_reminder",
		},
	}
	for skillID, expected := range want {
		if !reflect.DeepEqual(manifests[skillID], expected) {
			t.Fatalf("skill %q tools=%v want=%v", skillID, manifests[skillID], expected)
		}
	}
	for _, metadata := range []toolpkg.Metadata{
		toolpkg.WeatherLookupMetadata(),
		toolpkg.FinanceQuoteMetadata(),
	} {
		if metadata.Research.ResolvedOperation() != toolpkg.ResearchOperationDiscover ||
			!metadata.ReadOnly || metadata.RequiresConfirmation {
			t.Fatalf("typed fact metadata=%+v", metadata)
		}
	}
}
