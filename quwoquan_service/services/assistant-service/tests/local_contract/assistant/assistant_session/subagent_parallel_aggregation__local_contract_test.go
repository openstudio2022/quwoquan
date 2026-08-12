// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/planner-aggregation-orchestration/spec.md#gwt-002
package local_contract

import (
	"context"
	"encoding/json"
	"strings"
	"sync"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	"quwoquan_service/services/assistant-service/tests/support/promptassets"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

// subagentStubModel 按 stage 返回可控响应，并记录每个 skill 各自的推理请求。
type subagentStubModel struct {
	mu             sync.Mutex
	reasoningTools map[string][]string
	failSkillID    string
}

func (model *subagentStubModel) Complete(
	_ context.Context,
	req orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	switch strings.TrimSpace(req.Stage) {
	case "orchestration":
		delta := map[string]any{
			"problemShape": "multi_skill",
			"subagentPlan": []any{
				map[string]any{"skillId": "weather", "goal": "确认周末天气", "role": "supporting"},
				map[string]any{"skillId": "travel_companion", "goal": "确认吃玩住行与交通方案", "role": "primary"},
			},
		}
		raw, _ := json.Marshal(delta)
		return orchestration.ModelResponse{Text: string(raw), StructuredDelta: delta}, nil
	case "reasoning":
		model.mu.Lock()
		if model.reasoningTools == nil {
			model.reasoningTools = map[string][]string{}
		}
		model.reasoningTools[req.SkillID] = append(
			model.reasoningTools[req.SkillID],
			toolNames(req.ToolCatalog)...,
		)
		model.mu.Unlock()
		toolName := "web_search"
		if req.SkillID == "travel_companion" {
			toolName = "app_search"
		}
		delta := map[string]any{
			"nextAction": "tool_call",
			"toolName":   toolName,
			"toolInput":  map[string]any{"query": "杭州 周末"},
		}
		raw, _ := json.Marshal(delta)
		return orchestration.ModelResponse{Text: string(raw), StructuredDelta: delta}, nil
	case "evidence_processing":
		delta := map[string]any{
			"retrievalProcessing": map[string]any{
				"processingSummary":  "已核对该子任务的关键信息。",
				"selectedKeyPoints":  []string{"子任务结论已对齐"},
				"acceptedReferences": []any{},
			},
			"evidenceSufficient": true,
		}
		raw, _ := json.Marshal(delta)
		return orchestration.ModelResponse{Text: string(raw), StructuredDelta: delta}, nil
	default:
		if req.SkillID == model.failSkillID {
			return orchestration.ModelResponse{}, ports.ProviderFailure{
				Capability: "model",
				Reason:     ports.ProviderFailureInvalidResponse,
			}
		}
		answer := "你周末去杭州可以按室外行程安排，高铁班次也充足。"
		return orchestration.ModelResponse{
			Text:            answer,
			StructuredDelta: map[string]any{"userMarkdown": answer},
		}, nil
	}
}

func toolNames(catalog []ports.ModelToolDefinition) []string {
	names := make([]string, 0, len(catalog))
	for _, definition := range catalog {
		names = append(names, definition.Name)
	}
	return names
}

func subagentLoop(t *testing.T, model orchestration.ModelProvider) *orchestration.AgentLoop {
	t.Helper()
	registry := canonicalTestToolRegistry(map[string]toolpkg.Handler{
		"web_search": func(_ context.Context, _ toolpkg.Request) (toolpkg.Result, error) {
			return toolpkg.Result{Output: map[string]any{
				"summary":            "杭州周末多云，适合安排室外行程。",
				"references":         []any{},
				"reliable":           true,
				"evidenceAssessment": acceptedEvidenceAssessment("subagent_web_search_stub"),
			}}, nil
		},
		"app_search": func(_ context.Context, _ toolpkg.Request) (toolpkg.Result, error) {
			return toolpkg.Result{Output: map[string]any{
				"summary":            "杭州东站到市区的地铁与公交班次充足。",
				"resultBuckets":      []any{},
				"citations":          []any{},
				"emergedTagRefs":     []string{},
				"provenance":         map[string]any{"source": "search_index_view"},
				"retrievalPlan":      map[string]any{"digest": "sha256:test"},
				"evidenceAssessment": acceptedEvidenceAssessment("subagent_app_search_stub"),
			}}, nil
		},
	})
	loop := orchestration.NewAgentLoop(
		nil,
		orchestration.ReactRuntime{
			Model: model,
			Tools: orchestration.DefaultToolCoordinator{Registry: registry},
		},
		nil,
	)
	loop.PromptAssets = promptassets.MustResolver(t)
	loop.Catalog = skillfixture.Loader{}
	loop.Subagents = orchestration.ModelSubagentPlanner{Model: model, Loader: skillfixture.Loader{}}
	return loop
}

func multiSkillTurn() assistant.AssistantTurn {
	selection := testFrozenPolicySelection("assistant-default", "fallback_general_search", "assistant")
	selection.Template.AllowedTools = []string{"web_search", "app_search"}
	return assistant.AssistantTurn{
		SessionID:             "session-subagent",
		TurnID:                "turn-subagent",
		TraceID:               "trace-subagent",
		SkillID:               "travel_companion",
		DomainID:              "travel",
		Input:                 assistant.AssistantTurnInput{Text: "周末从上海出发去杭州，天气和交通怎么安排"},
		FrozenPolicySelection: selection,
	}
}

// 多技能问题必须并行跑出多条 skillRuns，并由聚合裁决出统一的最终形态。
func TestMultiSkillTurnAggregatesParallelSubagentRuns(t *testing.T) {
	model := &subagentStubModel{}
	loop := subagentLoop(t, model)
	events, failure, err := loop.RunTurn(t.Context(), multiSkillTurn())
	if err != nil || failure != nil {
		t.Fatalf("multi skill turn must succeed: failure=%+v err=%v", failure, err)
	}
	payload := completedPayload(t, events)
	runs, ok := payload["skillRuns"].([]map[string]any)
	if !ok || len(runs) != 2 {
		t.Fatalf("skillRuns=%#v want two parallel runs", payload["skillRuns"])
	}
	if payload["finalAnswerMode"] != "full" {
		t.Fatalf("finalAnswerMode=%v want full", payload["finalAnswerMode"])
	}
	plans, ok := payload["subagentPlan"].([]map[string]any)
	if !ok || len(plans) != 2 {
		t.Fatalf("subagentPlan=%#v want two plans", payload["subagentPlan"])
	}
	primaries := 0
	for _, plan := range plans {
		if plan["role"] == "primary" {
			primaries++
		}
	}
	if primaries != 1 {
		t.Fatalf("subagentPlan must declare exactly one primary, got %d", primaries)
	}
	dispatching, merging := false, false
	probeLifecycle := map[string]map[string]bool{}
	for _, process := range processEvents(events) {
		switch process.Stage {
		case "dispatching":
			dispatching = true
		case "merging":
			merging = true
		case "executing":
			if probeLifecycle[process.ProcessID] == nil {
				probeLifecycle[process.ProcessID] = map[string]bool{}
			}
			probeLifecycle[process.ProcessID][process.Status] = true
		}
	}
	if !dispatching || !merging {
		t.Fatalf("multi skill turn must emit dispatching and merging processes, got %v/%v", dispatching, merging)
	}
	if len(probeLifecycle) != 2 {
		t.Fatalf("parallel probe tasks=%d want one per subagent", len(probeLifecycle))
	}
	for processID, lifecycle := range probeLifecycle {
		if !lifecycle["active"] ||
			(!lifecycle["completed"] && !lifecycle["failed"]) {
			t.Fatalf("parallel probe %s lifecycle=%#v", processID, lifecycle)
		}
	}
}

// 每个子代理只能看到自己清单与策略交集内的工具，不得越权拿到兄弟子代理的工具。
func TestSubagentToolWhitelistIsIsolated(t *testing.T) {
	model := &subagentStubModel{}
	loop := subagentLoop(t, model)
	if _, failure, err := loop.RunTurn(t.Context(), multiSkillTurn()); err != nil || failure != nil {
		t.Fatalf("multi skill turn must succeed: failure=%+v err=%v", failure, err)
	}
	model.mu.Lock()
	defer model.mu.Unlock()
	weatherTools := model.reasoningTools["weather"]
	transportTools := model.reasoningTools["travel_companion"]
	if len(weatherTools) == 0 || len(transportTools) == 0 {
		t.Fatalf("both subagents must reason: %#v", model.reasoningTools)
	}
	for _, name := range weatherTools {
		if name == "app_search" {
			t.Fatalf("weather subagent must not receive app_search: %v", weatherTools)
		}
	}
}

// 单个子代理失败必须被隔离：整轮仍然给出有界回答，并把失败技能标为阻塞项。
func TestFailedSubagentDegradesToBoundedAnswer(t *testing.T) {
	model := &subagentStubModel{failSkillID: "weather"}
	loop := subagentLoop(t, model)
	events, failure, err := loop.RunTurn(t.Context(), multiSkillTurn())
	if err != nil || failure != nil {
		t.Fatalf("single subagent failure must not fail the turn: failure=%+v err=%v", failure, err)
	}
	payload := completedPayload(t, events)
	if payload["finalAnswerMode"] != "bounded_answer" {
		t.Fatalf("finalAnswerMode=%v want bounded_answer", payload["finalAnswerMode"])
	}
	aggregation, ok := payload["aggregationState"].(map[string]any)
	if !ok {
		t.Fatalf("aggregationState=%#v", payload["aggregationState"])
	}
	blocking, ok := aggregation["blockingSkills"].([]string)
	if !ok || len(blocking) != 1 || blocking[0] != "weather" {
		t.Fatalf("blockingSkills=%#v want the failed subagent", aggregation["blockingSkills"])
	}
	if aggregation["canGivePartialAnswer"] != true {
		t.Fatalf("aggregationState=%#v want a partial answer", aggregation)
	}
}
