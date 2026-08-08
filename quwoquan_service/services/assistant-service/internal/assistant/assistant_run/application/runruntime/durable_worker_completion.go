package runruntime

import (
	"context"
	"errors"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

func (w *DurableWorker) completeRun(
	ctx context.Context,
	current Run,
	result ExecutionResult,
	preverified VerificationVerdict,
	preverifiedFound bool,
) error {
	prepared, replanned, err := w.applyCompletionBoundary(ctx, current)
	if err != nil {
		if completionIntegrityFailure(err) {
			return w.failRun(ctx, current, "completion_boundary_corrupt", err)
		}
		return err
	}
	if replanned {
		if prepared.PauseRequested {
			return w.checkpointAndPause(ctx, prepared, result)
		}
		return nil
	}
	current = prepared
	if terminalRunState(current.State) {
		return nil
	}
	if current.PauseRequested {
		return w.checkpointAndPause(ctx, current, result)
	}
	switch current.State {
	case generated.AssistantRunStateExecuting:
	case generated.AssistantRunStatePaused,
		generated.AssistantRunStateWaitingApproval,
		generated.AssistantRunStateWaitingExternal:
		return nil
	default:
		return w.failRun(ctx, current, "completion_boundary_state_invalid", ErrJournalCorrupt)
	}
	availableArtifactRefs := uniqueSorted(append(
		append([]string{}, result.ArtifactRefs...),
		result.EvidenceRefs...,
	))
	verdict, found, err := verificationVerdictForCurrentAttempt(current)
	if err != nil {
		return w.failRun(ctx, current, "verification_journal_corrupt", err)
	}
	if !found {
		if preverifiedFound {
			verdict = cloneExecutionVerificationVerdict(preverified)
		} else {
			verdict = w.hooks.VerifyCompletion(ctx, current.DefinitionOfDone, VerificationInput{
				Run:                   current,
				Result:                result,
				AvailableArtifactRefs: availableArtifactRefs,
			})
		}
	}
	if !verdict.Accepted {
		observeCompletionRejected("verdict")
		var pauseWon bool
		current, verdict, pauseWon, err = w.persistVerificationVerdict(ctx, current, verdict)
		if err != nil {
			if errors.Is(err, ErrExecutionReplanned) {
				return nil
			}
			if completionIntegrityFailure(err) {
				return w.failRun(ctx, current, "verification_journal_corrupt", err)
			}
			return err
		}
		if pauseWon {
			return w.checkpointAndPause(ctx, current, result)
		}
		repairRun, repaired, repairPauseWon, terminalReason, repairErr := w.tryVerificationRepair(
			ctx,
			current,
			verdict,
		)
		if repairErr != nil {
			return repairErr
		}
		if repaired {
			return nil
		}
		if repairPauseWon {
			return w.checkpointAndPause(ctx, repairRun, result)
		}
		return w.failRunAtCompletion(
			ctx,
			current,
			terminalReason,
			ErrCompletionRejected,
			result,
		)
	}

	completionHook, err := w.runHook(ctx, HookBeforeComplete, current, map[string]any{
		"verification": verificationVerdictPayload(verdict),
	})
	if err != nil {
		return w.failRunAtCompletion(
			ctx,
			current,
			"before_complete_hook_failed",
			err,
			result,
		)
	}
	switch completionHook.Decision {
	case HookBlock:
		return w.failRunAtCompletion(
			ctx,
			current,
			"before_complete_hook_blocked",
			ErrCompletionRejected,
			result,
		)
	case HookRequireConfirmation:
		continuationToken := assistantRunContinuationToken(
			current.RunID,
			completionHook.ConfirmationRef,
		)
		if _, valid := pendingDeviceActionBinding(
			result.Presentation,
			current.RunID,
			completionHook.ConfirmationRef,
			continuationToken,
			"approved",
			w.now().UTC(),
		); !valid {
			return w.failRunAtCompletion(
				ctx,
				current,
				"before_complete_confirmation_invalid",
				ErrCompletionRejected,
				result,
			)
		}
		result.WaitingState = generated.AssistantRunStateWaitingApproval
		result.WaitReason = "before_complete_confirmation_required"
		result.PendingApprovalRef = completionHook.ConfirmationRef
		return w.waitRun(ctx, current, result)
	}

	run, authoritative, capsule, pauseWon, err := w.persistAcceptedCompletion(
		ctx,
		current,
		verdict,
		result,
		availableArtifactRefs,
	)
	if err != nil {
		if errors.Is(err, ErrExecutionReplanned) {
			return nil
		}
		if completionIntegrityFailure(err) {
			return w.failRun(ctx, current, "completion_capsule_rejected", err)
		}
		return err
	}
	if pauseWon {
		return w.checkpointAndPause(ctx, run, result)
	}
	return w.resumeAcceptedCompletion(ctx, run, authoritative, capsule)
}

func (w *DurableWorker) runHook(
	ctx context.Context,
	phase HookPhase,
	run Run,
	data map[string]any,
) (HookResult, error) {
	return w.hooks.Run(ctx, HookInput{
		InvocationID:         StableHookInvocationID(run.RunID, phase, run.Revision),
		Phase:                phase,
		Run:                  run,
		RunRevision:          run.Revision,
		TaskID:               "task_root",
		Data:                 data,
		ProtectedFactsDigest: ProtectedRunFactsDigest(run),
	})
}

func ProtectedRunFactsDigest(run Run) string {
	digest, err := commandDigest("assistant_run_protected_facts", struct {
		RunID                     string           `json:"runId"`
		UserID                    string           `json:"userId"`
		SkillPackageReleaseDigest string           `json:"skillPackageReleaseDigest"`
		InputText                 string           `json:"inputText"`
		GoalRevision              int64            `json:"goalRevision"`
		GoalHistory               []GoalRevision   `json:"goalHistory"`
		DefinitionOfDone          DefinitionOfDone `json:"definitionOfDone"`
	}{
		RunID:                     run.RunID,
		UserID:                    run.UserID,
		SkillPackageReleaseDigest: run.SkillPackageReleaseDigest,
		InputText:                 run.InputText,
		GoalRevision:              run.GoalRevision,
		GoalHistory:               append([]GoalRevision(nil), run.GoalHistory...),
		DefinitionOfDone:          cloneDefinition(run.DefinitionOfDone),
	})
	if err != nil {
		return ""
	}
	return "sha256:" + digest
}

func goalIndependentProtectedRunFactsDigest(run Run) string {
	digest, err := commandDigest("assistant_run_goal_independent_protected_facts", struct {
		RunID                     string           `json:"runId"`
		UserID                    string           `json:"userId"`
		SkillPackageReleaseDigest string           `json:"skillPackageReleaseDigest"`
		InputText                 string           `json:"inputText"`
		DefinitionOfDone          DefinitionOfDone `json:"definitionOfDone"`
	}{
		RunID:                     run.RunID,
		UserID:                    run.UserID,
		SkillPackageReleaseDigest: run.SkillPackageReleaseDigest,
		InputText:                 run.InputText,
		DefinitionOfDone:          cloneDefinition(run.DefinitionOfDone),
	})
	if err != nil {
		return ""
	}
	return "sha256:" + digest
}

func goalChainDigest(run Run) string {
	digest, err := commandDigest("assistant_run_goal_chain", struct {
		GoalRevision  int64  `json:"goalRevision"`
		EffectiveGoal string `json:"effectiveGoal"`
	}{
		GoalRevision:  run.GoalRevision,
		EffectiveGoal: run.EffectiveGoal(),
	})
	if err != nil {
		return ""
	}
	return "sha256:" + digest
}

func (w *DurableWorker) failRun(
	ctx context.Context,
	current Run,
	reason string,
	cause error,
) error {
	return w.failRunWithPauseResult(ctx, current, reason, cause, nil)
}

func (w *DurableWorker) failRunAtCompletion(
	ctx context.Context,
	current Run,
	reason string,
	cause error,
	result ExecutionResult,
) error {
	return w.failRunWithPauseResult(ctx, current, reason, cause, &result)
}

func (w *DurableWorker) failRunWithPauseResult(
	ctx context.Context,
	current Run,
	reason string,
	cause error,
	pauseResult *ExecutionResult,
) error {
	failure := assistantmodel.AssistantRunTerminalFailure{
		Code:   "ASSISTANT.SYSTEM.run_execution_failed",
		Origin: "system",
		Kind:   "internal",
		Nature: "transient",
	}
	var executionFailure *ExecutionFailure
	if errors.As(cause, &executionFailure) {
		if value := strings.TrimSpace(executionFailure.Code); value != "" {
			failure.Code = value
		}
		if value := strings.TrimSpace(executionFailure.Origin); value != "" {
			failure.Origin = value
		}
		if value := strings.TrimSpace(executionFailure.Kind); value != "" {
			failure.Kind = value
		}
		if value := strings.TrimSpace(executionFailure.Nature); value != "" {
			failure.Nature = value
		}
	}
	pauseWon := false
	committed, failureCommitted, err := w.commitMutationWithOutcome(
		ctx,
		current.RunID,
		"failed",
		func(
			run *Run,
			now time.Time,
		) error {
			pauseWon = false
			if terminalRunState(run.State) {
				return nil
			}
			if pauseResult != nil && run.PauseRequested {
				pauseWon = true
				return nil
			}
			run.CancelActiveWork(reason, now)
			if err := run.Transition(
				generated.AssistantRunStateFailed,
				reason,
				now,
			); err != nil {
				return err
			}
			if err := run.SetTerminalSnapshot(assistantmodel.AssistantRunTerminalSnapshot{
				AnswerText:        "",
				Processes:         []assistantmodel.AssistantRunVisibleProcess{},
				Failure:           &failure,
				SelectedPolicyRef: terminalSelectedPolicyRef(run.FrozenPolicySelection),
			}, now); err != nil {
				return err
			}
			return nil
		})
	if err != nil {
		return errors.Join(cause, err)
	}
	if pauseWon {
		return w.checkpointAndPause(ctx, committed, *pauseResult)
	}
	if !failureCommitted || committed.State != generated.AssistantRunStateFailed {
		return nil
	}
	_, hookErr := w.runHook(
		context.WithoutCancel(ctx),
		HookOnBlocked,
		committed,
		map[string]any{"reason": strings.TrimSpace(reason)},
	)
	return hookErr
}
