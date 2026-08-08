package runruntime

import (
	"context"
	"fmt"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

func (w *DurableWorker) awaitCoordinatedCancellation(
	ctx context.Context,
	runID string,
) error {
	deadline := time.NewTimer(10 * time.Second)
	defer deadline.Stop()
	ticker := time.NewTicker(50 * time.Millisecond)
	defer ticker.Stop()
	for {
		run, err := w.repository.Load(ctx, runID)
		if err != nil {
			return err
		}
		if run.State == generated.AssistantRunStateCancelled {
			return nil
		}
		if terminalRunState(run.State) {
			return ErrExecutionCancelled
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-deadline.C:
			return ErrExecutionCancelled
		case <-ticker.C:
		}
	}
}

func (w *DurableWorker) monitorRunControl(
	ctx context.Context,
	runID string,
	cancel context.CancelCauseFunc,
	done <-chan struct{},
) {
	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-done:
			return
		case <-ticker.C:
			run, err := w.repository.Load(ctx, runID)
			if err != nil {
				cancel(&runControlObservationError{cause: err})
				return
			}
			if terminalRunState(run.State) || run.PauseRequested ||
				run.State == generated.AssistantRunStatePaused {
				cancel(nil)
				return
			}
		}
	}
}

// runControlObservationError distinguishes a failed durable control read from
// an AgentLoop failure. The worker must stop producing new work while control
// is unknown, but the same Run remains runnable and must be retried instead of
// being committed as failed.
type runControlObservationError struct {
	cause error
}

func (e *runControlObservationError) Error() string {
	return fmt.Sprintf("observe assistant run control: %v", e.cause)
}

func (e *runControlObservationError) Unwrap() error {
	return e.cause
}

func (w *DurableWorker) checkpointAndPause(
	ctx context.Context,
	current Run,
	result ExecutionResult,
) error {
	_, err := w.commitMutation(ctx, current.RunID, "checkpoint_committed", func(
		run *Run,
		now time.Time,
	) error {
		return applyCheckpointAndPause(run, result, now)
	})
	if err != nil {
		return err
	}
	return nil
}

func applyCheckpointAndPause(
	run *Run,
	result ExecutionResult,
	now time.Time,
) error {
	previousGoalRevision := run.GoalRevision
	if err := run.MergeConfirmedSlots(result.ConfirmedSlots, now); err != nil {
		return err
	}
	if run.State == generated.AssistantRunStateExecuting {
		if err := run.Transition(
			generated.AssistantRunStateCheckpointing,
			"pause_requested",
			now,
		); err != nil {
			return err
		}
	}
	if _, err := run.CreateCheckpoint(
		"checkpoint:"+run.RunID+":"+fmt.Sprint(run.Revision+1),
		run.DefinitionOfDone.Outcome,
		[]string{"执行已在安全边界暂停"},
		"",
		remainingBudget(*run),
		now,
	); err != nil {
		return err
	}
	if err := run.ApplySafeBoundary(now); err != nil {
		return err
	}
	if run.GoalRevision != previousGoalRevision {
		return appendGoalRevisionPlanItem(run, now)
	}
	return nil
}

func (w *DurableWorker) waitRun(
	ctx context.Context,
	current Run,
	result ExecutionResult,
) error {
	current, pauseWon, err := w.persistWaitingPresentation(
		ctx,
		current,
		result.Presentation,
	)
	if err != nil {
		return err
	}
	if pauseWon {
		return w.checkpointAndPause(ctx, current, result)
	}
	_, err = w.commitMutation(ctx, current.RunID, "checkpoint_committed", func(
		run *Run,
		now time.Time,
	) error {
		if run.State == generated.AssistantRunStatePaused {
			return nil
		}
		if run.PauseRequested {
			return applyCheckpointAndPause(run, result, now)
		}
		if err := run.MergeConfirmedSlots(result.ConfirmedSlots, now); err != nil {
			return err
		}
		if run.State == generated.AssistantRunStateExecuting {
			if err := run.Transition(
				generated.AssistantRunStateCheckpointing,
				result.WaitReason,
				now,
			); err != nil {
				return err
			}
		}
		if _, err := run.CreateCheckpoint(
			"checkpoint:"+run.RunID+":"+fmt.Sprint(run.Revision+1),
			run.DefinitionOfDone.Outcome,
			[]string{result.WaitReason},
			result.PendingApprovalRef,
			remainingBudget(*run),
			now,
		); err != nil {
			return err
		}
		return run.Transition(result.WaitingState, result.WaitReason, now)
	})
	if err != nil {
		return err
	}
	return nil
}
