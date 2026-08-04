package local_contract

import (
	"context"
	"fmt"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

// canonicalTestToolMetadata keeps test executors on the same immutable metadata
// catalog as production. A test double may fake execution, but it must not invent
// confirmation, sensitivity, or reachability policy.
func canonicalTestToolMetadata(toolName string) (toolpkg.Metadata, bool) {
	return toolpkg.LookupCanonicalMetadata(toolName)
}

// canonicalTestToolRegistry is the test composition root for a fully bound
// process-local tool runtime. It keeps policy metadata canonical while binding
// every cloud tool to an explicit adapter that fails if a test invokes it
// unexpectedly. Device actions remain proposal-only, exactly as in production.
func canonicalTestToolRegistry(
	overrides map[string]toolpkg.Handler,
) toolpkg.Registry {
	registry := toolpkg.NewRegistry()
	for _, metadata := range toolpkg.CanonicalMetadata() {
		if metadata.Placement == toolpkg.PlacementDeviceAction {
			registry.RegisterDeviceAction(metadata)
			continue
		}
		handler := overrides[metadata.ToolName]
		if handler == nil {
			toolName := metadata.ToolName
			handler = func(
				context.Context,
				toolpkg.Request,
			) (toolpkg.Result, error) {
				return toolpkg.Result{}, fmt.Errorf(
					"unexpected canonical test tool %q",
					toolName,
				)
			}
		}
		registry.Register(metadata, handler)
	}
	return registry
}

func canonicalTestToolCoordinator(
	overrides map[string]toolpkg.Handler,
) orchestration.DefaultToolCoordinator {
	return orchestration.DefaultToolCoordinator{
		Registry: canonicalTestToolRegistry(overrides),
	}
}

func canonicalTestModelToolDefinitions(
	allowedToolNames []string,
) []ports.ModelToolDefinition {
	seen := map[string]bool{}
	definitions := make([]ports.ModelToolDefinition, 0, len(allowedToolNames))
	for _, toolName := range allowedToolNames {
		if seen[toolName] {
			continue
		}
		metadata, available := canonicalTestToolMetadata(toolName)
		if !available {
			continue
		}
		seen[toolName] = true
		declaration := toolpkg.ModelDeclarationFor(metadata)
		definitions = append(definitions, ports.ModelToolDefinition{
			Name:        declaration.Name,
			Description: declaration.Description,
			Parameters:  declaration.Parameters,
		})
	}
	return definitions
}

// acceptedEvidenceAssessment 是 catalog outputSchema 要求的最小 accepted 投影，
// 供 Registry stub handler 通过输出校验，而不伪造业务证据。
func acceptedEvidenceAssessment(reason string) map[string]any {
	if reason == "" {
		reason = "test_stub_accepted"
	}
	return map[string]any{
		"status":             "accepted",
		"evidenceSufficient": true,
		"replanRequired":     false,
		"reason":             reason,
		"targetIds":          []any{},
		"documentIds":        []any{},
		"artifactRefs":       []any{},
		"sourceIds":          []any{},
	}
}

func (*policyTools) ToolMetadata(toolName string) (toolpkg.Metadata, bool) {
	return canonicalTestToolMetadata(toolName)
}

func (*deepResearchTools) ToolMetadata(toolName string) (toolpkg.Metadata, bool) {
	return canonicalTestToolMetadata(toolName)
}

func (*decisionSafetyTools) ToolMetadata(toolName string) (toolpkg.Metadata, bool) {
	return canonicalTestToolMetadata(toolName)
}
