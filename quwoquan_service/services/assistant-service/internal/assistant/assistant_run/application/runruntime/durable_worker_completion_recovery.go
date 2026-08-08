package runruntime

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

type completionBoundaryFacts struct {
	goalRevision               int64
	goalHistory                []GoalRevision
	protectedFactsDigest       string
	goalIndependentFactsDigest string
}

func completionBoundaryFactsFor(run Run) completionBoundaryFacts {
	return completionBoundaryFacts{
		goalRevision:               run.GoalRevision,
		goalHistory:                append([]GoalRevision(nil), run.GoalHistory...),
		protectedFactsDigest:       ProtectedRunFactsDigest(run),
		goalIndependentFactsDigest: goalIndependentProtectedRunFactsDigest(run),
	}
}

func sameCompletionBoundaryFacts(
	run Run,
	expected completionBoundaryFacts,
) bool {
	actualDigest := ProtectedRunFactsDigest(run)
	return expected.protectedFactsDigest != "" && actualDigest != "" &&
		run.GoalRevision == expected.goalRevision &&
		actualDigest == expected.protectedFactsDigest
}

func sameGoalIndependentCompletionBoundaryFacts(
	run Run,
	expected completionBoundaryFacts,
) bool {
	actualDigest := goalIndependentProtectedRunFactsDigest(run)
	return expected.goalIndependentFactsDigest != "" && actualDigest != "" &&
		actualDigest == expected.goalIndependentFactsDigest
}

func goalRevisionPlanItemCommitted(run Run, goalRevision int64) bool {
	wantID := "plan:" + run.RunID + ":goal:" + int64String(goalRevision)
	for _, item := range run.Items {
		if item.ItemID == wantID {
			return goalRevisionPlanItemMatches(run, item, goalRevision)
		}
	}
	return false
}

func goalRevisionPlanItemMatches(
	run Run,
	item RunItem,
	goalRevision int64,
) bool {
	wantGoalDigest := goalChainDigest(run)
	if wantGoalDigest == "" || item.Kind != generated.AssistantRunItemKindPlan ||
		item.Status != generated.AssistantRunItemStatusCompleted ||
		item.TaskID != "task_root" {
		return false
	}
	return exactGoalRevisionPayload(item.Payload["goalRevision"], goalRevision) &&
		exactGoalDigestPayload(item.Payload["goalDigest"], wantGoalDigest)
}

func exactGoalRevisionPayload(value any, want int64) bool {
	switch typed := value.(type) {
	case int:
		return int64(typed) == want
	case int32:
		return int64(typed) == want
	case int64:
		return typed == want
	case float64:
		return typed == float64(want)
	default:
		return false
	}
}

func exactGoalDigestPayload(value any, want string) bool {
	typed, ok := value.(string)
	return ok && typed == want
}

func validateExistingGoalRevisionPlanItem(run Run) error {
	wantID := "plan:" + run.RunID + ":goal:" + int64String(run.GoalRevision)
	found := false
	for _, item := range run.Items {
		if item.ItemID != wantID {
			continue
		}
		if found || !goalRevisionPlanItemMatches(run, item, run.GoalRevision) {
			return ErrJournalCorrupt
		}
		found = true
	}
	return nil
}

func goalHistoryIsContinuous(history []GoalRevision, goalRevision int64) bool {
	if goalRevision < 1 || int64(len(history)) != goalRevision-1 {
		return false
	}
	for index, revision := range history {
		if revision.Revision != int64(index)+2 ||
			strings.TrimSpace(revision.Instruction) == "" || revision.AppliedAt.IsZero() {
			return false
		}
	}
	return true
}

func goalHistoryExtends(
	run Run,
	expected completionBoundaryFacts,
) bool {
	if !goalHistoryIsContinuous(expected.goalHistory, expected.goalRevision) ||
		!goalHistoryIsContinuous(run.GoalHistory, run.GoalRevision) ||
		run.GoalRevision <= expected.goalRevision ||
		len(run.GoalHistory) <= len(expected.goalHistory) {
		return false
	}
	for index := range expected.goalHistory {
		if !reflect.DeepEqual(run.GoalHistory[index], expected.goalHistory[index]) {
			return false
		}
	}
	return true
}

