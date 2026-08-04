package assistant_run

import (
	"context"
	"reflect"
	"sort"
	"testing"

	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
)

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-001
func TestAssistantToolCatalogIsGeneratedClosedAndRequiresExplicitMutationConfirmation(t *testing.T) {
	catalog := toolpkg.CanonicalMetadata()
	names := make([]string, 0, len(catalog))
	namespaceCounts := map[string]int{}
	for _, metadata := range catalog {
		names = append(names, metadata.ToolName)
		namespaceCounts[metadata.Namespace]++
		if metadata.InputSchema["additionalProperties"] != false ||
			metadata.OutputSchema["additionalProperties"] != false {
			t.Fatalf("tool %q schemas must be closed", metadata.ToolName)
		}
		if !metadata.ReadOnly &&
			(metadata.Placement != "device_action" || !metadata.RequiresConfirmation) {
			t.Fatalf(
				"mutating tool %q must be a confirmation-gated device action",
				metadata.ToolName,
			)
		}
		if metadata.ReadOnly && metadata.RequiresConfirmation {
			t.Fatalf("read-only tool %q must not require confirmation", metadata.ToolName)
		}
		if !reflect.DeepEqual(
			metadata.EnvironmentScopes,
			[]string{"alpha", "beta", "gamma", "prod"},
		) {
			t.Fatalf("tool %q scopes=%v", metadata.ToolName, metadata.EnvironmentScopes)
		}
	}
	sort.Strings(names)
	if !reflect.DeepEqual(
		names,
		[]string{
			"app_search",
			"calendar_create_reminder",
			"finance_quote",
			"weather_lookup",
			"web_find",
			"web_open",
			"web_search",
		},
	) {
		t.Fatalf("canonical tools=%v", names)
	}
	for namespace, count := range namespaceCounts {
		if count >= 10 {
			t.Fatalf("namespace %q exposes %d tools", namespace, count)
		}
	}

	open := toolpkg.WebOpenMetadata()
	if !reflect.DeepEqual(open.RequiredInputKeys(), []string{"runId", "target"}) {
		t.Fatalf("web_open required inputs=%v", open.RequiredInputKeys())
	}
	open.InputSchema["additionalProperties"] = true
	if toolpkg.WebOpenMetadata().InputSchema["additionalProperties"] != false {
		t.Fatal("canonical metadata must return an immutable fresh projection")
	}
	if toolpkg.WeatherLookupMetadata().Research.ResolvedOperation() !=
		toolpkg.ResearchOperationDiscover ||
		toolpkg.FinanceQuoteMetadata().Research.ResolvedOperation() !=
			toolpkg.ResearchOperationDiscover {
		t.Fatal("typed external fact tools must participate in evidence discovery")
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-002
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-003
func TestCanonicalRegistryRegistersDeviceActionsWithoutCloudHandlers(t *testing.T) {
	registry := toolpkg.BaseRegistry()
	handlers := map[string]toolpkg.Handler{}
	for _, metadata := range toolpkg.CanonicalMetadata() {
		if metadata.Placement == toolpkg.PlacementDeviceAction {
			continue
		}
		handlers[metadata.ToolName] = func(
			context.Context,
			toolpkg.Request,
		) (toolpkg.Result, error) {
			return toolpkg.Result{Output: map[string]any{}}, nil
		}
	}
	if err := toolpkg.RegisterCanonical(&registry, handlers); err != nil {
		t.Fatalf("register canonical production tools: %v", err)
	}
	for _, toolName := range toolpkg.CanonicalToolNames() {
		if _, ok := registry.Metadata(toolName); !ok {
			t.Fatalf("canonical tool %q is not registered", toolName)
		}
	}
	if _, err := registry.Execute(t.Context(), toolpkg.Request{
		ToolName: "calendar_create_reminder",
		Input: map[string]any{
			"title":           "产品评审",
			"startsAt":        "2026-08-01T09:00:00+08:00",
			"durationMinutes": 60,
			"reminderMinutes": 10,
			"notes":           "确认 M0 准出",
		},
	}); err == nil {
		t.Fatal("device action must remain proposal-only without a cloud handler")
	}
}
