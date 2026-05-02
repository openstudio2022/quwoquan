package reasoning

import "strings"

type Budget struct {
	MaxIterations int `json:"maxIterations"`
	MaxToolCalls  int `json:"maxToolCalls"`
}

func DefaultBudget() Budget {
	return Budget{MaxIterations: 4, MaxToolCalls: 3}
}

type PlanInput struct {
	ReasoningText   string
	StructuredDelta map[string]any
	ToolPolicy      []string
	Budget          Budget
}

type PlanStep struct {
	StepID   string         `json:"stepId"`
	Action   string         `json:"action"`
	ToolName string         `json:"toolName,omitempty"`
	Input    map[string]any `json:"input,omitempty"`
}

type ReactPlanner struct{}

func (ReactPlanner) Plan(input PlanInput) []PlanStep {
	if input.Budget.MaxToolCalls <= 0 {
		return []PlanStep{{StepID: "answer", Action: "answer"}}
	}
	if nextAction, _ := input.StructuredDelta["nextAction"].(string); strings.TrimSpace(nextAction) == "call_tool" {
		toolName, _ := input.StructuredDelta["toolName"].(string)
		if strings.TrimSpace(toolName) != "" {
			step := PlanStep{StepID: "tool:1", Action: "tool", ToolName: strings.TrimSpace(toolName)}
			if toolInput, ok := input.StructuredDelta["toolInput"].(map[string]any); ok {
				step.Input = toolInput
			}
			return []PlanStep{step, {StepID: "answer", Action: "answer"}}
		}
	}
	if len(input.ToolPolicy) == 0 {
		return []PlanStep{{StepID: "answer", Action: "answer"}}
	}
	toolName := "mock_search"
	for _, candidate := range input.ToolPolicy {
		if strings.TrimSpace(candidate) != "" {
			toolName = strings.TrimSpace(candidate)
			break
		}
	}
	return []PlanStep{{
		StepID:   "tool:1",
		Action:   "tool",
		ToolName: toolName,
	}, {
		StepID: "answer",
		Action: "answer",
	}}
}

type ReactReflector struct{}

func (ReactReflector) ShouldReplan(observation Observation, budget Budget) bool {
	return observation.Empty && budget.MaxIterations > 1
}

type Observation struct {
	Empty   bool
	Summary string
}