func completionAnswerItemPresent(run Run) bool {
	answerID := completionAnswerItemID(run.RunID)
	for _, item := range run.Items {
		if item.ItemID == answerID {
			return true
		}
	}
	return false
}

// acceptedCompletionPersisted recognizes only the atomic accepted
// verdict/capsule pair. Either half missing or malformed is corruption, never
// an incomplete state that may accept a new goal revision.
func acceptedCompletionPersisted(run Run) (bool, error) {
	rootIndex := run.TaskGraph.taskIndex("task_root")
	if rootIndex < 0 {
		if completionAnswerItemPresent(run) {
			return false, ErrJournalCorrupt
		}
		return false, nil
	}
	if run.TaskGraph.Tasks[rootIndex].Attempt <= 0 {
		if completionAnswerItemPresent(run) {
			return false, ErrJournalCorrupt
		}
		return false, nil
	}
	verdict, found, err := verificationVerdictForCurrentAttempt(run)
	if err != nil {
		return false, err
	}
	answerPresent := completionAnswerItemPresent(run)
	if !found {
		if answerPresent {
			return false, ErrJournalCorrupt
		}
		return false, nil
	}
	if !verdict.Accepted {
		if answerPresent {
			return false, ErrJournalCorrupt
		}
		return false, nil
	}
	if !answerPresent {
		return false, ErrJournalCorrupt
	}
	if _, _, err := completionCapsuleForCurrentAttempt(run); err != nil {
		return false, ErrJournalCorrupt
	}
	return true, nil
}

func guardCompletionBoundary(
	run *Run,
	expected completionBoundaryFacts,
	now time.Time,
) (bool, error) {
	if !goalHistoryIsContinuous(expected.goalHistory, expected.goalRevision) ||
		!goalHistoryIsContinuous(run.GoalHistory, run.GoalRevision) {
		return false, ErrJournalCorrupt
	}
	if err := validateExistingGoalRevisionPlanItem(*run); err != nil {
		return false, err
	}
	acceptedCompletion, err := acceptedCompletionPersisted(*run)
	if err != nil {
		return false, err
	}
	if len(run.PendingSteer) == 0 {
		if sameCompletionBoundaryFacts(*run, expected) {
			return false, nil
		}
		if run.GoalRevision > expected.goalRevision &&
			sameGoalIndependentCompletionBoundaryFacts(*run, expected) &&
			goalHistoryExtends(*run, expected) &&
			goalRevisionPlanItemCommitted(*run, run.GoalRevision) {
			return true, nil
		}
		return false, ErrRevisionConflict
	}
	if acceptedCompletion {
		return false, ErrInvalidTransition
	}
	if !sameCompletionBoundaryFacts(*run, expected) {
		return false, ErrRevisionConflict
	}
	verdict, verdictFound, err := verificationVerdictForCurrentAttempt(*run)
	if err != nil {
		return false, err
	}
	if verdictFound && verdict.Accepted {
		return false, ErrJournalCorrupt
	}
	previousGoalRevision := run.GoalRevision
	run.applyPendingSteer(now)
	if run.GoalRevision == previousGoalRevision {
		return false, ErrRevisionConflict
	}
	if !goalHistoryIsContinuous(run.GoalHistory, run.GoalRevision) {
		return false, ErrJournalCorrupt
	}
	if verdictFound {
		rootIndex := run.TaskGraph.taskIndex("task_root")
		if rootIndex < 0 ||
			run.TaskGraph.Tasks[rootIndex].Status != generated.AssistantTaskStatusRunning {
			return false, ErrJournalCorrupt
		}
		if err := run.TaskGraph.Fail("task_root", "goal_revised", true); err != nil {
			return false, err
		}
		if err := run.TaskGraph.Start("task_root"); err != nil {
			return false, err
		}
		rootIndex = run.TaskGraph.taskIndex("task_root")
		run.TaskGraph.Tasks[rootIndex].Verification = TaskVerification{}
		run.TaskGraph.Tasks[rootIndex].BlockReason = ""
	}
	if err := appendGoalRevisionPlanItem(run, now); err != nil {
		return false, err
	}
	if !goalRevisionPlanItemCommitted(*run, run.GoalRevision) {
		return false, ErrJournalCorrupt
	}
	return true, nil
}

