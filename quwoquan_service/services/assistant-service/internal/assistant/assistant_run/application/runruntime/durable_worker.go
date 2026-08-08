package runruntime

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
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
	ReasoningPolicy           ReasoningProfileConfig
	DefinitionOfDone          DefinitionOfDone
	TaskGraph                 TaskGraph
	GoalHistory               []GoalRevision
	Checkpoint                *Checkpoint
	BudgetConsumption         BudgetConsumption
	BudgetReceiptSequence     int64
	ContextSnapshot           map[string]any
	SurfaceCapabilities       map[string]any
	SessionContinuity         *SessionContinuity
	ConfirmedSlots            assistantmodel.AssistantRunConfirmedSlots
	SessionPreferences        []preferencemodel.AssistantPreferenceSnapshot
	LongTermPreferences       []preferencemodel.AssistantPreferenceSnapshot
	FeedbackContextSnapshot   assistantmodel.AssistantFeedbackContextSnapshot
	IdempotencyPrefix         string
	CreatedAt                 time.Time
	verifyCompletion          executionCompletionVerifier
}

type executionCompletionVerifier func(
	context.Context,
	ExecutionResult,
) (bool, error)

// VerifyCompletionWithinExecutionBudget invokes the worker-owned verifier
// while the production executor's request-scoped model policy and durable
// usage sink are still active. Callers can invoke but cannot replace the
// callback because the authority remains private to runruntime.
func (request ExecutionRequest) VerifyCompletionWithinExecutionBudget(
	ctx context.Context,
	result ExecutionResult,
) (bool, error) {
	if request.verifyCompletion == nil {
		return false, nil
	}
	return request.verifyCompletion(ctx, result)
}

// ExecutionTaskUpdate binds one public execution process to a durable task.
// The executor proposes the task's goal and dependency frontier; AssistantRun
// remains the only authority that can add or transition the TaskGraph node.
type ExecutionTaskUpdate struct {
	Goal         string
	Dependencies []string
	OwnerAgent   string
	Budget       TaskBudget
}

type ExecutionItemUpdate struct {
	ItemID       string
	Kind         generated.AssistantRunItemKind
	Status       generated.AssistantRunItemStatus
	TaskID       string
	Summary      string
	Payload      map[string]any
	ArtifactRefs []string
	Task         *ExecutionTaskUpdate
	Budget       *BudgetConsumptionReceipt
}

