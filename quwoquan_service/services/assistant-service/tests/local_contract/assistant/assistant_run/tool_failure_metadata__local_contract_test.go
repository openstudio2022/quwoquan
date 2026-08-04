// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-004
package assistant_run_test

import (
	"context"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

func TestToolFailureCodeComesFromCanonicalMetadataNotCapabilityName(t *testing.T) {
	metadata := toolpkg.DefaultMetadata("vertical_fact_reader")
	metadata.Failure.ProviderFailureCode = "ASSISTANT.MIDDLEWARE.vertical_fact_unavailable"
	registry := toolpkg.NewRegistry()
	registry.Register(metadata, func(
		context.Context,
		toolpkg.Request,
	) (toolpkg.Result, error) {
		return toolpkg.Result{}, ports.ProviderFailure{
			Capability: "new_vertical_without_agentloop_branch",
			Reason:     ports.ProviderFailureUnavailable,
		}
	})

	execution, err := (orchestration.DefaultToolCoordinator{Registry: registry}).Execute(
		t.Context(),
		orchestration.ToolRequest{
			Turn: assistant.AssistantTurn{
				TurnID:          "turn-metadata-failure",
				ClientRequestID: "request-metadata-failure",
				Input: assistant.AssistantTurnInput{
					Text: "read vertical fact",
				},
			},
			Skill:    orchestration.SkillSelection{SkillID: "new_vertical"},
			ToolName: "vertical_fact_reader",
		},
	)
	if err != nil {
		t.Fatalf("execute metadata-driven failure: %v", err)
	}
	if execution.Failure == nil {
		t.Fatal("provider failure was not projected")
	}
	if execution.Failure.Code != "ASSISTANT.MIDDLEWARE.vertical_fact_unavailable" {
		t.Fatalf("failure=%+v", execution.Failure)
	}
}