func (w *DurableWorker) applyCompletionBoundary(
	ctx context.Context,
	current Run,
) (Run, bool, error) {
	expected := completionBoundaryFactsFor(current)
	replanned := false
	committed, err := w.commitMutation(ctx, current.RunID, "task_graph_patch", func(
		run *Run,
		now time.Time,
	) error {
		var guardErr error
		replanned, guardErr = guardCompletionBoundary(run, expected, now)
		return guardErr
	})
	return committed, replanned, err
}

func (w *DurableWorker) persistAcceptedCompletion(
	ctx context.Context,
	current Run,
	verdict VerificationVerdict,
	result ExecutionResult,
	availableArtifactRefs []string,
) (Run, VerificationVerdict, durableCompletionCapsule, bool, error) {
	if !verdict.Accepted || len(verdict.Missing) > 0 || len(verdict.Failed) > 0 {
		return Run{}, VerificationVerdict{}, durableCompletionCapsule{}, false, ErrCompletionRejected
	}
	capsule, encoded, digest, err := encodeDurableCompletionCapsule(
		result,
		availableArtifactRefs,
	)
	if err != nil {
		return Run{}, VerificationVerdict{}, durableCompletionCapsule{}, false, err
	}
	itemID, taskAttempt, err := verificationItemIdentity(current)
	if err != nil {
		return Run{}, VerificationVerdict{}, durableCompletionCapsule{}, false, err
	}
	if persisted, found, decodeErr := verificationVerdictForItem(
		current,
		itemID,
		taskAttempt,
	); found || decodeErr != nil {
		if decodeErr != nil || !persisted.Accepted {
			return Run{}, VerificationVerdict{}, durableCompletionCapsule{}, false, ErrJournalCorrupt
		}
		persistedCapsule, persistedDigest, capsuleErr :=
			completionCapsuleForCurrentAttempt(current)
		if capsuleErr != nil || persistedDigest != digest {
			return Run{}, VerificationVerdict{}, durableCompletionCapsule{}, false, ErrJournalCorrupt
		}
		return current, persisted, persistedCapsule, false, nil
	}

	completionBoundary := completionBoundaryFactsFor(current)
	completionReplanned := false
	pauseWon := false
	committed, err := w.commitMutation(ctx, current.RunID, "answer_delta", func(
		run *Run,
		now time.Time,
	) error {
		replanned, boundaryErr := guardCompletionBoundary(
			run,
			completionBoundary,
			now,
		)
		if boundaryErr != nil {
			return boundaryErr
		}
		if replanned {
			completionReplanned = true
			return nil
		}
		if run.PauseRequested {
			pauseWon = true
			return nil
		}
		if run.State != generated.AssistantRunStateExecuting {
			return ErrJournalCorrupt
		}
		if persisted, found, decodeErr := verificationVerdictForItem(
			*run,
			itemID,
			taskAttempt,
		); found || decodeErr != nil {
			if decodeErr != nil || !persisted.Accepted {
				return ErrJournalCorrupt
			}
			_, persistedDigest, capsuleErr :=
				completionCapsuleForCurrentAttempt(*run)
			if capsuleErr != nil || persistedDigest != digest {
				return ErrJournalCorrupt
			}
			return nil
		}
		if err := run.MergeConfirmedSlots(result.ConfirmedSlots, now); err != nil {
			return err
		}
		verdictArtifactRefs := []string{}
		for _, row := range verdict.Evidence {
			verdictArtifactRefs = append(verdictArtifactRefs, row.ArtifactRefs...)
		}
		if err := run.BeginItem(
			itemID,
			generated.AssistantRunItemKindEvidence,
			"task_root",
			verdict.DecisionSummary,
			verificationVerdictJournalPayload(*run, verdict, taskAttempt),
			now,
		); err != nil {
			return err
		}
		if err := run.CompleteItem(
			itemID,
			generated.AssistantRunItemStatusCompleted,
			uniqueSorted(verdictArtifactRefs),
			verdict.DecisionSummary,
			now,
		); err != nil {
			return err
		}
		answerID := completionAnswerItemID(run.RunID)
		if err := run.BeginItem(
			answerID,
			generated.AssistantRunItemKindFinalAnswer,
			"task_root",
			"最终答案",
			map[string]any{
				"text": capsule.AnswerText, "taskAttempt": taskAttempt,
				completionCapsulePayloadKey: encoded,
				completionDigestPayloadKey:  digest,
			},
			now,
		); err != nil {
			return err
		}
		return run.CompleteItem(
			answerID,
			generated.AssistantRunItemStatusCompleted,
			capsule.ArtifactRefs,
			"最终答案",
			now,
		)
	})
	if err != nil {
		return Run{}, VerificationVerdict{}, durableCompletionCapsule{}, false, err
	}
	if completionReplanned {
		return Run{}, VerificationVerdict{}, durableCompletionCapsule{}, false,
			ErrExecutionReplanned
	}
	if pauseWon {
		return committed, VerificationVerdict{}, durableCompletionCapsule{}, true, nil
	}
	authoritative, found, decodeErr := verificationVerdictForCurrentAttempt(committed)
	if decodeErr != nil || !found || !authoritative.Accepted {
		return Run{}, VerificationVerdict{}, durableCompletionCapsule{}, false, ErrJournalCorrupt
	}
	authoritativeCapsule, _, capsuleErr := completionCapsuleForCurrentAttempt(committed)
	if capsuleErr != nil {
		return Run{}, VerificationVerdict{}, durableCompletionCapsule{}, false, capsuleErr
	}
	return committed, authoritative, authoritativeCapsule, false, nil
}

