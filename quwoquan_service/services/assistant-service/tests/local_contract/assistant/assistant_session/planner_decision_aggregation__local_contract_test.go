// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/planner-aggregation-orchestration/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/planner-aggregation-orchestration/spec.md#gwt-003
package local_contract

import (
	"context"
	"encoding/json"
	"fmt"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/streaming"
	"strings"
	"testing"

	"quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/tests/support/promptassets"
)

// plannerStubModel 按 stage 返回可控决策，用来驱动 planner 的动作分支。
type plannerStubModel struct {
	reasoningDelta map[string]any
	reasoningCalls int
}

func (model *plannerStubModel) Complete(
	_ context.Context,
	req orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	switch strings.TrimSpace(req.Stage) {
	case "reasoning":
		model.reasoningCalls++
		raw, _ := json.Marshal(model.reasoningDelta)
		return orchestration.ModelResponse{
			Text:            string(raw),
			StructuredDelta: model.reasoningDelta,
			FinishReason:    "stop",
		}, nil
	case "evidence_processing":
		delta := map[string]any{
			"retrievalProcessing": map[string]any{
				"processingSummary":  "已核对你关心的出行条件。",
				"selectedKeyPoints":  []string{"天气适合出行"},
				"acceptedReferences": []any{},
			},
			"evidenceSufficient": true,
		}
		raw, _ := json.Marshal(delta)
		return orchestration.ModelResponse{
			Text:            string(raw),
			StructuredDelta: delta,
			FinishReason:    "stop",
		}, nil
	default:
		answer := "你周末去杭州可以按室外行程安排，出发前再确认一次实时天气。"
		return orchestration.ModelResponse{
			Text:            answer,
			StructuredDelta: map[string]any{"userMarkdown": answer},
			FinishReason:    "stop",
		}, nil
	}
}

func plannerLoop(t *testing.T, model orchestration.ModelProvider, toolCalls *int) *orchestration.AgentLoop {
	t.Helper()
	registry := toolpkg.BaseRegistry()
	registry.Register(
		toolpkg.WebSearchMetadata(),
		func(_ context.Context, _ toolpkg.Request) (toolpkg.Result, error) {
			if toolCalls != nil {
				*toolCalls++
			}
			return toolpkg.Result{Output: map[string]any{
				"summary":    "杭州周末多云，适合安排室外行程。",
				"references": []any{},
				"reliable":   true,
			}}, nil
		},
	)
	loop := orchestration.NewAgentLoop(
		nil,
		orchestration.ReactRuntime{
			Model: model,
			Tools: orchestration.DefaultToolCoordinator{Registry: registry},
		},
		nil,
	)
	loop.PromptAssets = promptassets.MustResolver(t)
	return loop
}

func plannerTurn(skillID string) assistant.AssistantTurn {
	selection := testFrozenPolicySelection("assistant-default", skillID, "travel")
	selection.Template.AllowedTools = []string{"web_search"}
	return assistant.AssistantTurn{
		SessionID:             "session-planner",
		TurnID:                "turn-planner",
		TraceID:               "trace-planner",
		Input:                 assistant.AssistantTurnInput{Text: "我周末去杭州玩"},
		FrozenPolicySelection: selection,
	}
}

func completedPayload(t *testing.T, events []streaming.Envelope) map[string]any {
	t.Helper()
	for _, event := range events {
		if event.EventType == string(assistantstreaming.AssistantStreamEventCompleted) {
			return event.Payload
		}
	}
	t.Fatalf("no completed event in %d events", len(events))
	return nil
}

func processEvents(events []streaming.Envelope) []assistant.AssistantRunVisibleProcess {
	processes := []assistant.AssistantRunVisibleProcess{}
	for _, event := range events {
		process, ok := event.Payload["process"].(assistant.AssistantRunVisibleProcess)
		if !ok {
			continue
		}
		processes = append(processes, process)
	}
	return processes
}

