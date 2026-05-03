package application

import (
	"context"
	"fmt"

	react "quwoquan_service/services/assistant-service/internal/application/reasoning"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type ReactRuntime struct {
	Model     ModelProvider
	Tools     ToolExecutor
	Planner   react.ReactPlanner
	Reflector react.ReactReflector
	Guard     react.ToolExecutionGuard
	Assessor  react.ToolResultAssessor
	Truncator react.ToolResultTruncator
	Budget    react.Budget
}

type ReactResult struct {
	ReasoningText    string
	ModelDelta       string
	StructuredDelta  map[string]any
	Usage            map[string]any
	Tool             ToolExecution
	Steps            []ReactStepResult
	FinalText        string
	StopReason       string
	FinalClientTrace map[string]any
}

type ReactStepResult struct {
	Iteration               int
	ReasoningText           string
	ModelDelta              string
	StructuredDelta         map[string]any
	EvidenceModelDelta      string
	EvidenceStructuredDelta map[string]any
	ModelInteractions       []map[string]any
	Plan                    []react.PlanStep
	Tool                    ToolExecution
	Observation             react.Observation
	Replan                  bool
	ReplanReason            string
}

func (r ReactRuntime) Run(ctx context.Context, turn assistant.AssistantTurn, skill SkillSelection) (ReactResult, error) {
	return r.RunWithStepSink(ctx, turn, skill, nil)
}

func (r ReactRuntime) RunWithStepSink(ctx context.Context, turn assistant.AssistantTurn, skill SkillSelection, stepSink func(ReactStepResult) error) (ReactResult, error) {
	return r.RunWithSinks(ctx, turn, skill, nil, stepSink)
}

func (r ReactRuntime) RunWithSinks(ctx context.Context, turn assistant.AssistantTurn, skill SkillSelection, reasoningSink func(ReactStepResult) error, stepSink func(ReactStepResult) error) (ReactResult, error) {
	model := r.Model
	if model == nil {
		model = DeterministicModelProvider{}
	}
	tools := r.Tools
	if tools == nil {
		tools = DefaultToolCoordinator{}
	}
	budget := r.Budget
	if budget.MaxIterations == 0 {
		budget = react.DefaultBudget()
	}
	planner := r.Planner
	guard := r.Guard
	if guard.AllowedTools == nil && len(skill.ToolPolicy) > 0 {
		guard.AllowedTools = map[string]bool{}
		for _, allowed := range skill.ToolPolicy {
			guard.AllowedTools[allowed] = true
		}
	}
	assessor := r.Assessor
	truncator := r.Truncator
	reflector := r.Reflector
	toolHistory := []string{}
	stepsOut := []ReactStepResult{}
	usage := map[string]any{}
	finalObservation := map[string]any(nil)
	finalReasoningText := ""
	finalModelDelta := ""
	finalStructuredDelta := map[string]any(nil)
	stopReason := "max_iterations"
	for iteration := 1; iteration <= budget.MaxIterations; iteration++ {
		reasoning := fmt.Sprintf("第 %d 轮：根据 skill=%s 规划工具、评估观察，再决定是否重规划。", iteration, skill.SkillID)
		reasoningResp, err := model.Complete(ctx, ModelRequest{
			TurnID:       turn.TurnID,
			TraceID:      turn.TraceID,
			SkillID:      skill.SkillID,
			Stage:        "reasoning",
			Prompt:       reasoning,
			UserQuestion: turn.Input.Text,
			ContextTurns: turn.ContextTurns,
		})
		if err != nil {
			return ReactResult{}, err
		}
		stepInteractions := collectModelInteraction(reasoningResp)
		usage[fmt.Sprintf("reasoning_%d", iteration)] = reasoningResp.Usage
		finalReasoningText = reasoning
		finalModelDelta = reasoningResp.Text
		finalStructuredDelta = reasoningResp.StructuredDelta
		planned := planner.Plan(react.PlanInput{
			ReasoningText:   reasoningResp.Text,
			StructuredDelta: reasoningResp.StructuredDelta,
			ToolPolicy:      skill.ToolPolicy,
			Budget: react.Budget{
				MaxIterations: budget.MaxIterations - iteration + 1,
				MaxToolCalls:  budget.MaxToolCalls - len(toolHistory),
			},
		})
		toolName := ""
		toolInput := map[string]any(nil)
		for _, step := range planned {
			if step.Action == "tool" {
				toolName = step.ToolName
				toolInput = step.Input
				break
			}
		}
		if reasoningSink != nil {
			if err := reasoningSink(ReactStepResult{
				Iteration:         iteration,
				ReasoningText:     reasoning,
				ModelDelta:        reasoningResp.Text,
				StructuredDelta:   reasoningResp.StructuredDelta,
				ModelInteractions: stepInteractions,
				Plan:              planned,
				Tool: ToolExecution{Requested: assistant.ToolUse{
					ToolName: toolName,
					Input:    toolInput,
				}},
			}); err != nil {
				return ReactResult{}, err
			}
		}
		if toolName == "" || len(toolHistory) >= budget.MaxToolCalls {
			stopReason = "model_answered_without_tools"
			break
		}
		if err := guard.Allow(toolName); err != nil {
			if len(skill.ToolPolicy) == 0 || len(toolHistory) == 0 {
				return ReactResult{}, err
			}
			toolName = skill.ToolPolicy[0]
			if err := guard.Allow(toolName); err != nil {
				return ReactResult{}, err
			}
		}
		toolExecution, err := tools.Execute(ctx, ToolRequest{
			Turn:      turn,
			Skill:     skill,
			ToolName:  toolName,
			Input:     toolInput,
			History:   toolHistory,
			Reasoning: reasoningResp.Text,
		})
		if err != nil {
			return ReactResult{}, err
		}
		toolHistory = append(toolHistory, toolName)
		if toolExecution.Failure != nil {
			stepOut := ReactStepResult{
				Iteration:         iteration,
				ReasoningText:     reasoning,
				ModelDelta:        reasoningResp.Text,
				StructuredDelta:   reasoningResp.StructuredDelta,
				ModelInteractions: stepInteractions,
				Plan:              planned,
				Tool:              toolExecution,
				Observation:       react.Observation{Empty: true, Summary: "tool failed"},
				Replan:            false,
				ReplanReason:      "tool_failed",
			}
			if stepSink != nil {
				if err := stepSink(stepOut); err != nil {
					return ReactResult{}, err
				}
			}
			return ReactResult{
				ReasoningText:   reasoning,
				ModelDelta:      reasoningResp.Text,
				StructuredDelta: reasoningResp.StructuredDelta,
				Usage:           usage,
				Tool:            toolExecution,
				Steps:           append(stepsOut, stepOut),
				StopReason:      "tool_failed",
			}, nil
		}
		toolExecution.Completed.Result = truncator.Truncate(toolExecution.Completed.Result)
		observation := assessor.Assess(toolExecution.Completed.Result)
		finalObservation = toolExecution.Completed.Result
		evidenceObservation := map[string]any{
			"tool":         toolName,
			"toolInput":    toolInput,
			"result":       toolExecution.Completed.Result,
			"observation":  map[string]any{"summary": observation.Summary, "empty": observation.Empty},
			"userQuestion": turn.Input.Text,
		}
		evidenceResp, err := model.Complete(ctx, ModelRequest{
			TurnID:       turn.TurnID,
			TraceID:      turn.TraceID,
			SkillID:      skill.SkillID,
			Stage:        "evidence_processing",
			Prompt:       "基于工具返回的结构化结果，生成面向用户的证据处理叙事（processingSummary）与要点（selectedKeyPoints）；references 仅摘录你认为可靠且相关的条目。",
			Observation:  evidenceObservation,
			UserQuestion: turn.Input.Text,
			ContextTurns: turn.ContextTurns,
		})
		if err != nil {
			return ReactResult{}, err
		}
		usage[fmt.Sprintf("evidence_%d", iteration)] = evidenceResp.Usage
		stepInteractions = append(stepInteractions, collectModelInteraction(evidenceResp)...)
		remainingBudget := react.Budget{
			MaxIterations: budget.MaxIterations - iteration,
			MaxToolCalls:  budget.MaxToolCalls - len(toolHistory),
		}
		replan := reflector.ShouldReplan(observation, remainingBudget)
		reason := replanReason(observation, remainingBudget)
		stepOut := ReactStepResult{
			Iteration:               iteration,
			ReasoningText:           reasoning,
			ModelDelta:              reasoningResp.Text,
			StructuredDelta:         reasoningResp.StructuredDelta,
			EvidenceModelDelta:      evidenceResp.Text,
			EvidenceStructuredDelta: evidenceResp.StructuredDelta,
			ModelInteractions:       stepInteractions,
			Plan:                    planned,
			Tool:                    toolExecution,
			Observation:             observation,
			Replan:                  replan,
			ReplanReason:            reason,
		}
		stepsOut = append(stepsOut, stepOut)
		if stepSink != nil {
			if err := stepSink(stepOut); err != nil {
				return ReactResult{}, err
			}
		}
		if !replan {
			stopReason = "observation_sufficient"
			break
		}
		stopReason = "replan_budget_exhausted"
	}
	finalResp, err := model.Complete(ctx, ModelRequest{
		TurnID:       turn.TurnID,
		TraceID:      turn.TraceID,
		SkillID:      skill.SkillID,
		Stage:        "final",
		Prompt:       "结合工具观察生成最终回答",
		Observation:  finalObservation,
		UserQuestion: turn.Input.Text,
		ContextTurns: turn.ContextTurns,
	})
	if err != nil {
		return ReactResult{}, err
	}
	usage["final"] = finalResp.Usage
	toolExecution := ToolExecution{}
	if len(stepsOut) > 0 {
		toolExecution = stepsOut[len(stepsOut)-1].Tool
	}
	return ReactResult{
		ReasoningText:    finalReasoningText,
		ModelDelta:       finalModelDelta,
		StructuredDelta:  finalStructuredDelta,
		Usage:            usage,
		Tool:             toolExecution,
		Steps:            stepsOut,
		FinalText:        finalResp.Text,
		StopReason:       stopReason,
		FinalClientTrace: finalResp.ClientModelInteraction,
	}, nil
}

func collectModelInteraction(resp ModelResponse) []map[string]any {
	if resp.ClientModelInteraction == nil {
		return nil
	}
	return []map[string]any{resp.ClientModelInteraction}
}

func replanReason(observation react.Observation, budget react.Budget) string {
	if !observation.Empty {
		return "observation_sufficient"
	}
	if budget.MaxIterations <= 0 || budget.MaxToolCalls <= 0 {
		return "budget_exhausted"
	}
	return "observation_empty"
}
