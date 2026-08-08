// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
package assistant_run_test

import (
	"context"
	"errors"
	"strconv"
	"strings"
	"sync"
	"testing"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

func TestCompletionBoundaryAppliesSteerAfterFinalOrBudgetOnlyUpdate(t *testing.T) {
	for _, mode := range []string{"final_only", "budget_only"} {
		t.Run(mode, func(t *testing.T) {
			repository := newMemoryRunRepository()
			commands := workerCommandService(repository)
			run, err := commands.Start(t.Context(), runruntime.StartCommand{
				UserID: "user-completion-gap-" + mode, SessionID: "session-completion-gap",
				ClientRequestID: "request-completion-gap-" + mode,
				InputText:       "生成旧目标答案",
			})
			if err != nil {
				t.Fatalf("start run: %v", err)
			}
			executor := &completionBoundaryGapExecutor{
				commands: commands, userID: run.UserID, mode: mode,
				instruction: "在完成前切换到新目标",
			}
			queue := newMemoryWorkQueue()
			queue.enqueue(run.RunID)
			worker := runruntime.NewDurableWorker(
				repository, queue, executor, "worker-completion-gap-"+mode,
			)

			if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
				t.Fatalf("first completion boundary: worked=%t err=%v", worked, processErr)
			}
			replanned := loadCompletionBoundaryRun(t, repository, run.RunID)
			assertCompletionBoundaryReplanned(t, replanned, 2, 1)
			assertNoCompletionFacts(t, replanned)

			if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
				t.Fatalf("replanned completion: worked=%t err=%v", worked, processErr)
			}
			completed := loadCompletionBoundaryRun(t, repository, run.RunID)
			if completed.State != generated.AssistantRunStateCompleted ||
				executor.callCount() != 2 ||
				!strings.Contains(executor.requestAt(1).Goal, "在完成前切换到新目标") {
				t.Fatalf("replanned goal did not complete: run=%#v requests=%#v", completed, executor.requestsSnapshot())
			}
		})
	}
}

func TestAcceptedCompletionCASLosesToPendingSteerWithoutPersistingOldCapsule(t *testing.T) {
	base := newMemoryRunRepository()
	commands := workerCommandService(base)
	run, err := commands.Start(t.Context(), runruntime.StartCommand{
		UserID: "user-accepted-race", SessionID: "session-accepted-race",
		ClientRequestID: "request-accepted-race", InputText: "旧目标",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	var once sync.Once
	repository := &completionCommitInterceptor{
		memoryRunRepository: base,
		before: func(candidate runruntime.Run, events []runruntime.JournalEvent) error {
			if !completionCommitContainsCapsule(candidate, events) {
				return nil
			}
			var steerErr error
			once.Do(func() {
				_, steerErr = commands.Steer(
					t.Context(), run.UserID, run.RunID,
					"steer-before-accepted-cas", "新目标抢先提交",
				)
			})
			return steerErr
		},
	}
	executor := &completionRaceExecutor{}
	queue := newMemoryWorkQueue()
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository, queue, executor, "worker-accepted-race",
	)
	if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
		t.Fatalf("accepted CAS race: worked=%t err=%v", worked, processErr)
	}
	replanned := loadCompletionBoundaryRun(t, base, run.RunID)
	assertCompletionBoundaryReplanned(t, replanned, 2, 1)
	assertNoCompletionFacts(t, replanned)
	if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
		t.Fatalf("accepted race replay: worked=%t err=%v", worked, processErr)
	}
	if completed := loadCompletionBoundaryRun(t, base, run.RunID); completed.State != generated.AssistantRunStateCompleted ||
		executor.callCount() != 2 {
		t.Fatalf("accepted race did not complete revised goal: %#v", completed)
	}
}

