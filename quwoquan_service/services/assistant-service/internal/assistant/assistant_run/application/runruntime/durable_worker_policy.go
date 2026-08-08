package runruntime

import (
	"context"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
)

func (w *DurableWorker) applyReasoningBudget(
	ctx context.Context,
	current Run,
	profile ReasoningProfileConfig,
) (Run, error) {
	expected := TaskBudget{
		MaxToolCalls: profile.Budget.MaxToolCalls,
		MaxTokens:    profile.Budget.MaxTokens,
		MaxCostUnits: profile.Budget.MaxCostUnits,
		Deadline:     current.CreatedAt.UTC().Add(profile.Budget.MaxDuration),
	}
	for _, task := range current.TaskGraph.Tasks {
		if task.TaskID == "task_root" && task.Budget == expected &&
			current.ReasoningPolicy == profile {
			return current, nil
		}
	}
	return w.commitMutation(ctx, current.RunID, "task_graph_patch", func(
		run *Run,
		now time.Time,
	) error {
		if run.ReasoningPolicy.Profile != "" && run.ReasoningPolicy != profile {
			return ErrRevisionConflict
		}
		for index := range run.TaskGraph.Tasks {
			if run.TaskGraph.Tasks[index].TaskID != "task_root" {
				continue
			}
			run.TaskGraph.Tasks[index].Budget = expected
			run.ReasoningPolicy = profile
			run.TaskGraph.GraphRevision++
			run.touch(now)
			return nil
		}
		return ErrInvalidTaskGraph
	})
}

func executionRequest(
	run Run,
	reasoningPolicy ReasoningProfileConfig,
) ExecutionRequest {
	var checkpoint *Checkpoint
	if run.Checkpoint != nil {
		cloned := *run.Checkpoint
		checkpoint = &cloned
	}
	budgetReceiptSequence := int64(0)
	if run.Checkpoint != nil &&
		run.Checkpoint.BudgetReceiptScope == budgetReceiptScope(run) {
		budgetReceiptSequence = run.Checkpoint.BudgetReceiptSeq
	}
	return ExecutionRequest{
		RunID:                     run.RunID,
		UserID:                    run.UserID,
		SessionID:                 run.SessionID,
		Goal:                      run.EffectiveGoal(),
		RequestedSkillID:          run.RequestedSkillID,
		RequestedDomainID:         run.RequestedDomainID,
		SkillPackageID:            run.SkillPackageID,
		SkillPackageReleaseDigest: run.SkillPackageReleaseDigest,
		FrozenPolicySelection:     clonePolicySelection(run.FrozenPolicySelection),
		RequestContext:            normalizeRequestContext(run.RequestContext),
		Trigger:                   cloneMap(run.Trigger),
		ReasoningProfile:          run.ReasoningProfile,
		ReasoningPolicy:           reasoningPolicy,
		DefinitionOfDone:          cloneDefinition(run.DefinitionOfDone),
		TaskGraph: TaskGraph{
			GraphRevision: run.TaskGraph.GraphRevision,
			Tasks:         cloneTasks(run.TaskGraph.Tasks),
		},
		GoalHistory:           append([]GoalRevision(nil), run.GoalHistory...),
		Checkpoint:            checkpoint,
		BudgetConsumption:     budgetConsumptionFromCheckpoint(run.Checkpoint),
		BudgetReceiptSequence: budgetReceiptSequence,
		ContextSnapshot:       cloneMap(run.ContextSnapshot),
		SurfaceCapabilities:   cloneMap(run.SurfaceCapabilities),
		SessionContinuity:     cloneSessionContinuityPtr(run.SessionContinuity),
		ConfirmedSlots:        run.ConfirmedSlotSnapshot(),
		SessionPreferences: append(
			[]preferencemodel.AssistantPreferenceSnapshot(nil),
			run.SessionPreferences...,
		),
		LongTermPreferences: append(
			[]preferencemodel.AssistantPreferenceSnapshot(nil),
			run.LongTermPreferences...,
		),
		FeedbackContextSnapshot: run.FeedbackContextSnapshot.Clone(),
		IdempotencyPrefix:       executionAttemptScope(run),
		CreatedAt:               run.CreatedAt,
	}
}

func remainingBudget(run Run) map[string]int64 {
	// The root task is the frozen ReasoningProfile authority. Child Task
	// budgets are allocations inside that ceiling; only the Run-owned durable
	// consumption ledger may reduce it.
	return remainingBudgetFromConsumption(
		run,
		budgetConsumptionFromCheckpoint(run.Checkpoint),
	)
}

func queueRunnableRun(run Run) bool {
	if terminalRunState(run.State) || run.State == generated.AssistantRunStatePaused {
		return false
	}
	switch run.State {
	case generated.AssistantRunStateWaitingUser,
		generated.AssistantRunStateWaitingApproval,
		generated.AssistantRunStateWaitingExternal:
		return false
	default:
		return true
	}
}

func terminalRunState(state generated.AssistantRunState) bool {
	return state == generated.AssistantRunStateCompleted ||
		state == generated.AssistantRunStateFailed ||
		state == generated.AssistantRunStateCancelled
}
