// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/planner-aggregation-orchestration/spec.md#gwt-003
package local_contract

import (
	"context"
	"errors"
	"strings"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	react "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/reasoning"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

type decisionSafetyModel struct {
	decisions         []map[string]any
	reasoningCalls    int
	lastPreviousSteps []map[string]any
	toolCatalogs      [][]string
}

func (m *decisionSafetyModel) Complete(
	_ context.Context,
	request orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	switch request.Stage {
	case "reasoning":
		m.reasoningCalls++
		catalog := make([]string, 0, len(request.ToolCatalog))
		for _, definition := range request.ToolCatalog {
			catalog = append(catalog, definition.Name)
		}
		m.toolCatalogs = append(m.toolCatalogs, catalog)
		if previous, ok := request.Observation["previousSteps"].([]map[string]any); ok {
			m.lastPreviousSteps = previous
		}
		index := m.reasoningCalls - 1
		if index >= len(m.decisions) {
			return orchestration.ModelResponse{
				StructuredDelta: map[string]any{"nextAction": "answer"},
			}, nil
		}
		return orchestration.ModelResponse{
			StructuredDelta: m.decisions[index],
		}, nil
	case "evidence_processing":
		return orchestration.ModelResponse{StructuredDelta: map[string]any{
			"evidenceSufficient": true,
		}}, nil
	case "final":
		return orchestration.ModelResponse{
			Text: "已根据可用证据给出有边界的回答。",
			StructuredDelta: map[string]any{
				"userMarkdown": "已根据可用证据给出有边界的回答。",
			},
		}, nil
	default:
		return orchestration.ModelResponse{}, nil
	}
}

type decisionSafetyTools struct {
	requests          []orchestration.ToolRequest
	firstInsufficient bool
}

func TestReactRuntimeEmptyAllowlistExposesNoRegisteredTools(t *testing.T) {
	model := &decisionSafetyModel{decisions: []map[string]any{{"nextAction": "answer"}}}
	registry := toolpkg.BaseRegistry()
	registry.Register(
		toolpkg.WebSearchMetadata(),
		func(context.Context, toolpkg.Request) (toolpkg.Result, error) {
			return toolpkg.Result{}, nil
		},
	)
	_, err := (orchestration.ReactRuntime{
		Model:  model,
		Tools:  orchestration.DefaultToolCoordinator{Registry: registry},
		Budget: react.Budget{MaxIterations: 1, MaxToolCalls: 1},
	}).Run(t.Context(), decisionSafetyTurn(), orchestration.SkillSelection{
		SkillID:    "knowledge_general",
		ToolPolicy: []string{},
	})
	if err != nil {
		t.Fatalf("Run() error = %v", err)
	}
	if len(model.toolCatalogs) != 1 || len(model.toolCatalogs[0]) != 0 {
		t.Fatalf("empty allowlist leaked runtime tools: %#v", model.toolCatalogs)
	}
}

func TestReactRuntimeZeroToolSkillRechecksSkillAccessBeforeModel(t *testing.T) {
	model := &decisionSafetyModel{}
	revoked := errors.New("skill placement revoked")
	_, err := (orchestration.ReactRuntime{
		Model: model,
		PrePlanAccess: func(
			context.Context,
			assistant.AssistantTurn,
			orchestration.SkillSelection,
		) error {
			return revoked
		},
		Budget: react.Budget{MaxIterations: 1, MaxToolCalls: 1},
	}).Run(t.Context(), decisionSafetyTurn(), orchestration.SkillSelection{
		SkillID:    "knowledge_general",
		ToolPolicy: []string{},
	})
	if !errors.Is(err, revoked) {
		t.Fatalf("error = %v, want revoked Skill access", err)
	}
	if model.reasoningCalls != 0 {
		t.Fatalf("model was called %d time(s) after Skill revocation", model.reasoningCalls)
	}
}

func TestReactRuntimeFailsClosedWhenFrozenToolIsAbsentFromRuntimeRegistry(
	t *testing.T,
) {
	model := &decisionSafetyModel{}
	registry := toolpkg.BaseRegistry()
	registry.Register(
		toolpkg.WebSearchMetadata(),
		func(context.Context, toolpkg.Request) (toolpkg.Result, error) {
			return toolpkg.Result{}, nil
		},
	)
	_, err := (orchestration.ReactRuntime{
		Model:  model,
		Tools:  orchestration.DefaultToolCoordinator{Registry: registry},
		Budget: react.Budget{MaxIterations: 1, MaxToolCalls: 1},
	}).Run(t.Context(), decisionSafetyTurn(), orchestration.SkillSelection{
		SkillID:    "knowledge_general",
		ToolPolicy: []string{"web_search", "web_open"},
	})
	if err == nil || !strings.Contains(err.Error(), "web_open") {
		t.Fatalf("error = %v, want missing runtime tool", err)
	}
	if model.reasoningCalls != 0 {
		t.Fatalf("model was called %d time(s) before runtime availability validation", model.reasoningCalls)
	}
}

func (t *decisionSafetyTools) ModelToolDeclarations(
	allowedToolNames []string,
) []ports.ModelToolDefinition {
	definitions := make([]ports.ModelToolDefinition, 0, len(allowedToolNames))
	for _, name := range allowedToolNames {
		definitions = append(definitions, ports.ModelToolDefinition{
			Name: name,
			Parameters: map[string]any{
				"type":                 "object",
				"additionalProperties": true,
			},
		})
	}
	return definitions
}

func (t *decisionSafetyTools) Execute(
	_ context.Context,
	request orchestration.ToolRequest,
) (orchestration.ToolExecution, error) {
	t.requests = append(t.requests, request)
	result := map[string]any{"summary": "verified evidence"}
	if t.firstInsufficient && len(t.requests) == 1 {
		result["evidenceAssessment"] = map[string]any{
			"evidenceSufficient": false,
			"replanRequired":     true,
			"reason":             "evidence_gap",
		}
	}
	return orchestration.ToolExecution{
		Requested: assistant.ToolUse{
			ToolName: request.ToolName,
			Input:    request.Input,
		},
		Completed: assistant.ToolUse{
			ToolName: request.ToolName,
			Input:    request.Input,
			Result:   result,
			Status:   "completed",
		},
	}, nil
}

func TestReactRuntimeRepairsMissingToolNameWithoutExecutingPolicyFallback(
	t *testing.T,
) {
	model := &decisionSafetyModel{decisions: []map[string]any{
		{"nextAction": "tool_call"},
		{
			"nextAction": "tool_call",
			"toolName":   "web_search",
			"toolInput":  map[string]any{"query": "杭州天气"},
		},
	}}
	tools := &decisionSafetyTools{}
	result, err := (orchestration.ReactRuntime{
		Model:  model,
		Tools:  tools,
		Budget: react.Budget{MaxIterations: 3, MaxToolCalls: 2},
	}).Run(t.Context(), decisionSafetyTurn(), orchestration.SkillSelection{
		SkillID:    "knowledge_general",
		ToolPolicy: []string{"web_search"},
	})
	if err != nil {
		t.Fatalf("Run() error = %v", err)
	}
	if len(tools.requests) != 1 || tools.requests[0].ToolName != "web_search" {
		t.Fatalf("executed tools = %#v", tools.requests)
	}
	assertDecisionRejection(
		t,
		result.Steps[0].DecisionRejection,
		"tool_name_required",
		"",
		"web_search",
	)
	assertRepairObservation(t, model.lastPreviousSteps, "tool_name_required")
}

func TestReactRuntimeRejectsUnavailableToolWithoutRepeatingFirstRuntimeTool(
	t *testing.T,
) {
	model := &decisionSafetyModel{decisions: []map[string]any{
		{
			"nextAction": "tool_call",
			"toolName":   "web_search",
			"toolInput":  map[string]any{"query": "first evidence"},
		},
		{
			"nextAction": "tool_call",
			"toolName":   "not_registered",
		},
		{"nextAction": "answer"},
	}}
	tools := &decisionSafetyTools{firstInsufficient: true}
	result, err := (orchestration.ReactRuntime{
		Model:  model,
		Tools:  tools,
		Budget: react.Budget{MaxIterations: 3, MaxToolCalls: 3},
	}).Run(t.Context(), decisionSafetyTurn(), orchestration.SkillSelection{
		SkillID:    "knowledge_general",
		ToolPolicy: []string{"web_search"},
	})
	if err != nil {
		t.Fatalf("Run() error = %v", err)
	}
	if len(tools.requests) != 1 || tools.requests[0].ToolName != "web_search" {
		t.Fatalf("unavailable decision executed a fallback: %#v", tools.requests)
	}
	assertDecisionRejection(
		t,
		result.Steps[1].DecisionRejection,
		"tool_unavailable",
		"not_registered",
		"web_search",
	)
	assertRepairObservation(t, model.lastPreviousSteps, "tool_unavailable")
}

func TestReactRuntimeHidesGuardDeniedToolAndRejectsModelForgery(
	t *testing.T,
) {
	model := &decisionSafetyModel{decisions: []map[string]any{
		{
			"nextAction": "tool_call",
			"toolName":   "web_open",
			"toolInput":  map[string]any{"target": "source:first"},
		},
		{
			"nextAction": "tool_call",
			"toolName":   "web_search",
		},
		{"nextAction": "answer"},
	}}
	tools := &decisionSafetyTools{firstInsufficient: true}
	result, err := (orchestration.ReactRuntime{
		Model: model,
		Tools: tools,
		Guard: react.ToolExecutionGuard{AllowedTools: map[string]bool{
			"web_open": true,
		}},
		Budget: react.Budget{MaxIterations: 3, MaxToolCalls: 3},
	}).Run(t.Context(), decisionSafetyTurn(), orchestration.SkillSelection{
		SkillID:    "knowledge_general",
		ToolPolicy: []string{"web_open", "web_search"},
	})
	if err != nil {
		t.Fatalf("Run() error = %v", err)
	}
	if len(tools.requests) != 1 || tools.requests[0].ToolName != "web_open" {
		t.Fatalf("guard rejection executed an alternative: %#v", tools.requests)
	}
	assertDecisionRejection(
		t,
		result.Steps[1].DecisionRejection,
		"tool_unavailable",
		"web_search",
		"web_open",
	)
	for index, catalog := range model.toolCatalogs {
		if len(catalog) != 1 || catalog[0] != "web_open" {
			t.Fatalf("reasoning catalog[%d]=%v leaked guard-denied tool", index, catalog)
		}
	}
	assertRepairObservation(t, model.lastPreviousSteps, "tool_unavailable")
}

func TestReactRuntimeReevaluatesDynamicToolAccessAtEveryPlanningBoundary(
	t *testing.T,
) {
	model := &decisionSafetyModel{decisions: []map[string]any{
		{
			"nextAction": "tool_call",
			"toolName":   "web_search",
			"toolInput":  map[string]any{"query": "first evidence"},
		},
		{
			"nextAction": "tool_call",
			"toolName":   "web_search",
			"toolInput":  map[string]any{"query": "must not execute"},
		},
		{"nextAction": "answer"},
	}}
	tools := &decisionSafetyTools{firstInsufficient: true}
	checks := 0
	_, err := (orchestration.ReactRuntime{
		Model: model,
		Tools: tools,
		PreToolUse: func(
			context.Context,
			assistant.AssistantTurn,
			orchestration.SkillSelection,
			string,
			toolpkg.Metadata,
		) error {
			checks++
			// First planning boundary and its immediate execution are allowed.
			// The capability is revoked before the next planning boundary.
			if checks >= 3 {
				return context.Canceled
			}
			return nil
		},
		Budget: react.Budget{MaxIterations: 3, MaxToolCalls: 3},
	}).Run(t.Context(), decisionSafetyTurn(), orchestration.SkillSelection{
		SkillID:    "knowledge_general",
		ToolPolicy: []string{"web_search"},
	})
	if err != nil {
		t.Fatalf("Run() error = %v", err)
	}
	if len(tools.requests) != 1 {
		t.Fatalf("revoked tool executed %d time(s): %#v", len(tools.requests), tools.requests)
	}
	if len(model.toolCatalogs) != 2 ||
		len(model.toolCatalogs[0]) != 1 ||
		len(model.toolCatalogs[1]) != 0 {
		t.Fatalf("dynamic planning catalogs = %#v", model.toolCatalogs)
	}
}

func decisionSafetyTurn() assistant.AssistantTurn {
	return assistant.AssistantTurn{
		TurnID: "turn-decision-safety",
		Input:  assistant.AssistantTurnInput{Text: "核验事实"},
	}
}

func assertDecisionRejection(
	t *testing.T,
	rejection *react.ToolDecisionRejection,
	reasonCode string,
	requestedTool string,
	allowedTool string,
) {
	t.Helper()
	if rejection == nil {
		t.Fatal("rejection is nil")
	}
	allowedMatches := len(rejection.AllowedTools) == 1 &&
		rejection.AllowedTools[0] == allowedTool
	if allowedTool == "" {
		allowedMatches = len(rejection.AllowedTools) == 0
	}
	if rejection.ReasonCode != reasonCode ||
		rejection.RequestedTool != requestedTool || !rejection.Retryable ||
		!allowedMatches {
		t.Fatalf("rejection = %#v", rejection)
	}
}

func assertRepairObservation(
	t *testing.T,
	previousSteps []map[string]any,
	reasonCode string,
) {
	t.Helper()
	if len(previousSteps) == 0 {
		t.Fatal("repair iteration did not receive previous observations")
	}
	last := previousSteps[len(previousSteps)-1]
	if last["kind"] != "decision_rejected" ||
		last["status"] != "rejected" ||
		last["reasonCode"] != reasonCode ||
		last["retryable"] != true {
		t.Fatalf("repair observation = %#v", last)
	}
}