func TestCompletionBoundaryRejectsGoalRevisionWithOtherProtectedFactDrift(t *testing.T) {
	base := newMemoryRunRepository()
	commands := workerCommandService(base)
	run, err := commands.Start(t.Context(), runruntime.StartCommand{
		UserID: "user-protected-drift", SessionID: "session-protected-drift",
		ClientRequestID: "request-protected-drift", InputText: "原始受保护目标",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	var once sync.Once
	repository := &completionCommitInterceptor{
		memoryRunRepository: base,
		before: func(candidate runruntime.Run, events []runruntime.JournalEvent) error {
			if !completionCommitContainsGoalReplan(candidate, events) {
				return nil
			}
			once.Do(func() {
				candidate.UserID = "tampered-protected-user"
				base.mu.Lock()
				base.runs[run.RunID] = candidate
				base.mu.Unlock()
			})
			return nil
		},
	}
	executor := &completionBoundaryGapExecutor{
		commands: commands, userID: run.UserID, mode: "final_only",
		instruction: "合法推进 GoalRevision",
	}
	queue := newMemoryWorkQueue()
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository, queue, executor, "worker-protected-drift",
	)
	worked, processErr := worker.ProcessNext(t.Context())
	if !worked || !errors.Is(processErr, runruntime.ErrRevisionConflict) {
		t.Fatalf("protected fact drift: worked=%t err=%v", worked, processErr)
	}
	persisted := loadCompletionBoundaryRun(t, base, run.RunID)
	if persisted.State != generated.AssistantRunStateExecuting ||
		persisted.UserID != "tampered-protected-user" {
		t.Fatalf("protected fact drift was overwritten or terminalized: %#v", persisted)
	}
	assertNoCompletionFacts(t, persisted)
}

func TestAcceptedCompletionCASLosesToPauseAndPersistsCheckpoint(t *testing.T) {
	base := newMemoryRunRepository()
	commands := workerCommandService(base)
	run, err := commands.Start(t.Context(), runruntime.StartCommand{
		UserID: "user-pause-race", SessionID: "session-pause-race",
		ClientRequestID: "request-pause-race", InputText: "完成前暂停",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	var once sync.Once
	repository := &completionCommitInterceptor{
		memoryRunRepository: base,
		before: func(candidate runruntime.Run, events []runruntime.JournalEvent) error {
			if !completionCommitContainsCapsule(candidate, events) {
				return nil
			}
			var pauseErr error
			once.Do(func() {
				_, pauseErr = commands.Pause(
					t.Context(), run.UserID, run.RunID,
					"pause-before-accepted-cas", "用户在完成前暂停",
				)
			})
			return pauseErr
		},
	}
	executor := &completionRaceExecutor{}
	queue := newMemoryWorkQueue()
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository, queue, executor, "worker-pause-race",
	)
	if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
		t.Fatalf("pause CAS race: worked=%t err=%v", worked, processErr)
	}
	paused := loadCompletionBoundaryRun(t, base, run.RunID)
	if paused.State != generated.AssistantRunStatePaused ||
		paused.PauseRequested || paused.Checkpoint == nil || executor.callCount() != 1 {
		t.Fatalf("pause did not win completion boundary: %#v", paused)
	}
	assertNoCompletionFacts(t, paused)
	base.mu.Lock()
	events := append([]runruntime.JournalEvent{}, base.events[run.RunID]...)
	base.mu.Unlock()
	for _, event := range events {
		if event.Kind == "answer_delta" {
			t.Fatalf("pause-only boundary emitted an answer event: %#v", event)
		}
	}
}

func TestRejectedVerdictSteerBumpsAttemptBeforeRepair(t *testing.T) {
	base := newMemoryRunRepository()
	run := startVerifierRepairRun(
		t, base, generated.AssistantReasoningProfileBalanced, "rejected-steer-race",
	)
	commands := workerCommandService(base)
	var once sync.Once
	repository := &completionCommitInterceptor{
		memoryRunRepository: base,
		after: func(candidate runruntime.Run, events []runruntime.JournalEvent) error {
			if !completionCommitContainsRejectedVerdict(candidate, events) {
				return nil
			}
			var steerErr error
			once.Do(func() {
				_, steerErr = commands.Steer(
					t.Context(), run.UserID, run.RunID,
					"steer-after-rejected-verdict", "替换被拒绝的旧目标",
				)
			})
			return steerErr
		},
	}
	executor := &completionRaceExecutor{rejectFirst: true}
	queue := newMemoryWorkQueue()
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository, queue, executor, "worker-rejected-race",
	)
	if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
		t.Fatalf("rejected verdict race: worked=%t err=%v", worked, processErr)
	}
	replanned := loadCompletionBoundaryRun(t, base, run.RunID)
	assertCompletionBoundaryReplanned(t, replanned, 2, 2)
	assertNoCompletionCapsule(t, replanned)
	oldVerdict := verifierItemForAttempt(t, replanned, 1)
	if oldVerdict.Payload["accepted"] != false ||
		payloadAttempt(oldVerdict.Payload) != 1 ||
		payloadInteger(oldVerdict.Payload["goalRevision"]) != 1 ||
		!validTestSHA256(oldVerdict.Payload["protectedRunFactsDigest"]) {
		t.Fatalf("rejected verdict was not bound to old protected facts: %#v", oldVerdict.Payload)
	}
	if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
		t.Fatalf("rejected race replay: worked=%t err=%v", worked, processErr)
	}
	completed := loadCompletionBoundaryRun(t, base, run.RunID)
	if completed.State != generated.AssistantRunStateCompleted ||
		verifierRepairRootTask(t, completed).Attempt != 2 ||
		executor.callCount() != 2 {
		t.Fatalf("rejected race did not complete isolated attempt: %#v", completed)
	}
}

