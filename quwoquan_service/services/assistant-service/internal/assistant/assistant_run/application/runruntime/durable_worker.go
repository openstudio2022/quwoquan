package runruntime

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
)

type ExecutionRequest struct {
	RunID                     string
	UserID                    string
	SessionID                 string
	Goal                      string
	RequestedSkillID          string
	RequestedDomainID         string
	SkillPackageID            string
	SkillPackageReleaseDigest string
	FrozenPolicySelection     FrozenPolicySelection
	RequestContext            RequestContext
	Trigger                   map[string]any
	ReasoningProfile          generated.AssistantReasoningProfile
	DefinitionOfDone          DefinitionOfDone
	GoalHistory               []GoalRevision
	Checkpoint                *Checkpoint
	ContextSnapshot           map[string]any
	SurfaceCapabilities       map[string]any
	SessionPreferenceFacts    []preferencemodel.Snapshot
	LongTermPreferenceFacts   []preferencemodel.Snapshot
	IdempotencyPrefix         string
	CreatedAt                 time.Time
}

type ExecutionItemUpdate struct {
	ItemID       string
	Kind         generated.AssistantRunItemKind
	Status       generated.AssistantRunItemStatus
	TaskID       string
	Summary      string
	Payload      map[string]any
	ArtifactRefs []string
}

type ExecutionResult struct {
	AnswerText          string
	Processes           []map[string]any
	ArtifactRefs        []string
	EvidenceRefs        []string
	Presentation        map[string]any
	Verified            bool
	VerificationSummary string
	WaitingState        generated.AssistantRunState
	WaitReason          string
	PendingApprovalRef  string
}

// ExecutionFailure preserves the public, metadata-derived runtime failure
// across the AgentLoop -> durable AssistantRun boundary without persisting
// provider-specific diagnostics or credentials.
type ExecutionFailure struct {
	Code   string
	Origin string
	Kind   string
	Nature string
}

func (failure *ExecutionFailure) Error() string {
	if failure == nil || strings.TrimSpace(failure.Code) == "" {
		return "assistant run execution failed"
	}
	return strings.TrimSpace(failure.Code)
}

type RunExecutor interface {
	Execute(
		context.Context,
		ExecutionRequest,
		func(ExecutionItemUpdate) error,
	) (ExecutionResult, error)
}

type DurableWorker struct {
	repository        WorkerRepository
	queue             WorkQueue
	executor          RunExecutor
	workerID          string
	claimTTL          time.Duration
	heartbeatInterval time.Duration
	pollInterval      time.Duration
	now               func() time.Time
}

func NewDurableWorker(
	repository WorkerRepository,
	queue WorkQueue,
	executor RunExecutor,
	workerID string,
) *DurableWorker {
	if repository == nil || queue == nil || executor == nil ||
		strings.TrimSpace(workerID) == "" {
		panic("assistant durable worker dependencies are required")
	}
	return &DurableWorker{
		repository:        repository,
		queue:             queue,
		executor:          executor,
		workerID:          strings.TrimSpace(workerID),
		claimTTL:          15 * time.Second,
		heartbeatInterval: 3 * time.Second,
		pollInterval:      250 * time.Millisecond,
		now:               time.Now,
	}
}

func (w *DurableWorker) Run(ctx context.Context) {
	if w == nil {
		return
	}
	timer := time.NewTimer(0)
	defer timer.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-timer.C:
			worked, err := w.ProcessNext(ctx)
			delay := w.pollInterval
			if worked && err == nil {
				delay = 0
			}
			timer.Reset(delay)
		}
	}
}

