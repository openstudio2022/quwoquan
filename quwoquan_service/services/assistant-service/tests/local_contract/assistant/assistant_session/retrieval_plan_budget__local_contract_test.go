// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-004
package local_contract

import (
	"errors"
	"testing"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
)

func TestMultiQuerySearchReservesEveryOwnerCallBeforeExecution(t *testing.T) {
	model := &policyCapableModel{sequence: func(_ string, call int) (string, map[string]any) {
		if call > 1 {
			return "", nil
		}
		return "web_search", map[string]any{
			"query": "杭州亲子露营",
			"searchQueries": []any{
				map[string]any{"dimension": "place", "query": "杭州亲子露营地点"},
				map[string]any{"dimension": "content", "query": "杭州亲子露营攻略"},
			},
		}
	}}
	tools := &policyTools{}
	config := reasoningProfile(t, generated.AssistantReasoningProfileBalanced)
	config.Budget.MaxToolCalls = 2
	config.SourceBreadth = 4
	ctx, err := orchestration.WithAgentExecutionPolicy(
		t.Context(),
		config,
		model,
		orchestration.RuntimeExecutionCapabilities{Background: true, Compaction: true},
	)
	if err != nil {
		t.Fatalf("negotiate policy: %v", err)
	}

	_, err = (orchestration.ReactRuntime{Model: model, Tools: tools}).Run(
		ctx,
		policyTurn("run-multi-query-budget"),
		policySkill(4),
	)
	if !errors.Is(err, orchestration.ErrExecutionBudgetExhausted) {
		t.Fatalf("three owner calls must exceed a two-call budget before execution: %v", err)
	}
	if got := tools.requestCount("run-multi-query-budget"); got != 0 {
		t.Fatalf("owner executor invoked %d time(s) after reservation failed", got)
	}
	consumption, ok := orchestration.AgentExecutionBudgetConsumptionFromContext(ctx)
	if !ok || consumption.ToolCalls != 0 {
		t.Fatalf("rejected fanout must not persist consumption: %#v", consumption)
	}
}

func TestMultiQuerySearchPersistsOneBudgetUnitPerPlannedQuery(t *testing.T) {
	model := &policyCapableModel{sequence: func(_ string, call int) (string, map[string]any) {
		if call > 1 {
			return "", nil
		}
		return "web_search", map[string]any{
			"query": "杭州亲子露营",
			"searchQueries": []any{
				map[string]any{"dimension": "place", "query": "杭州亲子露营地点"},
				map[string]any{"dimension": "content", "query": "杭州亲子露营攻略"},
			},
		}
	}}
	tools := &policyTools{}
	config := reasoningProfile(t, generated.AssistantReasoningProfileBalanced)
	config.Budget.MaxToolCalls = 3
	config.SourceBreadth = 4
	ctx, err := orchestration.WithAgentExecutionPolicy(
		t.Context(),
		config,
		model,
		orchestration.RuntimeExecutionCapabilities{Background: true, Compaction: true},
	)
	if err != nil {
		t.Fatalf("negotiate policy: %v", err)
	}
	_, err = (orchestration.ReactRuntime{Model: model, Tools: tools}).Run(
		ctx,
		policyTurn("run-multi-query-consumption"),
		policySkill(4),
	)
	if err != nil {
		t.Fatalf("run multi-query search: %v", err)
	}
	if got := tools.requestCount("run-multi-query-consumption"); got != 1 {
		t.Fatalf("tool coordinator invocations=%d want=1", got)
	}
	consumption, ok := orchestration.AgentExecutionBudgetConsumptionFromContext(ctx)
	if !ok || consumption.ToolCalls != 3 {
		t.Fatalf("logical owner call consumption=%#v want toolCalls=3", consumption)
	}
}