func TestAcceptedCapsuleAckLossRejectsSteerAndRecoversWithoutExecution(t *testing.T) {
	base := newMemoryRunRepository()
	commands := workerCommandService(base)
	run, err := commands.Start(t.Context(), runruntime.StartCommand{
		UserID: "user-capsule-ack", SessionID: "session-capsule-ack",
		ClientRequestID: "request-capsule-ack", InputText: "持久完成",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	var once sync.Once
	repository := &completionCommitInterceptor{
		memoryRunRepository: base,
		after: func(candidate runruntime.Run, events []runruntime.JournalEvent) error {
			if !completionCommitContainsCapsule(candidate, events) {
				return nil
			}
			var injected error
			once.Do(func() { injected = errCompletionCapsuleAckLost })
			return injected
		},
	}
	executor := &completionRaceExecutor{}
	queue := newMemoryWorkQueue()
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository, queue, executor, "worker-capsule-ack-a",
	)
	worked, processErr := worker.ProcessNext(t.Context())
	if !worked || !errors.Is(processErr, errCompletionCapsuleAckLost) {
		t.Fatalf("accepted capsule ACK loss: worked=%t err=%v", worked, processErr)
	}
	persisted := loadCompletionBoundaryRun(t, base, run.RunID)
	if persisted.State != generated.AssistantRunStateExecuting {
		t.Fatalf("capsule ACK loss advanced state: %#v", persisted)
	}
	assertAcceptedCompletionPair(t, persisted)
	if _, steerErr := commands.Steer(
		t.Context(), run.UserID, run.RunID,
		"steer-after-capsule-ack-loss", "不得绑定到旧 capsule",
	); !errors.Is(steerErr, runruntime.ErrInvalidTransition) {
		t.Fatalf("accepted capsule allowed steer after ACK loss: %v", steerErr)
	}
	if _, pauseErr := commands.Pause(
		t.Context(), run.UserID, run.RunID,
		"pause-after-capsule-ack-loss", "不得忽略已接受完成事实",
	); !errors.Is(pauseErr, runruntime.ErrInvalidTransition) {
		t.Fatalf("accepted capsule allowed pause after ACK loss: %v", pauseErr)
	}
	if afterPause := loadCompletionBoundaryRun(t, base, run.RunID); afterPause.PauseRequested {
		t.Fatalf("rejected pause changed accepted completion: %#v", afterPause)
	}

	worker = runruntime.NewDurableWorker(
		repository, queue, executor, "worker-capsule-ack-b",
	)
	if worked, processErr = worker.ProcessNext(t.Context()); processErr != nil || !worked {
		t.Fatalf("recover accepted capsule: worked=%t err=%v", worked, processErr)
	}
	completed := loadCompletionBoundaryRun(t, base, run.RunID)
	if completed.State != generated.AssistantRunStateCompleted ||
		executor.callCount() != 1 {
		t.Fatalf("ACK recovery repeated execution: run=%#v calls=%d", completed, executor.callCount())
	}
	if _, steerErr := commands.Steer(
		t.Context(), run.UserID, run.RunID,
		"steer-after-capsule-terminal", "仍不得修改已接受目标",
	); !errors.Is(steerErr, runruntime.ErrInvalidTransition) {
		t.Fatalf("terminal accepted capsule changed steer result: %v", steerErr)
	}
}

func TestAcceptedCompletionRecoveryRejectsPersistedPauseFlag(t *testing.T) {
	base := newMemoryRunRepository()
	commands := workerCommandService(base)
	run, err := commands.Start(t.Context(), runruntime.StartCommand{
		UserID: "user-pair-pause-corrupt", SessionID: "session-pair-pause-corrupt",
		ClientRequestID: "request-pair-pause-corrupt", InputText: "完成事实不得携带暂停标记",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	repository := &interruptAfterCommitRepository{
		memoryRunRepository: base,
		kind:                "answer_delta",
		state:               generated.AssistantRunStateExecuting,
	}
	queue := newMemoryWorkQueue()
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository, queue, &countingTerminalExecutor{}, "worker-pair-pause-corrupt-a",
	)
	if worked, processErr := worker.ProcessNext(t.Context()); !worked ||
		!errors.Is(processErr, errInjectedTerminalBoundary) {
		t.Fatalf("persist accepted pair: worked=%t err=%v", worked, processErr)
	}
	base.mu.Lock()
	corrupt := base.runs[run.RunID]
	corrupt.PauseRequested = true
	base.runs[run.RunID] = corrupt
	base.mu.Unlock()

	worker = runruntime.NewDurableWorker(
		repository, queue, &countingTerminalExecutor{}, "worker-pair-pause-corrupt-b",
	)
	if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
		t.Fatalf("recover corrupt pause flag: worked=%t err=%v", worked, processErr)
	}
	failed := loadCompletionBoundaryRun(t, base, run.RunID)
	if failed.State != generated.AssistantRunStateFailed ||
		failed.TerminalReason != "completion_capsule_corrupt" {
		t.Fatalf("accepted pair with pause flag did not fail closed: %#v", failed)
	}
}

func TestCompletionBoundaryRecoveryKeepsTransientErrorsRetryable(t *testing.T) {
	tests := []struct {
		name      string
		err       error
		failCount int
	}{
		{name: "repository_transient", err: errCompletionBoundaryTransient, failCount: 1},
		{name: "claim_fenced", err: runruntime.ErrExecutionFenced, failCount: 1},
		{name: "revision_retry_exhausted", err: runruntime.ErrRevisionConflict, failCount: 4},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			base := newMemoryRunRepository()
			commands := workerCommandService(base)
			run, err := commands.Start(t.Context(), runruntime.StartCommand{
				UserID: "user-transient-" + test.name, SessionID: "session-transient",
				ClientRequestID: "request-transient-" + test.name,
				InputText:       "瞬时失败后继续执行",
			})
			if err != nil {
				t.Fatalf("start run: %v", err)
			}
			executor := &completionRecoveryTransientExecutor{
				commands: commands, userID: run.UserID,
			}
			repository := &completionBoundaryFailureRepository{
				memoryRunRepository: base,
				failure:             test.err,
				remaining:           test.failCount,
			}
			queue := newMemoryWorkQueue()
			queue.enqueue(run.RunID)
			worker := runruntime.NewDurableWorker(
				repository, queue, executor, "worker-transient-"+test.name,
			)
			if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
				t.Fatalf("prepare pending steer: worked=%t err=%v", worked, processErr)
			}
			worked, processErr := worker.ProcessNext(t.Context())
			if !worked || !errors.Is(processErr, test.err) {
				t.Fatalf("transient recovery: worked=%t err=%v", worked, processErr)
			}
			pending := loadCompletionBoundaryRun(t, base, run.RunID)
			if pending.State != generated.AssistantRunStateExecuting ||
				len(pending.PendingSteer) != 1 || terminalRunStateForTest(pending.State) {
				t.Fatalf("transient recovery terminalized pending steer: %#v", pending)
			}
			if worked, processErr = worker.ProcessNext(t.Context()); processErr != nil || !worked {
				t.Fatalf("retry completion boundary: worked=%t err=%v", worked, processErr)
			}
			if worked, processErr = worker.ProcessNext(t.Context()); processErr != nil || !worked {
				t.Fatalf("complete retried goal: worked=%t err=%v", worked, processErr)
			}
			completed := loadCompletionBoundaryRun(t, base, run.RunID)
			if completed.State != generated.AssistantRunStateCompleted || executor.callCount() != 2 {
				t.Fatalf("transient recovery did not converge: run=%#v calls=%d", completed, executor.callCount())
			}
		})
	}
}

