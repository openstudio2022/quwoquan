// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/native-tool-calling-model-routing/spec.md#gwt-002
package local_contract

import (
	"testing"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_conversation"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/ports"
)

func TestModelTierRoutingIsDeterministicPerStageAndProblemClass(t *testing.T) {
	cases := []struct {
		name     string
		input    orchestration.ModelRoutingInput
		expected ports.ModelTier
	}{
		{
			name: "skill selection always uses the fast tier",
			input: orchestration.ModelRoutingInput{
				Stage:           ports.ModelStageSkillSelection,
				ProblemClass:    assistantgenerated.ProblemClassComplexReasoning,
				SearchIntensity: assistantgenerated.SearchIntensityHigh,
			},
			expected: ports.ModelTierFast,
		},
		{
			name: "complex reasoning escalates the reasoning stage",
			input: orchestration.ModelRoutingInput{
				Stage:           ports.ModelStageReasoning,
				ProblemClass:    assistantgenerated.ProblemClassComplexReasoning,
				SearchIntensity: assistantgenerated.SearchIntensityLow,
			},
			expected: ports.ModelTierReasoning,
		},
		{
			name: "task execution escalates the final stage",
			input: orchestration.ModelRoutingInput{
				Stage:           ports.ModelStageFinal,
				ProblemClass:    assistantgenerated.ProblemClassTaskExecution,
				SearchIntensity: assistantgenerated.SearchIntensityLow,
			},
			expected: ports.ModelTierReasoning,
		},
		{
			name: "high search intensity escalates regardless of problem class",
			input: orchestration.ModelRoutingInput{
				Stage:           ports.ModelStageFinal,
				ProblemClass:    assistantgenerated.ProblemClassGeneral,
				SearchIntensity: assistantgenerated.SearchIntensityHigh,
			},
			expected: ports.ModelTierReasoning,
		},
		{
			name: "simple low intensity question stays on the fast tier",
			input: orchestration.ModelRoutingInput{
				Stage:           ports.ModelStageReasoning,
				ProblemClass:    assistantgenerated.ProblemClassSimpleQa,
				SearchIntensity: assistantgenerated.SearchIntensityLow,
			},
			expected: ports.ModelTierFast,
		},
		{
			name: "realtime evidence lookup stays balanced",
			input: orchestration.ModelRoutingInput{
				Stage:           ports.ModelStageEvidenceProcessing,
				ProblemClass:    assistantgenerated.ProblemClassRealtimeInfo,
				SearchIntensity: assistantgenerated.SearchIntensityMedium,
			},
			expected: ports.ModelTierBalanced,
		},
		{
			name: "general medium input stays on the balanced tier",
			input: orchestration.ModelRoutingInput{
				Stage:           ports.ModelStageFinal,
				ProblemClass:    assistantgenerated.ProblemClassGeneral,
				SearchIntensity: assistantgenerated.SearchIntensityMedium,
			},
			expected: ports.ModelTierBalanced,
		},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			first := orchestration.ResolveModelTier(testCase.input)
			second := orchestration.ResolveModelTier(testCase.input)
			if first != testCase.expected || second != testCase.expected {
				t.Fatalf(
					"tier=%q repeat=%q want %q for input=%+v",
					first,
					second,
					testCase.expected,
					testCase.input,
				)
			}
		})
	}
}

func TestModelTierDegradeOrderOnlyMovesDownward(t *testing.T) {
	cases := map[ports.ModelTier][]ports.ModelTier{
		ports.ModelTierReasoning: {
			ports.ModelTierReasoning,
			ports.ModelTierBalanced,
			ports.ModelTierFast,
		},
		ports.ModelTierBalanced: {
			ports.ModelTierBalanced,
			ports.ModelTierFast,
		},
		ports.ModelTierFast: {ports.ModelTierFast},
	}
	for tier, expected := range cases {
		order := orchestration.ModelTierDegradeOrder(tier)
		if len(order) != len(expected) {
			t.Fatalf("tier=%q order=%v want %v", tier, order, expected)
		}
		for index := range expected {
			if order[index] != expected[index] {
				t.Fatalf("tier=%q order=%v want %v", tier, order, expected)
			}
		}
	}
}
