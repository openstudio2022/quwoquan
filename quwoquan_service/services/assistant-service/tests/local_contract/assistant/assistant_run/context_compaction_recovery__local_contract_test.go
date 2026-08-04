// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"fmt"
	"sync"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

func TestContextCompactionPersistsMonotonicCursorAndSurvivesCheckpointReplacement(
	t *testing.T,
) {
	repository := newMemoryRunRepository()
	run, err := workerCommandService(repository).Start(
		t.Context(),
		runruntime.StartCommand{
			UserID:          "context-owner",
			SessionID:       "context-session",
			ClientRequestID: "context-request",
			InputText:       "持续探索并保留恢复游标",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	now := run.CreatedAt.Add(2 * time.Minute)
	ctx, err := runruntime.WithContextCompactionRuntime(
		t.Context(),
		runruntime.ContextCompactionRuntimeConfig{
			Scope:           runruntime.ContextProgressScope(run),
			CheckpointEvery: time.Minute,
			StartedAt:       run.CreatedAt,
			Now:             func() time.Time { return now },
			Sink: func(
				_ context.Context,
				receipt runruntime.ContextProgressReceipt,
			) error {
				return run.RecordContextProgress(receipt, now)
			},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	ctx = runruntime.WithContextCompactionBoundary(ctx)
	state := runruntime.AppendContextObservation(
		runruntime.ContextExecutionState{
			PlanCursor:      1,
			ToolIteration:   1,
			NavigationDepth: 1,
			SourceIDs:       []string{"source:official:1"},
			ToolHistory:     []string{"web_open"},
		},
		runruntime.ContextObservationSnapshot{
			Iteration: 1,
			ToolName:  "web_open",
			Status:    "completed",
			Summary:   "官方来源已读取",
			SourceIDs: []string{"source:official:1"},
		},
	)
	if err := runruntime.PersistContextProgress(ctx, state); err != nil {
		t.Fatal(err)
	}
	if !runruntime.ContextCompactionDue(ctx) {
		t.Fatal("CheckpointEvery elapsed but compaction was not due")
	}
	checkpoint, err := runruntime.CommitContextCompaction(
		ctx,
		state,
		"目标是持续探索；官方来源已读取；仍需完成综合。",
	)
	if err != nil {
		t.Fatal(err)
	}
	if checkpoint.ContextRevision != 1 ||
		checkpoint.State.PlanCursor != 1 ||
		len(checkpoint.State.RecentObservations) != 0 {
		t.Fatalf("invalid compaction checkpoint: %#v", checkpoint)
	}
	if run.Checkpoint == nil || run.Checkpoint.ContextReceiptSeq != 2 ||
		run.Checkpoint.ContextCompaction == nil ||
		run.Checkpoint.ContextState.NavigationDepth != 1 {
		t.Fatalf("context progress was not persisted: %#v", run.Checkpoint)
	}
	if _, err := run.CreateCheckpoint(
		"checkpoint:"+run.RunID+":wait",
		run.DefinitionOfDone.Outcome,
		[]string{"等待外部系统"},
		"",
		run.Checkpoint.RemainingBudget,
		now.Add(time.Second),
	); err != nil {
		t.Fatal(err)
	}
	if run.Checkpoint.ContextReceiptSeq != 2 ||
		run.Checkpoint.ContextState.PlanCursor != 1 ||
		run.Checkpoint.ContextCompaction == nil ||
		run.Checkpoint.ContextCompaction.SummaryText == "" {
		t.Fatalf("checkpoint replacement discarded context state: %#v", run.Checkpoint)
	}
}

type contextRecoveryExecutor struct {
	mu       sync.Mutex
	calls    int
	restored runruntime.ContextExecutionState
}

func (e *contextRecoveryExecutor) Execute(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	_ func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	ctx = runruntime.WithContextCompactionBoundary(ctx)
	state, _, ok := runruntime.RestoreContextExecution(ctx)
	if !ok {
		return runruntime.ExecutionResult{}, fmt.Errorf(
			"durable worker did not inject context runtime",
		)
	}
	e.mu.Lock()
	e.calls++
	call := e.calls
	if call == 2 {
		e.restored = state
	}
	e.mu.Unlock()
	if call == 1 {
		state = runruntime.AppendContextObservation(
			runruntime.ContextExecutionState{
				PlanCursor:          2,
				ToolIteration:       1,
				ReflectionIteration: 2,
				NavigationDepth:     2,
				SourceIDs:           []string{"source:recovery:1"},
				ToolHistory:         []string{"web_open"},
			},
			runruntime.ContextObservationSnapshot{
				Iteration: 2,
				ToolName:  "web_open",
				Status:    "completed",
				Summary:   "恢复测试来源已读取",
				SourceIDs: []string{"source:recovery:1"},
			},
		)
		if err := runruntime.PersistContextProgress(ctx, state); err != nil {
			return runruntime.ExecutionResult{}, err
		}
		return runruntime.ExecutionResult{}, runruntime.ErrExecutionReplanned
	}
	return runruntime.ExecutionResult{
		WaitingState: generated.AssistantRunStateWaitingUser,
		WaitReason:   "等待用户确认恢复结果",
	}, nil
}

func TestDurableWorkerRestoresContextLedgerBeforeReenteringExecutor(
	t *testing.T,
) {
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	run, err := workerCommandService(repository).Start(
		t.Context(),
		runruntime.StartCommand{
			UserID:          "context-restart-owner",
			SessionID:       "context-restart-session",
			ClientRequestID: "context-restart-request",
			InputText:       "在 Worker 重启后继续探索",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	queue.enqueue(run.RunID)
	executor := &contextRecoveryExecutor{}
	firstWorker := runruntime.NewDurableWorker(
		repository,
		queue,
		executor,
		"context-worker-first",
	)
	if worked, err := firstWorker.ProcessNext(t.Context()); err != nil || !worked {
		t.Fatalf("first worker worked=%t err=%v", worked, err)
	}
	afterFirst, err := repository.Load(t.Context(), run.RunID)
	if err != nil {
		t.Fatal(err)
	}
	if afterFirst.Checkpoint == nil ||
		afterFirst.Checkpoint.ContextState.PlanCursor != 2 ||
		afterFirst.Checkpoint.ContextState.NavigationDepth != 2 {
		t.Fatalf("first worker did not persist cursor: %#v", afterFirst.Checkpoint)
	}
	secondWorker := runruntime.NewDurableWorker(
		repository,
		queue,
		executor,
		"context-worker-second",
	)
	if worked, err := secondWorker.ProcessNext(t.Context()); err != nil || !worked {
		t.Fatalf("second worker worked=%t err=%v", worked, err)
	}
	executor.mu.Lock()
	restored := executor.restored
	executor.mu.Unlock()
	if restored.PlanCursor != 2 || restored.ToolIteration != 1 ||
		restored.ReflectionIteration != 2 || restored.NavigationDepth != 2 ||
		len(restored.SourceIDs) != 1 ||
		restored.SourceIDs[0] != "source:recovery:1" ||
		len(restored.ToolHistory) != 1 ||
		restored.ToolHistory[0] != "web_open" {
		t.Fatalf("second worker received reset context state: %#v", restored)
	}
	stored, err := repository.Load(t.Context(), run.RunID)
	if err != nil {
		t.Fatal(err)
	}
	if stored.State != generated.AssistantRunStateWaitingUser ||
		stored.Checkpoint == nil ||
		stored.Checkpoint.ContextState.PlanCursor != 2 {
		t.Fatalf("waiting checkpoint lost restored context: %#v", stored)
	}
}