func (w *DurableWorker) ProcessNext(
	ctx context.Context,
) (worked bool, resultErr error) {
	claim, err := w.queue.ClaimNext(ctx, w.workerID, w.claimTTL)
	if errors.Is(err, ErrNoWork) {
		return false, nil
	}
	if err != nil {
		if errors.Is(err, ErrLeaseConflict) {
			observeLeaseContention("claim")
		}
		return false, err
	}
	startedAt := w.now()
	defer func() {
		observeWorkerClaim(claim, startedAt, resultErr)
	}()
	processCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	var claimMu sync.Mutex
	activeClaim := claim
	heartbeatErr := make(chan error, 1)
	go func() {
		ticker := time.NewTicker(w.heartbeatInterval)
		defer ticker.Stop()
		for {
			select {
			case <-processCtx.Done():
				return
			case <-ticker.C:
				claimMu.Lock()
				current := activeClaim
				claimMu.Unlock()
				next, heartbeat := w.queue.HeartbeatClaim(
					processCtx,
					current,
					w.claimTTL,
				)
				if heartbeat != nil {
					if errors.Is(heartbeat, ErrLeaseConflict) {
						observeLeaseContention("heartbeat")
					}
					select {
					case heartbeatErr <- heartbeat:
					default:
					}
					cancel()
					return
				}
				claimMu.Lock()
				activeClaim = next
				claimMu.Unlock()
			}
		}
	}()

	processErr := w.processClaim(processCtx, claim.RunID)
	if errors.Is(processErr, ErrExecutionFenced) {
		observeLeaseContention("fenced")
	}
	cancel()
	select {
	case err := <-heartbeatErr:
		if processErr == nil {
			processErr = err
		}
	default:
	}
	claimMu.Lock()
	finalClaim := activeClaim
	claimMu.Unlock()

	run, loadErr := w.repository.Load(context.WithoutCancel(ctx), claim.RunID)
	if loadErr != nil && processErr == nil {
		processErr = loadErr
	}
	reschedule := loadErr == nil && queueRunnableRun(run)
	if processErr != nil && !errors.Is(processErr, context.Canceled) {
		reschedule = reschedule && !terminalRunState(run.State)
	}
	completeErr := w.queue.CompleteClaim(
		context.WithoutCancel(ctx),
		finalClaim,
		reschedule,
		w.now().UTC().Add(w.pollInterval),
	)
	if errors.Is(completeErr, ErrLeaseConflict) {
		observeLeaseContention("complete")
	}
	if completeErr != nil && !errors.Is(completeErr, ErrLeaseConflict) {
		return true, errors.Join(processErr, completeErr)
	}
	return true, processErr
}