// 关键信息缺失时，该轮必须以反问收尾：不调用工具、不给结论，且用契约枚举表达。
func TestPlannerAskUserEndsTurnWithClarification(t *testing.T) {
	toolCalls := 0
	model := &plannerStubModel{reasoningDelta: map[string]any{
		"nextAction": "ask_user",
		"askUser": map[string]any{
			"slotId":      "destination",
			"prompt":      "你想去哪座城市？",
			"required":    true,
			"suggestions": []any{"杭州", "苏州"},
		},
	}}
	loop := plannerLoop(t, model, &toolCalls)
	events, failure, err := loop.RunTurn(t.Context(), plannerTurn("travel_planning"))
	if err != nil || failure != nil {
		t.Fatalf("clarification turn must succeed: failure=%+v err=%v", failure, err)
	}
	if toolCalls != 0 {
		t.Fatalf("toolCalls=%d want 0 before the missing slot is filled", toolCalls)
	}
	payload := completedPayload(t, events)
	if payload["messageKind"] != "ask_user" {
		t.Fatalf("messageKind=%v want ask_user", payload["messageKind"])
	}
	if payload["finalAnswerMode"] != "clarify" {
		t.Fatalf("finalAnswerMode=%v want clarify", payload["finalAnswerMode"])
	}
	ask, ok := payload["askUser"].(map[string]any)
	if !ok || ask["slotId"] != "destination" {
		t.Fatalf("askUser=%#v want the missing slot", payload["askUser"])
	}
	if answer := fmt.Sprint(payload["finalAnswer"]); !strings.Contains(answer, "你想去哪座城市？") {
		t.Fatalf("finalAnswer=%q must carry the question", answer)
	}
	aggregation, ok := payload["aggregationState"].(map[string]any)
	if !ok || aggregation["clarificationNeeded"] != true || aggregation["finalAnswerReady"] != false {
		t.Fatalf("aggregationState=%#v want clarification pending", payload["aggregationState"])
	}
	clarifying := false
	for _, process := range processEvents(events) {
		if process.Stage == "clarifying" && process.ActionCode == "ask_clarification" {
			clarifying = true
		}
		if process.Stage == "searching" {
			t.Fatalf("clarification turn must not emit a retrieval process: %#v", process)
		}
	}
	if !clarifying {
		t.Fatal("clarification turn must emit a clarifying process with ask_clarification")
	}
}

// 证据充分的单技能运行必须裁决成 full，并且 skillRuns 里恰好一条已就绪记录。
func TestAggregationMarksSingleReadySkillRunAsFull(t *testing.T) {
	toolCalls := 0
	model := &plannerStubModel{reasoningDelta: map[string]any{
		"nextAction": "tool_call",
		"toolName":   "web_search",
		"toolInput":  map[string]any{"query": "杭州 周末 天气"},
	}}
	loop := plannerLoop(t, model, &toolCalls)
	events, failure, err := loop.RunTurn(t.Context(), plannerTurn("travel_planning"))
	if err != nil || failure != nil {
		t.Fatalf("answer turn must succeed: failure=%+v err=%v", failure, err)
	}
	payload := completedPayload(t, events)
	if payload["finalAnswerMode"] != "full" {
		t.Fatalf("finalAnswerMode=%v want full", payload["finalAnswerMode"])
	}
	if payload["messageKind"] != "answer" {
		t.Fatalf("messageKind=%v want answer", payload["messageKind"])
	}
	runs, ok := payload["skillRuns"].([]map[string]any)
	if !ok || len(runs) != 1 {
		t.Fatalf("skillRuns=%#v want exactly one run", payload["skillRuns"])
	}
	if runs[0]["answerReady"] != true || runs[0]["skillId"] != "travel_planning" {
		t.Fatalf("skillRun=%#v want a ready travel_planning run", runs[0])
	}
	toolNames, ok := runs[0]["toolNames"].([]string)
	if !ok || len(toolNames) != 1 || toolNames[0] != "web_search" {
		t.Fatalf("toolNames=%#v want the executed tool", runs[0]["toolNames"])
	}
}

// 工具预算来自技能清单：模型持续要求检索时，工具调用次数不得超过清单声明。
func TestToolBudgetComesFromSkillManifest(t *testing.T) {
	catalog, err := orchestration.LoadAssistantDomainSkillCatalog()
	if err != nil {
		t.Fatalf("load assistant domain skill catalog: %v", err)
	}
	budget := 0
	for _, manifest := range catalog {
		if manifest.SkillID == "weather" {
			budget = manifest.ToolPolicy.MaxToolCalls
		}
	}
	if budget <= 0 {
		t.Fatal("weather manifest must declare a tool budget")
	}
	toolCalls := 0
	model := &plannerStubModel{reasoningDelta: map[string]any{
		"nextAction": "tool_call",
		"toolName":   "web_search",
		"toolInput":  map[string]any{"query": "杭州 天气"},
	}}
	loop := plannerLoop(t, model, &toolCalls)
	if _, failure, err := loop.RunTurn(t.Context(), plannerTurn("weather")); err != nil || failure != nil {
		t.Fatalf("weather turn must succeed: failure=%+v err=%v", failure, err)
	}
	if toolCalls > budget {
		t.Fatalf("toolCalls=%d exceeds manifest budget %d", toolCalls, budget)
	}
	if model.reasoningCalls > budget+1 {
		t.Fatalf("reasoningCalls=%d exceeds iteration budget %d", model.reasoningCalls, budget+1)
	}
}
