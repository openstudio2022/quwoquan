// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
package local_contract

import (
	"context"
	"errors"
	"testing"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

type budgetFailingTools struct {
	policyTools
	failure error
}

func (tools *budgetFailingTools) Execute(
	_ context.Context,
	request orchestration.ToolRequest,
) (orchestration.ToolExecution, error) {
	tools.mu.Lock()
	if tools.requests == nil {
		tools.requests = map[string][]orchestration.ToolRequest{}
	}
	tools.requests[request.Turn.TurnID] = append(
		tools.requests[request.Turn.TurnID],
		request,
	)
	tools.mu.Unlock()
	return orchestration.ToolExecution{}, tools.failure
}

func TestAgentLoopAccumulatesOneSharedModelAndToolBudget(t *testing.T) {
	model := &policyCapableModel{usageTokens: 7}
	tools := &policyTools{}
	ctx, err := orchestration.WithAgentExecutionPolicy(
		t.Context(),
		reasoningProfile(t, generated.AssistantReasoningProfileBalanced),
		model,
		orchestration.RuntimeExecutionCapabilities{
			Background: true,
			Compaction: true,
		},
	)
	if err != nil {
		t.Fatalf("negotiate policy: %v", err)
	}
	result, err := (orchestration.ReactRuntime{
		Model: model,
		Tools: tools,
	}).Run(ctx, policyTurn("run-shared-consumption"), policySkill(2))
	if err != nil {
		t.Fatalf("run AgentLoop: %v", err)
	}
	consumption, ok := orchestration.AgentExecutionBudgetConsumptionFromContext(ctx)
	if !ok {
		t.Fatal("execution context lost the shared consumption authority")
	}
	wantToolCalls := int64(tools.requestCount("run-shared-consumption"))
	if consumption.ToolCalls != wantToolCalls ||
		consumption.ToolCalls != int64(len(result.Steps)) {
		t.Fatalf(
			"tool consumption=%d requests=%d steps=%d",
			consumption.ToolCalls,
			wantToolCalls,
			len(result.Steps),
		)
	}
	wantTokens := int64(0)
	for _, raw := range result.Usage {
		usage, _ := raw.(map[string]any)
		switch value := usage["totalTokens"].(type) {
		case int64:
			wantTokens += value
		case int:
			wantTokens += int64(value)
		}
	}
	if wantTokens <= 0 || consumption.Tokens != wantTokens ||
		consumption.CostUnits != wantTokens {
		t.Fatalf(
			"consumption=%#v must equal model usage tokens=%d",
			consumption,
			wantTokens,
		)
	}
}

func TestAgentLoopCountsAnActuallyInvokedFailingTool(t *testing.T) {
	model := &policyCapableModel{usageTokens: 3}
	toolFailure := errors.New("tool dependency unavailable")
	tools := &budgetFailingTools{failure: toolFailure}
	ctx, err := orchestration.WithAgentExecutionPolicy(
		t.Context(),
		reasoningProfile(t, generated.AssistantReasoningProfileBalanced),
		model,
		orchestration.RuntimeExecutionCapabilities{
			Background: true,
			Compaction: true,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	_, err = (orchestration.ReactRuntime{Model: model, Tools: tools}).Run(
		ctx,
		policyTurn("run-failing-tool-consumption"),
		policySkill(2),
	)
	if !errors.Is(err, toolFailure) {
		t.Fatalf("tool failure=%v want %v", err, toolFailure)
	}
	consumption, ok := orchestration.AgentExecutionBudgetConsumptionFromContext(ctx)
	if !ok || consumption.ToolCalls != 1 ||
		tools.requestCount("run-failing-tool-consumption") != 1 {
		t.Fatalf("actual failing tool call was not counted once: %#v", consumption)
	}
}

func TestDurableExecutorContinuesThePersistedBudgetReceiptSequence(
	t *testing.T,
) {
	executor, _, _ := durablePresentationExecutor(
		t,
		&durablePresentationContextResolver{},
	)
	request := durablePresentationRequest(t)
	request.BudgetConsumption = runruntime.BudgetConsumption{
		ToolCalls: 1,
		Tokens:    90,
		CostUnits: 70,
	}
	request.BudgetReceiptSequence = 3
	receipts := make([]runruntime.BudgetConsumptionReceipt, 0)
	_, err := executor.Execute(
		t.Context(),
		request,
		func(update runruntime.ExecutionItemUpdate) error {
			if update.Budget != nil {
				receipts = append(receipts, *update.Budget)
			}
			return nil
		},
	)
	if err != nil {
		t.Fatalf("Execute() error=%v", err)
	}
	if len(receipts) < 2 {
		t.Fatalf("model boundaries emitted %d receipts, want at least 2", len(receipts))
	}
	for index, receipt := range receipts {
		wantSequence := int64(4 + index)
		if receipt.Scope != request.IdempotencyPrefix ||
			receipt.Sequence != wantSequence {
			t.Fatalf("receipt[%d]=%#v want scope=%q sequence=%d", index, receipt, request.IdempotencyPrefix, wantSequence)
		}
		if receipt.Consumption != request.BudgetConsumption {
			t.Fatalf("zero-usage model discarded restored consumption: %#v", receipt)
		}
	}
}
