package assistant_run

import (
	"context"
	"strings"
	"testing"

	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
)

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-002
func TestCanonicalRegistryRequiresHandlerOrExplicitUnavailableBinding(t *testing.T) {
	const (
		poiTool   = "location_poi_search"
		routeTool = "location_route_read"
	)
	handlers := canonicalCloudHandlersExcept(poiTool, routeTool)
	unavailable := toolpkg.UnavailableCanonicalBindings(toolpkg.RuntimeAvailability{})
	for _, toolName := range []string{poiTool, routeTool} {
		binding, found := unavailable[toolName]
		if !found || binding.BindingKind != "public_provider" ||
			binding.Reason != "integration_location_binding_not_ready" {
			t.Fatalf("location availability %q=%#v", toolName, binding)
		}
	}
	registry := toolpkg.BaseRegistry()
	if err := toolpkg.RegisterCanonical(&registry, handlers, unavailable); err != nil {
		t.Fatalf("register canonical runtime availability: %v", err)
	}
	for _, toolName := range []string{poiTool, routeTool} {
		if _, found := registry.Metadata(toolName); found {
			t.Fatalf("unavailable canonical tool %q entered runtime registry", toolName)
		}
	}
	if _, found := registry.Metadata("app_search"); !found {
		t.Fatal("real handler-backed canonical tool was not registered")
	}
	if _, found := registry.Metadata("calendar_create_reminder"); !found {
		t.Fatal("proposal-only device action metadata was not registered")
	}
	if _, err := registry.Execute(t.Context(), toolpkg.Request{
		ToolName: poiTool,
		Input:    map[string]any{"query": "西湖"},
	}); err == nil || !strings.Contains(err.Error(), "not registered") {
		t.Fatalf("unavailable tool execution must fail as unregistered: %v", err)
	}
}

func TestCanonicalRuntimeAvailabilityRequiresReadyBindingBeforeLocationRegistration(t *testing.T) {
	if unavailable := toolpkg.UnavailableCanonicalBindings(toolpkg.RuntimeAvailability{
		LocationPublicProviderReady: true,
	}); len(unavailable) != 0 {
		t.Fatalf("ready location provider retained unavailable bindings: %#v", unavailable)
	}

	registry := toolpkg.BaseRegistry()
	err := toolpkg.RegisterCanonical(
		&registry,
		canonicalCloudHandlersExcept("location_poi_search", "location_route_read"),
		toolpkg.UnavailableCanonicalBindings(toolpkg.RuntimeAvailability{
			LocationPublicProviderReady: true,
		}),
	)
	if err == nil || !strings.Contains(err.Error(), "location_poi_search") {
		t.Fatalf("ready-without-handler must fail startup, got %v", err)
	}
	if !registry.IsZero() {
		t.Fatal("failed ready composition partially mutated registry")
	}
}

func TestCanonicalRegistryRejectsUnaccountedAndConflictingBindingsBeforeMutation(t *testing.T) {
	const poiTool = "location_poi_search"
	tests := map[string]struct {
		handlers    map[string]toolpkg.Handler
		unavailable map[string]toolpkg.UnavailableBinding
		want        string
	}{
		"missing handler and availability": {
			handlers: canonicalCloudHandlersExcept(poiTool),
			want:     poiTool,
		},
		"handler and availability conflict": {
			handlers: canonicalCloudHandlersExcept(),
			unavailable: map[string]toolpkg.UnavailableBinding{
				poiTool: {BindingKind: "public_provider", Reason: "not_ready"},
			},
			want: "both a handler and unavailable binding",
		},
		"incomplete unavailable evidence": {
			handlers: canonicalCloudHandlersExcept(poiTool),
			unavailable: map[string]toolpkg.UnavailableBinding{
				poiTool: {BindingKind: "public_provider"},
			},
			want: "unavailable binding is incomplete",
		},
		"unknown unavailable tool": {
			handlers: canonicalCloudHandlersExcept(),
			unavailable: map[string]toolpkg.UnavailableBinding{
				"unknown_location_tool": {BindingKind: "public_provider", Reason: "not_ready"},
			},
			want: "absent from the canonical catalog",
		},
	}
	for name, test := range tests {
		t.Run(name, func(t *testing.T) {
			registry := toolpkg.BaseRegistry()
			err := toolpkg.RegisterCanonical(
				&registry,
				test.handlers,
				test.unavailable,
			)
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("error=%v, want substring %q", err, test.want)
			}
			if !registry.IsZero() {
				t.Fatal("failed canonical reconciliation partially mutated registry")
			}
		})
	}
}

func canonicalCloudHandlersExcept(excluded ...string) map[string]toolpkg.Handler {
	skip := make(map[string]bool, len(excluded))
	for _, toolName := range excluded {
		skip[toolName] = true
	}
	handlers := map[string]toolpkg.Handler{}
	for _, metadata := range toolpkg.CanonicalMetadata() {
		if metadata.Placement == toolpkg.PlacementDeviceAction || skip[metadata.ToolName] {
			continue
		}
		handlers[metadata.ToolName] = func(
			context.Context,
			toolpkg.Request,
		) (toolpkg.Result, error) {
			return toolpkg.Result{Output: map[string]any{}}, nil
		}
	}
	return handlers
}