// recoverPersistedCompletion is the sole claim-time recovery entry point for
// both accepted and rejected authoritative verdicts. It returns handled=false
// only when an executing Run has no durable verdict and may invoke the executor.
func (w *DurableWorker) recoverPersistedCompletion(
	ctx context.Context,
	current Run,
) (bool, error) {
	if len(current.PendingSteer) > 0 {
		prepared, replanned, err := w.applyCompletionBoundary(ctx, current)
		if err != nil {
			if completionIntegrityFailure(err) {
				return true, w.failCompletionRecovery(
					ctx,
					current,
					"completion_boundary_corrupt",
					err,
				)
			}
			return true, err
		}
		if replanned {
			if prepared.PauseRequested {
				return true, w.checkpointAndPause(
					ctx,
					prepared,
					ExecutionResult{},
				)
			}
			return true, nil
		}
		current = prepared
	}
	if current.PauseRequested {
		acceptedCompletion, pairErr := acceptedCompletionPersisted(current)
		if pairErr != nil || acceptedCompletion {
			if pairErr == nil {
				pairErr = ErrJournalCorrupt
			}
			return true, w.failCompletionRecovery(
				ctx,
				current,
				"completion_capsule_corrupt",
				pairErr,
			)
		}
		return true, w.checkpointAndPause(ctx, current, ExecutionResult{})
	}
	verdict, found, err := verificationVerdictForCurrentAttempt(current)
	if err != nil {
		return true, w.failCompletionRecovery(ctx, current, "verification_journal_corrupt", err)
	}
	if !found {
		if current.State == generated.AssistantRunStateExecuting {
			return false, nil
		}
		return true, w.failCompletionRecovery(
			ctx,
			current,
			"completion_capsule_missing",
			ErrJournalCorrupt,
		)
	}
	if !verdict.Accepted {
		if current.State != generated.AssistantRunStateExecuting {
			return true, w.failCompletionRecovery(
				ctx, current, "verification_state_corrupt", ErrJournalCorrupt,
			)
		}
		repairRun, repaired, pauseWon, terminalReason, repairErr :=
			w.tryVerificationRepair(ctx, current, verdict)
		if repairErr != nil {
			return true, repairErr
		}
		if repaired {
			return true, nil
		}
		if pauseWon {
			return true, w.checkpointAndPause(ctx, repairRun, ExecutionResult{})
		}
		return true, w.failRunAtCompletion(
			ctx,
			current,
			terminalReason,
			ErrCompletionRejected,
			ExecutionResult{},
		)
	}
	capsule, _, err := completionCapsuleForCurrentAttempt(current)
	if err != nil {
		return true, w.failCompletionRecovery(ctx, current, "completion_capsule_corrupt", err)
	}
	return true, w.resumeAcceptedCompletion(ctx, current, verdict, capsule)
}

