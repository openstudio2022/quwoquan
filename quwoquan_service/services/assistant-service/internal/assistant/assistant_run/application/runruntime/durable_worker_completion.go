package runruntime

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

func (w *DurableWorker) completeRun(
	ctx context.Context,
	current Run,
	result ExecutionResult,
) error {
	availableArtifactRefs := uniqueSorted(append(
		append([]string{}, result.ArtifactRefs...),
		result.EvidenceRefs...,
	))
	verdict := w.hooks.VerifyCompletion(ctx, current.DefinitionOfDone, VerificationInput{
		Run:                   current,
		Result:                result,
		AvailableArtifactRefs: availableArtifactRefs,
	})
	if !verdict.Accepted {
		current, _ = w.persistVerificationVerdict(ctx, current, verdict)
		return w.failRun(
			ctx,
			current,
			"verification_failed",
			ErrCompletionRejected,
		)
	}
	completionHook, err := w.runHook(ctx, HookBeforeComplete, current, map[string]any{
		"verification": verificationVerdictPayload(verdict),
	})
	if err != nil {
		return w.failRun(ctx, current, "before_complete_hook_failed", err)
	}
	switch completionHook.Decision {
	case HookBlock:
		return w.failRun(
			ctx,
			current,
			"before_complete_hook_blocked",
			ErrCompletionRejected,
		)
	case HookRequireConfirmation:
		continuationToken := assistantRunContinuationToken(
			current.RunID,
			completionHook.ConfirmationRef,
		)
		if _, valid := pendingDeviceActionKind(
			result.Presentation,
			completionHook.ConfirmationRef,
			continuationToken,
		); !valid {
			return w.failRun(
				ctx,
				current,
				"before_complete_confirmation_invalid",
				ErrCompletionRejected,
			)
		}
		result.WaitingState = generated.AssistantRunStateWaitingApproval
		result.WaitReason = "before_complete_confirmation_required"
		result.PendingApprovalRef = completionHook.ConfirmationRef
		return w.waitRun(ctx, current, result)
	}

	run, err := w.commitMutation(ctx, current.RunID, "process_commit", func(
		run *Run,
		now time.Time,
	) error {
		if err := run.MergeConfirmedSlots(result.ConfirmedSlots, now); err != nil {
			return err
		}
		if err := run.Transition(generated.AssistantRunStateObserving, "", now); err != nil {
			return err
		}
		return run.TaskGraph.Complete(
			"task_root",
			availableArtifactRefs,
			TaskVerification{
				Requirements: run.DefinitionOfDone.VerificationRequirements,
				EvidenceRefs: availableArtifactRefs,
				Passed:       verdict.Accepted,
				Summary:      verdict.DecisionSummary,
			},
		)
	})
	if err != nil {
		return err
	}
	run, err = w.commitMutation(ctx, run.RunID, "run_state_changed", func(
		run *Run,
		now time.Time,
	) error {
		if err := run.Transition(generated.AssistantRunStateReflecting, "", now); err != nil {
			return err
		}
		return run.Transition(generated.AssistantRunStateSynthesizing, "", now)
	})
	if err != nil {
		return err
	}
	run, err = w.commitMutation(ctx, run.RunID, "answer_delta", func(
		run *Run,
		now time.Time,
	) error {
		if err := run.BeginItem(
			"answer:"+run.RunID,
			generated.AssistantRunItemKindFinalAnswer,
			"task_root",
			"最终答案",
			map[string]any{"text": strings.TrimSpace(result.AnswerText)},
			now,
		); err != nil {
			return err
		}
		return run.CompleteItem(
			"answer:"+run.RunID,
			generated.AssistantRunItemStatusCompleted,
			availableArtifactRefs,
			"最终答案",
			now,
		)
	})
	if err != nil {
		return err
	}
	run, err = w.persistPresentation(ctx, run, result.Presentation)
	if err != nil {
		return err
	}
	run, err = w.commitMutation(ctx, run.RunID, "run_state_changed", func(
		run *Run,
		now time.Time,
	) error {
		return run.Transition(generated.AssistantRunStateVerifying, "", now)
	})
	if err != nil {
		return err
	}
	run, err = w.persistVerificationVerdict(ctx, run, verdict)
	if err != nil {
		return err
	}
	_, err = w.commitMutation(ctx, run.RunID, "completed", func(
		run *Run,
		now time.Time,
	) error {
		if err := run.AcceptVerification(verdict, now); err != nil {
			return err
		}
		snapshot := assistantmodel.AssistantRunTerminalSnapshot{
			AnswerText:        strings.TrimSpace(result.AnswerText),
			Processes:         result.Processes,
			SelectedPolicyRef: terminalSelectedPolicyRef(run.FrozenPolicySelection),
		}
		return run.SetTerminalSnapshot(snapshot, now)
	})
	if err != nil {
		return err
	}
	return w.runStopHook(ctx, run.RunID, "completed")
}