func TestSteerFailsClosedForIncompleteOrCorruptAcceptedCompletionPair(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*runruntime.Run)
	}{
		{
			name: "missing_verdict",
			mutate: func(run *runruntime.Run) {
				items := run.Items[:0]
				for _, item := range run.Items {
					if item.Kind != generated.AssistantRunItemKindEvidence {
						items = append(items, item)
					}
				}
				run.Items = items
			},
		},
		{
			name: "missing_capsule",
			mutate: func(run *runruntime.Run) {
				items := run.Items[:0]
				for _, item := range run.Items {
					if item.Kind != generated.AssistantRunItemKindFinalAnswer {
						items = append(items, item)
					}
				}
				run.Items = items
			},
		},
		{
			name: "corrupt_capsule",
			mutate: func(run *runruntime.Run) {
				for index := range run.Items {
					if run.Items[index].Kind == generated.AssistantRunItemKindFinalAnswer {
						run.Items[index].Payload["completionDigest"] = "sha256:" + strings.Repeat("0", 64)
					}
				}
			},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			base := newMemoryRunRepository()
			commands := workerCommandService(base)
			run, err := commands.Start(t.Context(), runruntime.StartCommand{
				UserID: "user-pair-corrupt-" + test.name, SessionID: "session-pair-corrupt",
				ClientRequestID: "request-pair-corrupt-" + test.name,
				InputText:       "持久完成后拒绝不一致目标",
			})
			if err != nil {
				t.Fatalf("start run: %v", err)
			}
			repository := &interruptAfterCommitRepository{
				memoryRunRepository: base,
				kind:                "answer_delta",
				state:               generated.AssistantRunStateExecuting,
			}
			queue := newMemoryWorkQueue()
			queue.enqueue(run.RunID)
			worker := runruntime.NewDurableWorker(
				repository, queue, &countingTerminalExecutor{}, "worker-pair-corrupt",
			)
			if worked, processErr := worker.ProcessNext(t.Context()); !worked || !errors.Is(processErr, errInjectedTerminalBoundary) {
				t.Fatalf("persist accepted pair: worked=%t err=%v", worked, processErr)
			}

			base.mu.Lock()
			corrupt := base.runs[run.RunID]
			test.mutate(&corrupt)
			base.runs[run.RunID] = corrupt
			base.mu.Unlock()

			if _, steerErr := commands.Steer(
				t.Context(), run.UserID, run.RunID,
				"steer-pair-corrupt-"+test.name, "不得把损坏完成事实当作尚未完成",
			); !errors.Is(steerErr, runruntime.ErrJournalCorrupt) {
				t.Fatalf("corrupt accepted pair did not fail closed: %v", steerErr)
			}
			if _, pauseErr := commands.Pause(
				t.Context(), run.UserID, run.RunID,
				"pause-pair-corrupt-"+test.name, "不得暂停损坏完成事实",
			); !errors.Is(pauseErr, runruntime.ErrJournalCorrupt) {
				t.Fatalf("corrupt accepted pair allowed pause: %v", pauseErr)
			}
		})
	}
}