func (w *DurableWorker) resumeAcceptedCompletion(
	ctx context.Context,
	current Run,
	verdict VerificationVerdict,
	capsule durableCompletionCapsule,
) error {
	for step := 0; step < 8; step++ {
		if err := validateAcceptedCompletionFacts(current, verdict, capsule); err != nil {
			return w.failCompletionRecovery(ctx, current, "completion_capsule_corrupt", err)
		}
		switch current.State {
		case generated.AssistantRunStateExecuting:
			var err error
			current, err = w.commitMutation(ctx, current.RunID, "process_commit", func(
				run *Run,
				now time.Time,
			) error {
				if err := validateAcceptedCompletionFacts(*run, verdict, capsule); err != nil {
					return err
				}
				if err := run.TaskGraph.Complete(
					"task_root",
					capsule.ArtifactRefs,
					TaskVerification{
						Requirements: run.DefinitionOfDone.VerificationRequirements,
						EvidenceRefs: capsule.ArtifactRefs,
						Passed:       true, Summary: verdict.DecisionSummary,
					},
				); err != nil {
					return err
				}
				rootIndex := run.TaskGraph.taskIndex("task_root")
				if rootIndex < 0 {
					return ErrInvalidTaskGraph
				}
				run.TaskGraph.Tasks[rootIndex].BlockReason = ""
				return run.Transition(generated.AssistantRunStateObserving, "", now)
			})
			if err != nil {
				return w.handleCompletionRecoveryError(ctx, current, err)
			}
		case generated.AssistantRunStateObserving:
			if !current.TaskGraph.AllCompleted() {
				return w.failCompletionRecovery(
					ctx, current, "completion_task_graph_corrupt", ErrJournalCorrupt,
				)
			}
			var err error
			current, err = w.transitionCompletionStage(
				ctx, current, generated.AssistantRunStateReflecting,
			)
			if err != nil {
				return w.handleCompletionRecoveryError(ctx, current, err)
			}
		case generated.AssistantRunStateReflecting:
			var err error
			current, err = w.transitionCompletionStage(
				ctx, current, generated.AssistantRunStateSynthesizing,
			)
			if err != nil {
				return w.handleCompletionRecoveryError(ctx, current, err)
			}
		case generated.AssistantRunStateSynthesizing:
			var err error
			current, err = w.persistPresentation(ctx, current, capsule.Presentation)
			if err != nil {
				return w.handleCompletionRecoveryError(ctx, current, err)
			}
			current, err = w.transitionCompletionStage(
				ctx, current, generated.AssistantRunStateVerifying,
			)
			if err != nil {
				return w.handleCompletionRecoveryError(ctx, current, err)
			}
		case generated.AssistantRunStateVerifying:
			_, err := w.commitAcceptedTerminal(ctx, current, verdict, capsule)
			if err != nil {
				return w.handleCompletionRecoveryError(ctx, current, err)
			}
			return nil
		case generated.AssistantRunStateCompleted:
			if !sameCompletionTerminal(current, capsule) {
				return ErrJournalCorrupt
			}
			return nil
		case generated.AssistantRunStateFailed, generated.AssistantRunStateCancelled,
			generated.AssistantRunStatePaused:
			return nil
		default:
			return w.failCompletionRecovery(
				ctx, current, "completion_state_corrupt", ErrJournalCorrupt,
			)
		}
	}
	return w.failCompletionRecovery(ctx, current, "completion_resume_exhausted", ErrJournalCorrupt)
}