func (w *DurableWorker) persistVerificationVerdict(
	ctx context.Context,
	current Run,
	verdict VerificationVerdict,
) (Run, error) {
	itemID := "verification:" + current.RunID + ":goal:" +
		fmt.Sprint(current.GoalRevision)
	for _, item := range current.Items {
		if item.ItemID == itemID {
			return current, nil
		}
	}
	artifactRefs := []string{}
	for _, item := range verdict.Evidence {
		artifactRefs = append(artifactRefs, item.ArtifactRefs...)
	}
	return w.commitMutation(ctx, current.RunID, "process_commit", func(
		run *Run,
		now time.Time,
	) error {
		if err := run.BeginItem(
			itemID,
			generated.AssistantRunItemKindEvidence,
			"task_root",
			verdict.DecisionSummary,
			verificationVerdictPayload(verdict),
			now,
		); err != nil {
			return err
		}
		return run.CompleteItem(
			itemID,
			generated.AssistantRunItemStatusCompleted,
			uniqueSorted(artifactRefs),
			verdict.DecisionSummary,
			now,
		)
	})
}

func verificationVerdictPayload(verdict VerificationVerdict) map[string]any {
	evidence := make([]map[string]any, 0, len(verdict.Evidence))
	for _, item := range verdict.Evidence {
		evidence = append(evidence, map[string]any{
			"requirement":   item.Requirement,
			"verifierId":    item.VerifierID,
			"passed":        item.Passed,
			"artifactRefs":  append([]string{}, item.ArtifactRefs...),
			"summary":       item.Summary,
			"fixSuggestion": item.FixSuggestion,
		})
	}
	return map[string]any{
		"accepted":        verdict.Accepted,
		"evidence":        evidence,
		"missing":         append([]string{}, verdict.Missing...),
		"failed":          append([]string{}, verdict.Failed...),
		"decisionSummary": verdict.DecisionSummary,
	}
}

func (w *DurableWorker) runHook(
	ctx context.Context,
	phase HookPhase,
	run Run,
	data map[string]any,
) (HookResult, error) {
	return w.hooks.Run(ctx, HookInput{
		Phase:                phase,
		Run:                  run,
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
		GoalRevision              int64            `json:"goalRevision"`
		DefinitionOfDone          DefinitionOfDone `json:"definitionOfDone"`
	}{
		RunID:                     run.RunID,
		UserID:                    run.UserID,
		SkillPackageReleaseDigest: run.SkillPackageReleaseDigest,
		GoalRevision:              run.GoalRevision,
		DefinitionOfDone:          cloneDefinition(run.DefinitionOfDone),
	})
	if err != nil {
		return ""
	}
	return "sha256:" + digest
}

func (w *DurableWorker) runStopHook(
	ctx context.Context,
	runID string,
	outcome string,
) error {
	run, err := w.repository.Load(context.WithoutCancel(ctx), runID)
	if err != nil {
		return err
	}
	_, err = w.runHook(context.WithoutCancel(ctx), HookOnStop, run, map[string]any{
		"outcome": strings.TrimSpace(outcome),
	})
	return err
}

func (w *DurableWorker) failRun(
	ctx context.Context,
	current Run,
	reason string,
	cause error,
) error {
	blockedHook, hookErr := w.runHook(
		context.WithoutCancel(ctx),
		HookOnBlocked,
		current,
		map[string]any{"reason": strings.TrimSpace(reason)},
	)
	if blockedHook.Reason != "" {
		reason = strings.TrimSpace(reason) + ":" + blockedHook.Reason
	}
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
	failed, err := w.commitMutation(ctx, current.RunID, "failed", func(
		run *Run,
		now time.Time,
	) error {
		if terminalRunState(run.State) {
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
		return run.SetTerminalSnapshot(assistantmodel.AssistantRunTerminalSnapshot{
			AnswerText:        "",
			Processes:         []assistantmodel.AssistantRunVisibleProcess{},
			Failure:           &failure,
			SelectedPolicyRef: terminalSelectedPolicyRef(run.FrozenPolicySelection),
		}, now)
	})
	if err != nil {
		return errors.Join(cause, hookErr, err)
	}
	stopErr := w.runStopHook(context.WithoutCancel(ctx), failed.RunID, "failed")
	return errors.Join(hookErr, stopErr)
}