func (w *DurableWorker) processClaim(ctx context.Context, runID string) error {
	run, err := w.repository.Load(ctx, runID)
	if err != nil {
		return err
	}
	observeCheckpointAge(run.Checkpoint, w.now())
	if terminalRunState(run.State) || !queueRunnableRun(run) {
		return nil
	}
	if run.State == generated.AssistantRunStateAccepted {
		run, err = w.commitMutation(ctx, run.RunID, "run_state_changed", func(
			run *Run,
			now time.Time,
		) error {
			return run.Transition(generated.AssistantRunStateOrienting, "", now)
		})
		if err != nil {
			return err
		}
	}
	if run.State == generated.AssistantRunStateOrienting {
		run, err = w.commitMutation(ctx, run.RunID, "task_graph_patch", func(
			run *Run,
			now time.Time,
		) error {
			if err := run.Transition(generated.AssistantRunStatePlanning, "", now); err != nil {
				return err
			}
			if err := run.TaskGraph.Start("task_root"); err != nil {
				return err
			}
			return run.BeginItem(
				"plan:"+run.RunID,
				generated.AssistantRunItemKindPlan,
				"task_root",
				"执行计划已冻结",
				map[string]any{"goalRevision": run.GoalRevision},
				now,
			)
		})
		if err != nil {
			return err
		}
		run, err = w.commitMutation(ctx, run.RunID, "process_commit", func(
			run *Run,
			now time.Time,
		) error {
			return run.CompleteItem(
				"plan:"+run.RunID,
				generated.AssistantRunItemStatusCompleted,
				nil,
				"执行计划已冻结",
				now,
			)
		})
		if err != nil {
			return err
		}
	}
	if run.State == generated.AssistantRunStatePlanning {
		run, err = w.commitMutation(ctx, run.RunID, "run_state_changed", func(
			run *Run,
			now time.Time,
		) error {
			if err := run.ApplySafeBoundary(now); err != nil {
				return err
			}
			if run.State == generated.AssistantRunStatePaused {
				return nil
			}
			return run.Transition(generated.AssistantRunStateExecuting, "", now)
		})
		if err != nil || run.State == generated.AssistantRunStatePaused {
			return err
		}
	}
	if run.State == generated.AssistantRunStateCheckpointing {
		run, err = w.commitMutation(ctx, run.RunID, "run_state_changed", func(
			run *Run,
			now time.Time,
		) error {
			if err := run.ApplySafeBoundary(now); err != nil {
				return err
			}
			if run.State == generated.AssistantRunStatePaused {
				return nil
			}
			return run.Transition(generated.AssistantRunStateExecuting, "", now)
		})
		if err != nil || run.State == generated.AssistantRunStatePaused {
			return err
		}
	}
	if run.State != generated.AssistantRunStateExecuting {
		return nil
	}

	executionCtx, cancelExecution := context.WithCancel(ctx)
	defer cancelExecution()
	controlDone := make(chan struct{})
	go w.monitorRunControl(executionCtx, run.RunID, cancelExecution, controlDone)
	result, executionErr := w.executor.Execute(
		executionCtx,
		executionRequest(run),
		func(update ExecutionItemUpdate) error {
			return w.persistExecutionUpdate(executionCtx, run.RunID, update)
		},
	)
	close(controlDone)
	if executionErr != nil {
		if errors.Is(executionErr, ErrExecutionCancelled) {
			return w.awaitCoordinatedCancellation(
				context.WithoutCancel(ctx),
				run.RunID,
			)
		}
		current, loadErr := w.repository.Load(context.WithoutCancel(ctx), run.RunID)
		if loadErr != nil {
			return errors.Join(executionErr, loadErr)
		}
		if terminalRunState(current.State) {
			return nil
		}
		if current.PauseRequested {
			return w.checkpointAndPause(context.WithoutCancel(ctx), current)
		}
		if errors.Is(executionErr, context.Canceled) && ctx.Err() != nil {
			return executionErr
		}
		return w.failRun(
			context.WithoutCancel(ctx),
			current,
			"executor_failed",
			executionErr,
		)
	}
	current, err := w.repository.Load(ctx, run.RunID)
	if err != nil {
		return err
	}
	if terminalRunState(current.State) {
		return nil
	}
	if current.PauseRequested {
		return w.checkpointAndPause(ctx, current)
	}
	if result.WaitingState != "" {
		return w.waitRun(ctx, current, result)
	}
	return w.completeRun(ctx, current, result)
}

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
	cancel context.CancelFunc,
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
				cancel()
				return
			}
			if terminalRunState(run.State) || run.PauseRequested ||
				run.State == generated.AssistantRunStatePaused {
				cancel()
				return
			}
		}
	}
}

func (w *DurableWorker) persistExecutionUpdate(
	ctx context.Context,
	runID string,
	update ExecutionItemUpdate,
) error {
	kind := "process_append"
	_, err := w.commitMutation(ctx, runID, kind, func(run *Run, now time.Time) error {
		switch update.Status {
		case generated.AssistantRunItemStatusStarted:
			return run.BeginItem(
				update.ItemID,
				update.Kind,
				update.TaskID,
				update.Summary,
				update.Payload,
				now,
			)
		case generated.AssistantRunItemStatusCompleted,
			generated.AssistantRunItemStatusFailed,
			generated.AssistantRunItemStatusCancelled:
			return run.CompleteItem(
				update.ItemID,
				update.Status,
				update.ArtifactRefs,
				update.Summary,
				now,
			)
		default:
			return ErrItemStateConflict
		}
	})
	return err
}

