// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/spec.md#sit-001
package assistant_run

import (
	"context"
	"testing"

	runorchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

type unmatchedSkillSelectionModel struct{}

func (unmatchedSkillSelectionModel) Complete(
	context.Context,
	runorchestration.ModelRequest,
) (runorchestration.ModelResponse, error) {
	return runorchestration.ModelResponse{
		StructuredDelta: map[string]any{"skillId": "not-in-frozen-catalog"},
	}, nil
}

func TestModelDrivenSkillFallbackStaysInsideFrozenActiveCatalog(t *testing.T) {
	runtime := runorchestration.ModelDrivenSkillRuntime{
		Model: unmatchedSkillSelectionModel{},
		Loader: skillfixture.StaticLoader{Manifests: []skillpkg.Manifest{
			{
				SkillID:         "travel_companion",
				DomainID:        "travel",
				DisplayName:     "贴身旅行管家",
				Activation:      skillpkg.ActivationReactive,
				RoutingHints:    []string{"旅行"},
				RoutingFallback: false,
			},
			{
				SkillID:         "fallback_general_search",
				DomainID:        "assistant",
				DisplayName:     "通用搜索助手",
				Activation:      skillpkg.ActivationReactive,
				RoutingFallback: true,
			},
		}},
	}

	selection, err := runtime.SelectSkill(context.Background(), assistant.AssistantTurn{
		TurnID: "turn-frozen-fallback",
		Input: assistant.AssistantTurnInput{
			Text: "一个不命中任何声明式 routing hint 的问题",
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if selection.SkillID != "fallback_general_search" {
		t.Fatalf("skillId=%q, want frozen catalog fallback", selection.SkillID)
	}
}