type ExecutionResult struct {
	AnswerText           string
	Processes            []assistantmodel.AssistantRunVisibleProcess
	ArtifactRefs         []string
	EvidenceRefs         []string
	VerificationEvidence []VerificationEvidence
	Presentation         map[string]any
	WaitingState         generated.AssistantRunState
	WaitReason           string
	PendingApprovalRef   string
	ConfirmedSlots       assistantmodel.AssistantRunConfirmedSlots
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

// InExecutionCompletionVerifier is implemented by production executors that
// promise to invoke the worker-owned completion verifier before their durable
// model budget context leaves scope. The worker fails closed if such an
// executor returns a terminal result without the bound verification capture.
type InExecutionCompletionVerifier interface {
	VerifiesCompletionWithinExecutionBudget() bool
}

type executionCompletionVerificationCapture struct {
	mu           sync.Mutex
	runDigest    string
	resultDigest string
	verdict      VerificationVerdict
	found        bool
}

func (capture *executionCompletionVerificationCapture) verify(
	result ExecutionResult,
	verify func() (VerificationVerdict, string, bool, error),
) (bool, error) {
	digest, err := commandDigest(
		"assistant_run_completion_verification_result",
		result,
	)
	if err != nil {
		return false, err
	}
	capture.mu.Lock()
	defer capture.mu.Unlock()
	if capture.found {
		if capture.resultDigest != digest {
			return false, ErrJournalCorrupt
		}
		return true, nil
	}
	verdict, runDigest, found, err := verify()
	if err != nil || !found {
		return found, err
	}
	if strings.TrimSpace(runDigest) == "" {
		return false, ErrJournalCorrupt
	}
	capture.runDigest = strings.TrimSpace(runDigest)
	capture.resultDigest = digest
	capture.verdict = cloneExecutionVerificationVerdict(verdict)
	capture.found = true
	return true, nil
}

func (capture *executionCompletionVerificationCapture) load(
	run Run,
	result ExecutionResult,
) (VerificationVerdict, bool, error) {
	digest, err := commandDigest(
		"assistant_run_completion_verification_result",
		result,
	)
	if err != nil {
		return VerificationVerdict{}, false, err
	}
	capture.mu.Lock()
	defer capture.mu.Unlock()
	if !capture.found {
		return VerificationVerdict{}, false, nil
	}
	if capture.runDigest != ProtectedRunFactsDigest(run) ||
		capture.resultDigest != digest {
		return VerificationVerdict{}, false, ErrJournalCorrupt
	}
	return cloneExecutionVerificationVerdict(capture.verdict), true, nil
}

func cloneExecutionVerificationVerdict(
	verdict VerificationVerdict,
) VerificationVerdict {
	cloned := verdict
	cloned.Missing = append([]string{}, verdict.Missing...)
	cloned.Failed = append([]string{}, verdict.Failed...)
	cloned.Evidence = make([]VerificationEvidence, len(verdict.Evidence))
	for index, row := range verdict.Evidence {
		cloned.Evidence[index] = row
		cloned.Evidence[index].ArtifactRefs = append(
			[]string{},
			row.ArtifactRefs...,
		)
	}
	return cloned
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
	reasoningProfiles *ReasoningProfileCatalog
	hooks             *HookRegistry
	logger            *slog.Logger

	healthMu           sync.RWMutex
	lastSuccessfulPoll time.Time
	lastFailure        error
}

type workClaimContextKey struct{}

func withWorkClaim(ctx context.Context, claim WorkClaim) context.Context {
	return context.WithValue(ctx, workClaimContextKey{}, claim)
}

func workClaimFromContext(ctx context.Context, runID string) (WorkClaim, error) {
	claim, ok := ctx.Value(workClaimContextKey{}).(WorkClaim)
	if !ok || strings.TrimSpace(claim.RunID) != strings.TrimSpace(runID) ||
		strings.TrimSpace(claim.WorkerID) == "" || claim.FencingToken <= 0 {
		return WorkClaim{}, ErrExecutionFenced
	}
	return claim, nil
}

func NewDurableWorker(
	repository WorkerRepository,
	queue WorkQueue,
	executor RunExecutor,
	workerID string,
) *DurableWorker {
	profiles, err := DefaultReasoningProfileCatalog()
	if err != nil {
		panic(fmt.Sprintf("default assistant reasoning profiles: %v", err))
	}
	hooks, err := NewHookRegistry()
	if err != nil {
		panic(fmt.Sprintf("default assistant run hooks: %v", err))
	}
	return NewConfiguredDurableWorker(
		repository,
		queue,
		executor,
		workerID,
		profiles,
		hooks,
	)
}

// NewConfiguredDurableWorker is the single construction path for a worker
// with explicit, provider-neutral execution policy and lifecycle hooks.

func NewConfiguredDurableWorker(
	repository WorkerRepository,
	queue WorkQueue,
	executor RunExecutor,
	workerID string,
	reasoningProfiles *ReasoningProfileCatalog,
	hooks *HookRegistry,
) *DurableWorker {
	if repository == nil || queue == nil || executor == nil ||
		strings.TrimSpace(workerID) == "" || reasoningProfiles == nil || hooks == nil {
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
		reasoningProfiles: reasoningProfiles,
		hooks:             hooks,
		logger:            slog.Default(),
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
			if err != nil && ctx.Err() == nil {
				w.logger.ErrorContext(
					ctx,
					"assistant durable run worker poll failed",
					slog.String("error", err.Error()),
				)
			}
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
	defer func() {
		w.recordPoll(resultErr)
	}()
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
	// A durable claim is a real queue round trip. Record it immediately so a
	// long-running Run remains live while its lease heartbeats continue.
	w.recordPoll(nil)
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
					w.recordPoll(heartbeat)
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
				w.recordPoll(nil)
				claimMu.Lock()
				activeClaim = next
				claimMu.Unlock()
			}
		}
	}()

	processErr := w.processClaim(processCtx, claim)
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
	reschedule := false
	switch {
	case loadErr == nil:
		reschedule = queueRunnableRun(run)
	case errors.Is(loadErr, ErrRunNotFound):
		// The aggregate no longer exists, so retaining its work document would
		// create a permanently unclaimable poison item.
		reschedule = false
	default:
		// A failed snapshot read cannot prove terminality. Preserve the work
		// claim so a later worker can recover the authoritative Run.
		reschedule = true
	}
	if loadErr == nil && processErr != nil &&
		!errors.Is(processErr, context.Canceled) {
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

func (w *DurableWorker) processClaim(ctx context.Context, claim WorkClaim) error {
	runID := strings.TrimSpace(claim.RunID)
	if runID == "" || strings.TrimSpace(claim.WorkerID) == "" ||
		claim.FencingToken <= 0 {
		return ErrExecutionFenced
	}
	ctx = withWorkClaim(ctx, claim)
	run, err := w.repository.Load(ctx, runID)
	if err != nil {
		return err
	}
	observeCheckpointAge(run.Checkpoint, w.now())
	if terminalRunState(run.State) || !queueRunnableRun(run) {
		return nil
	}
	reasoningPolicy := run.ReasoningPolicy
	if reasoningPolicy.Profile == "" {
		reasoningPolicy, err = w.reasoningProfiles.Resolve(run.ReasoningProfile)
	} else if reasoningPolicy.Profile != run.ReasoningProfile {
		err = fmt.Errorf(
			"frozen reasoning profile %s does not match Run profile %s",
			reasoningPolicy.Profile,
			run.ReasoningProfile,
		)
	}
	if err == nil {
		err = validateReasoningProfileForRun(reasoningPolicy, run.DefinitionOfDone)
	}
	if err != nil {
		return w.failRun(
			ctx,
			run,
			"reasoning_profile_rejected",
			&ExecutionFailure{
				Code:   "ASSISTANT.SYSTEM.run_reasoning_profile_unavailable",
				Origin: "system",
				Kind:   "policy",
				Nature: "permanent",
			},
		)
	}
	run, err = w.applyReasoningBudget(ctx, run, reasoningPolicy)
	if err != nil {
		return err
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
	switch run.State {
	case generated.AssistantRunStateExecuting,
		generated.AssistantRunStateObserving,
		generated.AssistantRunStateReflecting,
		generated.AssistantRunStateSynthesizing,
		generated.AssistantRunStateVerifying:
		handled, recoveryErr := w.recoverPersistedCompletion(ctx, run)
		if handled || recoveryErr != nil {
			return recoveryErr
		}
	}
	if run.State != generated.AssistantRunStateExecuting {
		return w.failRun(ctx, run, "runnable_state_unhandled", ErrJournalCorrupt)
	}

	executionDeadline := run.CreatedAt.UTC().Add(reasoningPolicy.Budget.MaxDuration)
	if !w.now().UTC().Before(executionDeadline) {
		return w.failRun(
			ctx,
			run,
			"reasoning_budget_exhausted",
			context.DeadlineExceeded,
		)
	}
	deadlineCtx, cancelDeadline := context.WithDeadline(ctx, executionDeadline)
	defer cancelDeadline()
	executionCtx, cancelExecution := context.WithCancelCause(deadlineCtx)
	defer cancelExecution(nil)
	executionCtx = WithExecutionHooks(executionCtx, w.hooks, run)
	initialContextState := ContextExecutionState{}
	var initialContextCompaction *ContextCompactionCheckpoint
	initialContextReceiptSequence := int64(0)
	contextScope := ContextProgressScope(run)
	if run.Checkpoint != nil {
		initialContextState = cloneContextExecutionState(
			run.Checkpoint.ContextState,
		)
		initialContextCompaction = cloneContextCompaction(
			run.Checkpoint.ContextCompaction,
		)
		if run.Checkpoint.ContextReceiptScope == contextScope {
			initialContextReceiptSequence = run.Checkpoint.ContextReceiptSeq
		}
	}
	executionCtx, err = WithContextCompactionRuntime(
		executionCtx,
		ContextCompactionRuntimeConfig{
			Scope:                  contextScope,
			CheckpointEvery:        reasoningPolicy.CheckpointEvery,
			StartedAt:              run.CreatedAt,
			InitialState:           initialContextState,
			InitialCompaction:      initialContextCompaction,
			InitialReceiptSequence: initialContextReceiptSequence,
			Now:                    w.now,
			Sink: func(
				receiptCtx context.Context,
				receipt ContextProgressReceipt,
			) error {
				_, commitErr := w.commitMutation(
					receiptCtx,
					run.RunID,
					"checkpoint_committed",
					func(current *Run, now time.Time) error {
						return current.RecordContextProgress(receipt, now)
					},
				)
				return commitErr
			},
		},
	)
	if err != nil {
		return w.failRun(
			ctx,
			run,
			"context_checkpoint_rejected",
			err,
		)
	}
	completionVerification := &executionCompletionVerificationCapture{}
	request := executionRequest(run, reasoningPolicy)
	request.verifyCompletion = func(
		verificationCtx context.Context,
		result ExecutionResult,
	) (bool, error) {
		return completionVerification.verify(
			result,
			func() (VerificationVerdict, string, bool, error) {
				activeClaim, claimErr := workClaimFromContext(
					verificationCtx,
					run.RunID,
				)
				if claimErr != nil || activeClaim.WorkerID != claim.WorkerID ||
					activeClaim.FencingToken != claim.FencingToken {
					return VerificationVerdict{}, "", false, ErrExecutionFenced
				}
				current, loadErr := w.repository.Load(
					verificationCtx,
					run.RunID,
				)
				if loadErr != nil {
					return VerificationVerdict{}, "", false, loadErr
				}
				if terminalRunState(current.State) || current.PauseRequested ||
					result.WaitingState != "" {
					return VerificationVerdict{}, "", false, nil
				}
				availableArtifactRefs := uniqueSorted(append(
					append([]string{}, result.ArtifactRefs...),
					result.EvidenceRefs...,
				))
				return w.hooks.VerifyCompletion(
					verificationCtx,
					current.DefinitionOfDone,
					VerificationInput{
						Run:                   current,
						Result:                result,
						AvailableArtifactRefs: availableArtifactRefs,
					},
				), ProtectedRunFactsDigest(current), true, nil
			},
		)
	}
	controlDone := make(chan struct{})
	controlStopped := make(chan struct{})
	go func() {
		defer close(controlStopped)
		w.monitorRunControl(
			executionCtx,
			run.RunID,
			cancelExecution,
			controlDone,
		)
	}()
	result, executionErr := w.executor.Execute(
		executionCtx,
		request,
		func(update ExecutionItemUpdate) error {
			return w.persistExecutionUpdateWithBudgetReadback(
				executionCtx,
				run.RunID,
				update,
			)
		},
	)
	close(controlDone)
	// Cancel an in-flight control read and join the monitor before classifying
	// the execution result. The first cancel cause wins, so a repository error
	// observed by the monitor cannot be overwritten by this normal shutdown.
	cancelExecution(nil)
	<-controlStopped
	var controlObservation *runControlObservationError
	controlObservationFailed := errors.As(
		context.Cause(executionCtx),
		&controlObservation,
	)
	var controlObservationErr error
	if controlObservationFailed {
		controlObservationErr = controlObservation
	}
	if executionErr != nil {
		if errors.Is(executionErr, ErrExecutionCancelled) {
			return w.awaitCoordinatedCancellation(
				context.WithoutCancel(ctx),
				run.RunID,
			)
		}
		current, loadErr := w.repository.Load(context.WithoutCancel(ctx), run.RunID)
		if loadErr != nil {
			return errors.Join(executionErr, controlObservationErr, loadErr)
		}
		if terminalRunState(current.State) {
			return nil
		}
		if current.PauseRequested {
			return w.checkpointAndPause(
				context.WithoutCancel(ctx),
				current,
				result,
			)
		}
		if controlObservationFailed {
			return controlObservation
		}
		if errors.Is(executionErr, ErrExecutionReplanned) {
			// A completed Item is the safe boundary: the revised goal and its
			// audit Plan item were already committed. Keep the Run executable so
			// the queue can claim it with the new goal revision.
			return nil
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
	if controlObservationFailed {
		current, loadErr := w.repository.Load(
			context.WithoutCancel(ctx),
			run.RunID,
		)
		if loadErr != nil {
			return errors.Join(controlObservation, loadErr)
		}
		if terminalRunState(current.State) {
			return nil
		}
		if current.PauseRequested {
			return w.checkpointAndPause(
				context.WithoutCancel(ctx),
				current,
				result,
			)
		}
		return controlObservation
	}
	current, err := w.repository.Load(ctx, run.RunID)
	if err != nil {
		return err
	}
	if terminalRunState(current.State) {
		return nil
	}
	if current.PauseRequested {
		return w.checkpointAndPause(ctx, current, result)
	}
	if result.WaitingState != "" {
		return w.waitRun(ctx, current, result)
	}
	verdict, found, captureErr := completionVerification.load(current, result)
	if captureErr != nil {
		return w.failRun(
			ctx,
			current,
			"completion_verification_capture_invalid",
			captureErr,
		)
	}
	if executor, required := w.executor.(InExecutionCompletionVerifier); required && executor.VerifiesCompletionWithinExecutionBudget() && !found {
		return w.failRun(
			ctx,
			current,
			"completion_verification_budget_ledger_missing",
			ErrCompletionRejected,
		)
	}
	return w.completeRun(ctx, current, result, verdict, found)
}

func (w *DurableWorker) persistExecutionUpdateWithBudgetReadback(
	ctx context.Context,
	runID string,
	update ExecutionItemUpdate,
) error {
	err := w.persistExecutionUpdate(ctx, runID, update)
	if err == nil || update.Budget == nil {
		return err
	}
	current, loadErr := w.repository.Load(context.WithoutCancel(ctx), runID)
	if loadErr == nil && budgetReceiptMatchesCheckpoint(current, *update.Budget) {
		return nil
	}
	return err
}

func budgetReceiptMatchesCheckpoint(
	run Run,
	receipt BudgetConsumptionReceipt,
) bool {
	return run.Checkpoint != nil &&
		strings.TrimSpace(run.Checkpoint.BudgetReceiptScope) ==
			strings.TrimSpace(receipt.Scope) &&
		run.Checkpoint.BudgetReceiptSeq == receipt.Sequence &&
		run.Checkpoint.BudgetConsumption == receipt.Consumption
}