var (
	errCompletionCapsuleAckLost    = errors.New("completion capsule commit acknowledgement lost")
	errCompletionBoundaryTransient = errors.New("completion boundary repository transient")
)

type completionBoundaryGapExecutor struct {
	mu          sync.Mutex
	commands    *runruntime.CommandService
	userID      string
	mode        string
	instruction string
	requests    []runruntime.ExecutionRequest
}

func (e *completionBoundaryGapExecutor) Execute(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	e.mu.Lock()
	e.requests = append(e.requests, request)
	call := len(e.requests)
	e.mu.Unlock()
	if call == 1 {
		if e.mode == "budget_only" {
			if err := emit(runruntime.ExecutionItemUpdate{
				Budget: &runruntime.BudgetConsumptionReceipt{
					Scope: request.IdempotencyPrefix, Sequence: request.BudgetReceiptSequence + 1,
					Consumption: runruntime.BudgetConsumption{Tokens: 1, CostUnits: 1},
				},
			}); err != nil {
				return runruntime.ExecutionResult{}, err
			}
		}
		if _, err := e.commands.Steer(
			ctx, e.userID, request.RunID,
			"completion-gap-steer-"+e.mode, e.instruction,
		); err != nil {
			return runruntime.ExecutionResult{}, err
		}
	}
	return completionBoundaryResult(request, true), nil
}

