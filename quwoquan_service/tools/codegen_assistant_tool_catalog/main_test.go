package main

import (
	"strings"
	"testing"
)

func TestMutatingToolRequiresCapabilityIntersectionPolicy(t *testing.T) {
	valid := map[string]any{
		"capability": map[string]any{
			"capabilityKey":        "calendar.event.create",
			"connectorRequirement": "required",
			"consentScopes":        []any{"calendar.event.create"},
			"allowedSurfaceKinds":  []any{"personal"},
			"recheckAtExecution":   true,
		},
	}
	if err := validateMutatingCapabilityPolicy("calendar_create_reminder", valid); err != nil {
		t.Fatalf("valid capability policy rejected: %v", err)
	}

	for name, mutate := range map[string]func(map[string]any){
		"missing capability": func(tool map[string]any) { delete(tool, "capability") },
		"no consent": func(tool map[string]any) {
			tool["capability"].(map[string]any)["consentScopes"] = []any{}
		},
		"no execution recheck": func(tool map[string]any) {
			tool["capability"].(map[string]any)["recheckAtExecution"] = false
		},
	} {
		t.Run(name, func(t *testing.T) {
			tool := map[string]any{
				"capability": map[string]any{
					"capabilityKey":        "calendar.event.create",
					"connectorRequirement": "required",
					"consentScopes":        []any{"calendar.event.create"},
					"allowedSurfaceKinds":  []any{"personal"},
					"recheckAtExecution":   true,
				},
			}
			mutate(tool)
			err := validateMutatingCapabilityPolicy("calendar_create_reminder", tool)
			if err == nil || !strings.Contains(err.Error(), "capability") &&
				!strings.Contains(err.Error(), "consent") {
				t.Fatalf("invalid capability policy was not rejected: %v", err)
			}
		})
	}
}