func (w *DurableWorker) checkpointAndPause(
	ctx context.Context,
	current Run,
) error {
	_, err := w.commitMutation(ctx, current.RunID, "checkpoint_committed", func(
		run *Run,
		now time.Time,
	) error {
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
		return run.ApplySafeBoundary(now)
	})
	return err
}

func (w *DurableWorker) waitRun(
	ctx context.Context,
	current Run,
	result ExecutionResult,
) error {
	var err error
	current, err = w.persistPresentation(ctx, current, result.Presentation)
	if err != nil {
		return err
	}
	_, err = w.commitMutation(ctx, current.RunID, "checkpoint_committed", func(
		run *Run,
		now time.Time,
	) error {
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
	return err
}

func (w *DurableWorker) persistPresentation(
	ctx context.Context,
	current Run,
	presentation map[string]any,
) (Run, error) {
	if len(presentation) == 0 {
		return current, nil
	}
	nextRevision := int64(1)
	if revision, ok := presentationRevision(current.PresentationDocument["revision"]); ok {
		nextRevision = revision + 1
	}
	document := cloneMap(presentation)
	document["revision"] = nextRevision
	document["committedAt"] = ""
	run, err := w.commitMutation(ctx, current.RunID, "presentation_snapshot", func(
		run *Run,
		now time.Time,
	) error {
		return run.SetPresentationDocument(document, now)
	})
	observePresentationProjection("snapshot", err)
	if err != nil {
		return Run{}, err
	}
	committed, err := w.commitMutation(ctx, run.RunID, "presentation_commit", func(
		run *Run,
		now time.Time,
	) error {
		return run.CommitPresentation(now)
	})
	observePresentationProjection("commit", err)
	return committed, err
}

func (w *DurableWorker) completeRun(
	ctx context.Context,
	current Run,
	result ExecutionResult,
) error {
	run, err := w.commitMutation(ctx, current.RunID, "process_commit", func(
		run *Run,
		now time.Time,
	) error {
		if err := run.Transition(generated.AssistantRunStateObserving, "", now); err != nil {
			return err
		}
		return run.TaskGraph.Complete(
			"task_root",
			result.ArtifactRefs,
			TaskVerification{
				Requirements: run.DefinitionOfDone.VerificationRequirements,
				EvidenceRefs: result.EvidenceRefs,
				Passed:       result.Verified,
				Summary:      result.VerificationSummary,
			},
		)
	})
	if err != nil {
		if errors.Is(err, ErrCompletionRejected) {
			return w.failRun(ctx, current, "verification_failed", err)
		}
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
			result.ArtifactRefs,
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
	if !result.Verified {
		return w.failRun(ctx, run, "verification_failed", ErrCompletionRejected)
	}
	_, err = w.commitMutation(ctx, run.RunID, "completed", func(
		run *Run,
		now time.Time,
	) error {
		verdict := VerificationVerdict{
			Accepted: true,
			Evidence: []VerificationEvidence{{
				Requirement:  strings.Join(run.DefinitionOfDone.VerificationRequirements, ","),
				Passed:       true,
				EvidenceRefs: result.EvidenceRefs,
				Summary:      result.VerificationSummary,
			}},
			DecisionSummary: result.VerificationSummary,
		}
		if err := run.AcceptVerification(verdict, now); err != nil {
			return err
		}
		snapshot := map[string]any{
			"answerText": strings.TrimSpace(result.AnswerText),
			"processes":  result.Processes,
		}
		if run.FrozenPolicySelection.PolicyID != "" {
			snapshot["selectedPolicyRef"] = map[string]any{
				"policyId":      run.FrozenPolicySelection.PolicyID,
				"releaseDigest": run.FrozenPolicySelection.ReleaseDigest,
				"cohort":        run.FrozenPolicySelection.Cohort,
			}
		}
		return run.SetTerminalSnapshot(snapshot, now)
	})
	return err
}

func (w *DurableWorker) failRun(
	ctx context.Context,
	current Run,
	reason string,
	cause error,
) error {
	failurePayload := map[string]any{
		"code":   "ASSISTANT.SYSTEM.run_execution_failed",
		"origin": "system",
		"kind":   "internal",
		"nature": "transient",
	}
	var executionFailure *ExecutionFailure
	if errors.As(cause, &executionFailure) {
		if value := strings.TrimSpace(executionFailure.Code); value != "" {
			failurePayload["code"] = value
		}
		if value := strings.TrimSpace(executionFailure.Origin); value != "" {
			failurePayload["origin"] = value
		}
		if value := strings.TrimSpace(executionFailure.Kind); value != "" {
			failurePayload["kind"] = value
		}
		if value := strings.TrimSpace(executionFailure.Nature); value != "" {
			failurePayload["nature"] = value
		}
	}
	_, err := w.commitMutation(ctx, current.RunID, "failed", func(
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
		return run.SetTerminalSnapshot(map[string]any{
			"answerText": "",
			"processes":  []map[string]any{},
			"failure":    failurePayload,
		}, now)
	})
	if err != nil {
		return errors.Join(cause, err)
	}
	return nil
}

func (w *DurableWorker) commitMutation(
	ctx context.Context,
	runID string,
	eventKind string,
	change func(*Run, time.Time) error,
) (Run, error) {
	for attempt := 0; attempt < 4; attempt++ {
		run, err := w.repository.Load(ctx, runID)
		if err != nil {
			return Run{}, err
		}
		if terminalRunState(run.State) {
			return run, nil
		}
		expectedRevision := run.Revision
		if err := change(&run, w.now().UTC()); err != nil {
			return Run{}, err
		}
		if run.Revision == expectedRevision {
			return run, nil
		}
		run.JournalSequence++
		event := JournalEvent{
			EventID:   run.RunID + ":" + int64String(run.JournalSequence),
			RunID:     run.RunID,
			Sequence:  run.JournalSequence,
			Revision:  run.Revision,
			Kind:      strings.TrimSpace(eventKind),
			Payload:   mutationPayload(run, eventKind),
			CreatedAt: w.now().UTC(),
		}
		if err := w.repository.Commit(
			ctx,
			expectedRevision,
			run,
			[]JournalEvent{event},
			nil,
		); err == nil {
			return run, nil
		} else if !errors.Is(err, ErrRevisionConflict) {
			return Run{}, err
		}
	}
	return Run{}, ErrRevisionConflict
}

func executionRequest(run Run) ExecutionRequest {
	var checkpoint *Checkpoint
	if run.Checkpoint != nil {
		cloned := *run.Checkpoint
		checkpoint = &cloned
	}
	return ExecutionRequest{
		RunID:                     run.RunID,
		UserID:                    run.UserID,
		SessionID:                 run.SessionID,
		Goal:                      run.InputText,
		RequestedSkillID:          run.RequestedSkillID,
		RequestedDomainID:         run.RequestedDomainID,
		SkillPackageID:            run.SkillPackageID,
		SkillPackageReleaseDigest: run.SkillPackageReleaseDigest,
		FrozenPolicySelection:     clonePolicySelection(run.FrozenPolicySelection),
		RequestContext:            normalizeRequestContext(run.RequestContext),
		Trigger:                   cloneMap(run.Trigger),
		ReasoningProfile:          run.ReasoningProfile,
		DefinitionOfDone:          cloneDefinition(run.DefinitionOfDone),
		GoalHistory:               append([]GoalRevision(nil), run.GoalHistory...),
		Checkpoint:                checkpoint,
		ContextSnapshot:           cloneMap(run.ContextSnapshot),
		SurfaceCapabilities:       cloneMap(run.SurfaceCapabilities),
		SessionPreferenceFacts: append(
			[]preferencemodel.Snapshot(nil),
			run.SessionPreferenceFacts...,
		),
		LongTermPreferenceFacts: append(
			[]preferencemodel.Snapshot(nil),
			run.LongTermPreferenceFacts...,
		),
		IdempotencyPrefix: "run:" + run.RunID + ":goal:" + fmt.Sprint(run.GoalRevision),
		CreatedAt:         run.CreatedAt,
	}
}

func mutationPayload(run Run, eventKind string) map[string]any {
	if eventKind == "completed" || eventKind == "failed" || eventKind == "cancelled" {
		return terminalMutationPayload(run, eventKind)
	}
	payload := map[string]any{
		"status":       run.State.WireName(),
		"runRevision":  run.Revision,
		"goalRevision": run.GoalRevision,
	}
	switch eventKind {
	case "answer_delta":
		for index := len(run.Items) - 1; index >= 0; index-- {
			if run.Items[index].Kind == generated.AssistantRunItemKindFinalAnswer {
				payload["text"] = run.Items[index].Payload["text"]
				break
			}
		}
	case "process_append", "process_commit":
		if process := latestVisibleProcess(run); process != nil {
			payload["process"] = process
		}
	case "presentation_snapshot":
		revision, _ := presentationRevision(run.PresentationDocument["revision"])
		payload["baseRevision"] = int64(0)
		payload["revision"] = revision
		payload["document"] = cloneMap(run.PresentationDocument)
	case "presentation_commit":
		revision, _ := presentationRevision(run.PresentationDocument["revision"])
		payload["baseRevision"] = revision - 1
		payload["revision"] = revision
	}
	return payload
}

func terminalMutationPayload(run Run, eventKind string) map[string]any {
	processes := any([]map[string]any{})
	if value, found := run.TerminalSnapshot["processes"]; found && value != nil {
		processes = value
	}
	payload := map[string]any{
		"status":      run.State.WireName(),
		"finalAnswer": run.TerminalSnapshot["answerText"],
		"processes":   processes,
	}
	if eventKind == "failed" {
		payload["runtimeFailure"] = run.TerminalSnapshot["failure"]
	}
	return payload
}

// TerminalReplayEvent projects the no-TTL terminal snapshot into the one
// terminal SSE event required after the bounded journal has expired.
func TerminalReplayEvent(run Run) (JournalEvent, bool) {
	if run.CompletedAt == nil || len(run.TerminalSnapshot) == 0 ||
		!terminalRunState(run.State) || run.JournalSequence <= 0 {
		return JournalEvent{}, false
	}
	kind := run.State.WireName()
	return JournalEvent{
		EventID:   run.RunID + ":terminal-replay",
		RunID:     run.RunID,
		Sequence:  run.JournalSequence,
		Revision:  run.Revision,
		Kind:      kind,
		Payload:   mutationPayload(run, kind),
		CreatedAt: run.CompletedAt.UTC(),
	}, true
}

func latestVisibleProcess(run Run) map[string]any {
	for index := len(run.Items) - 1; index >= 0; index-- {
		item := run.Items[index]
		if item.Kind == generated.AssistantRunItemKindPlan ||
			item.Kind == generated.AssistantRunItemKindFinalAnswer {
			continue
		}
		process := cloneMap(item.Payload)
		if process == nil {
			process = map[string]any{}
		}
		process["processId"] = item.ItemID
		process["order"] = item.Sequence
		process["summary"] = item.Summary
		if strings.TrimSpace(fmt.Sprint(process["scope"])) == "" {
			process["scope"] = string(item.Kind)
		}
		if strings.TrimSpace(fmt.Sprint(process["stage"])) == "" {
			process["stage"] = string(item.Kind)
		}
		switch item.Status {
		case generated.AssistantRunItemStatusStarted:
			process["status"] = "active"
		default:
			process["status"] = string(item.Status)
		}
		return process
	}
	return nil
}

func remainingBudget(run Run) map[string]int64 {
	result := map[string]int64{}
	for _, task := range run.TaskGraph.Tasks {
		result["toolCalls"] += int64(task.Budget.MaxToolCalls)
		result["tokens"] += task.Budget.MaxTokens
		result["costUnits"] += task.Budget.MaxCostUnits
	}
	return result
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