func (e *completionBoundaryGapExecutor) callCount() int {
	e.mu.Lock()
	defer e.mu.Unlock()
	return len(e.requests)
}

func (e *completionBoundaryGapExecutor) requestAt(index int) runruntime.ExecutionRequest {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.requests[index]
}

func (e *completionBoundaryGapExecutor) requestsSnapshot() []runruntime.ExecutionRequest {
	e.mu.Lock()
	defer e.mu.Unlock()
	return append([]runruntime.ExecutionRequest{}, e.requests...)
}

type completionRaceExecutor struct {
	mu          sync.Mutex
	requests    []runruntime.ExecutionRequest
	rejectFirst bool
}

type completionRecoveryTransientExecutor struct {
	mu       sync.Mutex
	commands *runruntime.CommandService
	userID   string
	calls    int
}

func (e *completionRecoveryTransientExecutor) Execute(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	_ func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	e.mu.Lock()
	e.calls++
	call := e.calls
	e.mu.Unlock()
	if call == 1 {
		if _, err := e.commands.Steer(
			ctx, e.userID, request.RunID,
			"steer-before-transient-recovery", "恢复时应用的新目标",
		); err != nil {
			return runruntime.ExecutionResult{}, err
		}
		return runruntime.ExecutionResult{}, runruntime.ErrExecutionReplanned
	}
	return completionBoundaryResult(request, true), nil
}

func (e *completionRecoveryTransientExecutor) callCount() int {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.calls
}

func (e *completionRaceExecutor) Execute(
	_ context.Context,
	request runruntime.ExecutionRequest,
	_ func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	e.mu.Lock()
	e.requests = append(e.requests, request)
	call := len(e.requests)
	e.mu.Unlock()
	return completionBoundaryResult(request, !e.rejectFirst || call > 1), nil
}

func (e *completionRaceExecutor) callCount() int {
	e.mu.Lock()
	defer e.mu.Unlock()
	return len(e.requests)
}

func completionBoundaryResult(
	request runruntime.ExecutionRequest,
	accepted bool,
) runruntime.ExecutionResult {
	if !accepted {
		return runruntime.ExecutionResult{}
	}
	answerRef := "assistant_run_item:answer:" + request.RunID
	return runruntime.ExecutionResult{
		AnswerText:   "completion boundary answer",
		ArtifactRefs: []string{answerRef},
		VerificationEvidence: []runruntime.VerificationEvidence{{
			Requirement: "answer_present", Passed: true,
			ArtifactRefs: []string{answerRef}, Summary: "bounded answer evidence",
			FixSuggestion: "regenerate for the revised goal",
		}},
	}
}

type completionCommitInterceptor struct {
	*memoryRunRepository
	before func(runruntime.Run, []runruntime.JournalEvent) error
	after  func(runruntime.Run, []runruntime.JournalEvent) error
}

type completionBoundaryFailureRepository struct {
	*memoryRunRepository
	mu        sync.Mutex
	failure   error
	remaining int
}

func (r *completionBoundaryFailureRepository) CommitClaim(
	ctx context.Context,
	claim runruntime.WorkClaim,
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	if completionCommitContainsGoalReplan(run, events) {
		r.mu.Lock()
		if r.remaining > 0 {
			r.remaining--
			failure := r.failure
			r.mu.Unlock()
			return failure
		}
		r.mu.Unlock()
	}
	return r.memoryRunRepository.CommitClaim(
		ctx, claim, expectedRevision, run, events, receipt,
	)
}

func (r *completionCommitInterceptor) CommitClaim(
	ctx context.Context,
	claim runruntime.WorkClaim,
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	if r.before != nil {
		if err := r.before(run, events); err != nil {
			return err
		}
	}
	if err := r.memoryRunRepository.CommitClaim(
		ctx, claim, expectedRevision, run, events, receipt,
	); err != nil {
		return err
	}
	if r.after != nil {
		return r.after(run, events)
	}
	return nil
}

func completionCommitContainsCapsule(
	run runruntime.Run,
	events []runruntime.JournalEvent,
) bool {
	if len(events) != 1 || events[0].Kind != "answer_delta" {
		return false
	}
	for _, item := range run.Items {
		if item.Kind == generated.AssistantRunItemKindFinalAnswer &&
			item.Status == generated.AssistantRunItemStatusCompleted {
			_, encoded := item.Payload["completionCapsule"].(string)
			_, digest := item.Payload["completionDigest"].(string)
			return encoded && digest
		}
	}
	return false
}