func (w *DurableWorker) transitionCompletionStage(
	ctx context.Context,
	current Run,
	next generated.AssistantRunState,
) (Run, error) {
	return w.commitMutation(ctx, current.RunID, "run_state_changed", func(
		run *Run,
		now time.Time,
	) error {
		return run.Transition(next, "", now)
	})
}

func (w *DurableWorker) commitAcceptedTerminal(
	ctx context.Context,
	current Run,
	verdict VerificationVerdict,
	capsule durableCompletionCapsule,
) (Run, error) {
	return w.commitMutation(ctx, current.RunID, "completed", func(
		run *Run,
		now time.Time,
	) error {
		if err := validateAcceptedCompletionFacts(*run, verdict, capsule); err != nil {
			return err
		}
		if len(capsule.Presentation) > 0 &&
			(!samePresentationContent(run.PresentationDocument, capsule.Presentation) ||
				!presentationDocumentCommitted(run.PresentationDocument)) {
			return ErrJournalCorrupt
		}
		if err := run.AcceptVerification(verdict, now); err != nil {
			return err
		}
		return run.SetTerminalSnapshot(assistantmodel.AssistantRunTerminalSnapshot{
			AnswerText: capsule.AnswerText, Processes: capsule.Processes,
			SelectedPolicyRef: terminalSelectedPolicyRef(run.FrozenPolicySelection),
		}, now)
	})
}

func validateAcceptedCompletionFacts(
	run Run,
	verdict VerificationVerdict,
	capsule durableCompletionCapsule,
) error {
	if run.PauseRequested ||
		!goalHistoryIsContinuous(run.GoalHistory, run.GoalRevision) {
		return ErrJournalCorrupt
	}
	persisted, found, err := verificationVerdictForCurrentAttempt(run)
	if err != nil || !found || !persisted.Accepted ||
		len(persisted.Missing) > 0 || len(persisted.Failed) > 0 ||
		!reflect.DeepEqual(persisted, verdict) {
		return ErrJournalCorrupt
	}
	persistedCapsule, _, err := completionCapsuleForCurrentAttempt(run)
	if err != nil || !reflect.DeepEqual(persistedCapsule, capsule) {
		return ErrJournalCorrupt
	}
	return nil
}

func sameCompletionTerminal(run Run, capsule durableCompletionCapsule) bool {
	if run.TerminalSnapshot == nil || run.TerminalSnapshot.Failure != nil {
		return false
	}
	want := assistantmodel.AssistantRunTerminalSnapshot{
		AnswerText: capsule.AnswerText, Processes: capsule.Processes,
		SelectedPolicyRef: terminalSelectedPolicyRef(run.FrozenPolicySelection),
	}
	return reflect.DeepEqual(*run.TerminalSnapshot, want)
}

func completionIntegrityFailure(err error) bool {
	return errors.Is(err, ErrUnsafePayload) || errors.Is(err, ErrJournalCorrupt) ||
		errors.Is(err, ErrInvalidRun) || errors.Is(err, ErrInvalidTransition) ||
		errors.Is(err, ErrInvalidTaskGraph) || errors.Is(err, ErrTaskNotReady) ||
		errors.Is(err, ErrItemStateConflict) || errors.Is(err, ErrCompletionRejected)
}

func (w *DurableWorker) handleCompletionRecoveryError(
	ctx context.Context,
	current Run,
	err error,
) error {
	if !completionIntegrityFailure(err) {
		return err
	}
	return w.failCompletionRecovery(ctx, current, "completion_recovery_corrupt", err)
}

func (w *DurableWorker) failCompletionRecovery(
	ctx context.Context,
	current Run,
	reason string,
	cause error,
) error {
	if terminalRunState(current.State) {
		return cause
	}
	return w.failRun(ctx, current, reason, cause)
}
