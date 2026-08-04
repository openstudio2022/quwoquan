// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

type subtaskBudgetWaitingExecutor struct{}

func (*subtaskBudgetWaitingExecutor) Execute(
	_ context.Context,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	rootBudget := request.TaskGraph.Tasks[0].Budget
	if err := emit(runruntime.ExecutionItemUpdate{
		ItemID:  "task:bounded-child",
		Kind:    generated.AssistantRunItemKindTask,
		Status:  generated.AssistantRunItemStatusStarted,
		TaskID:  "bounded-child",
		Summary: "执行有界子任务",
		Task: &runruntime.ExecutionTaskUpdate{
			Goal:       "验证子任务预算不增加全局容量",
			OwnerAgent: "manager",
			Budget: runruntime.TaskBudget{
				MaxToolCalls: 1,
				MaxTokens:    100,
				MaxCostUnits: 100,
				Deadline:     rootBudget.Deadline,
			},
		},
	}); err != nil {
		return runruntime.ExecutionResult{}, err
	}
	return runruntime.ExecutionResult{
		WaitingState: generated.AssistantRunStateWaitingUser,
		WaitReason:   "等待用户补充约束",
	}, nil
}

type consumingBudgetWaitingExecutor struct{}

func (*consumingBudgetWaitingExecutor) Execute(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	result, err := (&subtaskBudgetWaitingExecutor{}).Execute(ctx, request, emit)
	if err != nil {
		return runruntime.ExecutionResult{}, err
	}
	consumption := request.BudgetConsumption
	consumption.ToolCalls++
	consumption.Tokens += 100
	consumption.CostUnits += 80
	if err := emit(runruntime.ExecutionItemUpdate{
		Budget: &runruntime.BudgetConsumptionReceipt{
			Scope:       request.IdempotencyPrefix,
			Sequence:    request.BudgetReceiptSequence + 1,
			Consumption: consumption,
		},
	}); err != nil {
		return runruntime.ExecutionResult{}, err
	}
	return result, nil
}

func TestCheckpointBudgetSubtractsIdempotentRunConsumption(t *testing.T) {
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	run, err := workerCommandService(repository).Start(
		t.Context(),
		runruntime.StartCommand{
			UserID:          "user-budget-ledger",
			SessionID:       "session-budget-ledger",
			ClientRequestID: "request-budget-ledger",
			InputText:       "记录真实推理消费并等待补充",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository,
		queue,
		&consumingBudgetWaitingExecutor{},
		"worker-budget-ledger",
	)
	if worked, err := worker.ProcessNext(t.Context()); err != nil || !worked {
		t.Fatalf("process waiting run worked=%t error=%v", worked, err)
	}
	stored, err := repository.Load(t.Context(), run.RunID)
	if err != nil {
		t.Fatal(err)
	}
	rootBudget := stored.TaskGraph.Tasks[0].Budget
	scope := "run:" + stored.RunID + ":goal:" + fmt.Sprint(stored.GoalRevision)
	receipt := runruntime.BudgetConsumptionReceipt{
		Scope:    scope,
		Sequence: 1,
		Consumption: runruntime.BudgetConsumption{
			ToolCalls: 1,
			Tokens:    100,
			CostUnits: 80,
		},
	}
	remaining := stored.Checkpoint.RemainingBudget
	if remaining["toolCalls"] != int64(rootBudget.MaxToolCalls)-1 ||
		remaining["tokens"] != rootBudget.MaxTokens-100 ||
		remaining["costUnits"] != rootBudget.MaxCostUnits-80 {
		t.Fatalf("checkpoint did not subtract canonical consumption: %#v", remaining)
	}
	revision := stored.Revision
	if err := stored.RecordBudgetConsumption(receipt, time.Now()); err != nil {
		t.Fatalf("same receipt must be idempotent: %v", err)
	}
	if stored.Revision != revision {
		t.Fatalf("same receipt changed revision: got %d want %d", stored.Revision, revision)
	}
	conflict := receipt
	conflict.Consumption.Tokens++
	if err := stored.RecordBudgetConsumption(conflict, time.Now()); !errors.Is(err, runruntime.ErrRevisionConflict) {
		t.Fatalf("same receipt sequence with different usage error=%v", err)
	}

	receipt.Sequence++
	receipt.Consumption.Tokens += 50
	receipt.Consumption.CostUnits += 40
	if err := stored.RecordBudgetConsumption(receipt, time.Now()); err != nil {
		t.Fatal(err)
	}
	consumption := stored.Checkpoint.BudgetConsumption
	if consumption != receipt.Consumption {
		t.Fatalf("canonical consumption=%#v want %#v", consumption, receipt.Consumption)
	}
	if _, err := stored.CreateCheckpoint(
		"checkpoint:"+stored.RunID+":wait",
		stored.DefinitionOfDone.Outcome,
		[]string{"等待用户补充约束"},
		"",
		stored.Checkpoint.RemainingBudget,
		time.Now(),
	); err != nil {
		t.Fatal(err)
	}
	if stored.Checkpoint.BudgetConsumption != receipt.Consumption ||
		stored.Checkpoint.BudgetReceiptScope != scope ||
		stored.Checkpoint.BudgetReceiptSeq != receipt.Sequence {
		t.Fatalf("later checkpoint discarded budget receipt: %#v", stored.Checkpoint)
	}
}

func TestCheckpointBudgetUsesRootAuthorityWithoutSubtaskAmplification(
	t *testing.T,
) {
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	run, err := workerCommandService(repository).Start(
		t.Context(),
		runruntime.StartCommand{
			UserID:          "user-budget-checkpoint",
			SessionID:       "session-budget-checkpoint",
			ClientRequestID: "request-budget-checkpoint",
			InputText:       "建立有界任务图并等待补充",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository,
		queue,
		&subtaskBudgetWaitingExecutor{},
		"worker-budget-checkpoint",
	)
	if worked, err := worker.ProcessNext(t.Context()); err != nil || !worked {
		t.Fatalf("process waiting run worked=%t error=%v", worked, err)
	}
	stored, err := repository.Load(t.Context(), run.RunID)
	if err != nil {
		t.Fatal(err)
	}
	if stored.Checkpoint == nil || len(stored.TaskGraph.Tasks) != 2 {
		t.Fatalf("checkpoint/task graph not persisted: %#v", stored)
	}
	rootBudget := stored.TaskGraph.Tasks[0].Budget
	remaining := stored.Checkpoint.RemainingBudget
	if remaining["toolCalls"] != int64(rootBudget.MaxToolCalls) ||
		remaining["tokens"] != rootBudget.MaxTokens ||
		remaining["costUnits"] != rootBudget.MaxCostUnits {
		t.Fatalf(
			"checkpoint budget=%#v must equal root authority=%#v",
			remaining,
			rootBudget,
		)
	}
	childBudget := stored.TaskGraph.Tasks[1].Budget
	if remaining["toolCalls"] == int64(rootBudget.MaxToolCalls+childBudget.MaxToolCalls) ||
		remaining["tokens"] == rootBudget.MaxTokens+childBudget.MaxTokens ||
		remaining["costUnits"] == rootBudget.MaxCostUnits+childBudget.MaxCostUnits {
		t.Fatalf("subtask budget amplified checkpoint capacity: %#v", remaining)
	}
}