func completionCommitContainsRejectedVerdict(
	run runruntime.Run,
	events []runruntime.JournalEvent,
) bool {
	if len(events) != 1 || events[0].Kind != "process_commit" {
		return false
	}
	for _, item := range run.Items {
		if item.Kind == generated.AssistantRunItemKindEvidence &&
			item.Status == generated.AssistantRunItemStatusCompleted &&
			item.Payload["accepted"] == false {
			return true
		}
	}
	return false
}

func completionCommitContainsGoalReplan(
	run runruntime.Run,
	events []runruntime.JournalEvent,
) bool {
	if len(events) != 1 || events[0].Kind != "task_graph_patch" ||
		run.GoalRevision <= 1 || len(run.PendingSteer) != 0 {
		return false
	}
	wantID := "plan:" + run.RunID + ":goal:" + strconv.FormatInt(run.GoalRevision, 10)
	for _, item := range run.Items {
		if item.ItemID == wantID && item.Status == generated.AssistantRunItemStatusCompleted {
			return true
		}
	}
	return false
}

func terminalRunStateForTest(state generated.AssistantRunState) bool {
	return state == generated.AssistantRunStateCompleted ||
		state == generated.AssistantRunStateFailed ||
		state == generated.AssistantRunStateCancelled
}

func loadCompletionBoundaryRun(
	t *testing.T,
	repository *memoryRunRepository,
	runID string,
) runruntime.Run {
	t.Helper()
	run, err := repository.Load(t.Context(), runID)
	if err != nil {
		t.Fatalf("load completion boundary run: %v", err)
	}
	return run
}

func assertCompletionBoundaryReplanned(
	t *testing.T,
	run runruntime.Run,
	wantGoalRevision int64,
	wantAttempt int,
) {
	t.Helper()
	root := verifierRepairRootTask(t, run)
	if run.State != generated.AssistantRunStateExecuting ||
		run.GoalRevision != wantGoalRevision || len(run.PendingSteer) != 0 ||
		root.Attempt != wantAttempt ||
		root.Status != generated.AssistantTaskStatusRunning {
		t.Fatalf("completion boundary did not durably replan: run=%#v root=%#v", run, root)
	}
	wantPlanID := "plan:" + run.RunID + ":goal:2"
	for _, item := range run.Items {
		if item.ItemID == wantPlanID &&
			item.Status == generated.AssistantRunItemStatusCompleted {
			return
		}
	}
	t.Fatalf("goal revision plan audit missing: %#v", run.Items)
}

func assertNoCompletionFacts(t *testing.T, run runruntime.Run) {
	t.Helper()
	for _, item := range run.Items {
		if item.Kind == generated.AssistantRunItemKindEvidence ||
			item.Kind == generated.AssistantRunItemKindFinalAnswer {
			t.Fatalf("old completion facts persisted after steer: %#v", item)
		}
	}
}

func assertNoCompletionCapsule(t *testing.T, run runruntime.Run) {
	t.Helper()
	for _, item := range run.Items {
		if _, found := item.Payload["completionCapsule"]; found {
			t.Fatalf("old completion capsule persisted after steer: %#v", item)
		}
	}
}

func assertAcceptedCompletionPair(t *testing.T, run runruntime.Run) {
	t.Helper()
	verdictFound, capsuleFound := false, false
	for _, item := range run.Items {
		if item.Kind == generated.AssistantRunItemKindEvidence &&
			item.Payload["accepted"] == true {
			verdictFound = true
			if payloadInteger(item.Payload["goalRevision"]) != int(run.GoalRevision) ||
				!validTestSHA256(item.Payload["protectedRunFactsDigest"]) {
				t.Fatalf("accepted verdict is not bound to protected facts: %#v", item.Payload)
			}
		}
		if _, found := item.Payload["completionCapsule"]; found {
			capsuleFound = true
		}
	}
	if !verdictFound || !capsuleFound {
		t.Fatalf("accepted verdict/capsule pair is incomplete: %#v", run.Items)
	}
}

func payloadInteger(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	default:
		return 0
	}
}

func validTestSHA256(value any) bool {
	digest, ok := value.(string)
	return ok && len(digest) == len("sha256:")+64 &&
		strings.HasPrefix(digest, "sha256:")
}
