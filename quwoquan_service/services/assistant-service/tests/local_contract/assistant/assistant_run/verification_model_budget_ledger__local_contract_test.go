// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
package assistant_run_test

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

var errVerificationBudgetReceiptAckLost = errors.New(
	"verification budget receipt commit response lost",
)

type verificationBudgetCapabilityModel struct{}

func (verificationBudgetCapabilityModel) Complete(
	context.Context,
	orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	return orchestration.ModelResponse{}, errors.New(
		"device completion path unexpectedly invoked the execution model",
	)
}

func (verificationBudgetCapabilityModel) ModelExecutionCapabilities() orchestration.ModelExecutionCapabilities {
	return orchestration.ModelExecutionCapabilities{
		ToolCalling:     true,
		ParallelTools:   true,
		ReasoningEffort: true,
	}
}

type verificationBudgetStep struct {
	passed bool
	tokens int64
}

type verificationBudgetModel struct {
	mu    sync.Mutex
	steps []verificationBudgetStep
	calls int
}

func (model *verificationBudgetModel) VerifyRequirement(
	ctx context.Context,
	request runruntime.ConstrainedVerificationRequest,
) (runruntime.ConstrainedVerificationResponse, error) {
	model.mu.Lock()
	if model.calls >= len(model.steps) {
		model.mu.Unlock()
		return runruntime.ConstrainedVerificationResponse{}, errors.New(
			"unexpected constrained verification call",
		)
	}
	step := model.steps[model.calls]
	model.calls++
	model.mu.Unlock()

	if err := orchestration.ConsumeExecutionModelResponse(
		ctx,
		orchestration.ModelResponse{Usage: map[string]any{
			"totalTokens": step.tokens,
		}},
	); err != nil {
		return runruntime.ConstrainedVerificationResponse{}, err
	}
	artifactRefs := append([]string{}, request.ArtifactRefs...)
	if len(artifactRefs) > 1 {
		artifactRefs = artifactRefs[:1]
	}
	response := runruntime.ConstrainedVerificationResponse{
		Passed:       step.passed,
		ArtifactRefs: artifactRefs,
		Summary:      "constrained completion verification evaluated",
	}
	if !step.passed {
		response.FixSuggestion = "repair the public answer before retrying"
	}
	return response, nil
}

func (model *verificationBudgetModel) callCount() int {
	model.mu.Lock()
	defer model.mu.Unlock()
	return model.calls
}

type verificationBudgetProductionExecutor struct {
	inner *orchestration.DurableRunExecutor
	mu    sync.Mutex
	calls int
}

func newVerificationBudgetProductionExecutor() *verificationBudgetProductionExecutor {
	loop := orchestration.NewAgentLoop(
		nil,
		orchestration.ReactRuntime{Model: verificationBudgetCapabilityModel{}},
		time.Now,
	)
	return &verificationBudgetProductionExecutor{
		inner: orchestration.NewDurableRunExecutor(loop),
	}
}

func (*verificationBudgetProductionExecutor) VerifiesCompletionWithinExecutionBudget() bool {
	return true
}

func (executor *verificationBudgetProductionExecutor) Execute(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	executor.mu.Lock()
	executor.calls++
	executor.mu.Unlock()

	checkpoint := runruntime.Checkpoint{}
	if request.Checkpoint != nil {
		checkpoint = *request.Checkpoint
		checkpoint.DecisionSummary = append(
			[]string{},
			request.Checkpoint.DecisionSummary...,
		)
		checkpoint.DeviceActionReceipts = append(
			[]runruntime.DeviceActionExecutionReceipt{},
			request.Checkpoint.DeviceActionReceipts...,
		)
	}
	idempotencyKey := request.IdempotencyPrefix + ":device_completion"
	checkpoint.DecisionSummary = append(
		checkpoint.DecisionSummary,
		"device_action_completed:"+idempotencyKey,
	)
	checkpoint.DeviceActionReceipts = append(
		checkpoint.DeviceActionReceipts,
		runruntime.DeviceActionExecutionReceipt{
			Capability:     "calendar.read",
			IdempotencyKey: idempotencyKey,
			Outcome:        "completed",
			ExecutedAt:     time.Now().UTC(),
		},
	)
	request.Checkpoint = &checkpoint
	request.RequestedSkillID = ""
	return executor.inner.Execute(ctx, request, emit)
}

func (executor *verificationBudgetProductionExecutor) callCount() int {
	executor.mu.Lock()
	defer executor.mu.Unlock()
	return executor.calls
}

type verificationBudgetMissingCallbackExecutor struct{ calls int }

func (*verificationBudgetMissingCallbackExecutor) VerifiesCompletionWithinExecutionBudget() bool {
	return true
}

func (executor *verificationBudgetMissingCallbackExecutor) Execute(
	_ context.Context,
	request runruntime.ExecutionRequest,
	_ func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	executor.calls++
	answerRef := "assistant_run_item:answer:" + request.RunID
	return runruntime.ExecutionResult{
		AnswerText:   "unbudgeted completion must be rejected",
		ArtifactRefs: []string{answerRef},
	}, nil
}

type verificationBudgetAckLossRepository struct {
	*memoryRunRepository
	mu      sync.Mutex
	ackLost bool
}

func (repository *verificationBudgetAckLossRepository) CommitClaim(
	ctx context.Context,
	claim runruntime.WorkClaim,
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	if err := repository.memoryRunRepository.CommitClaim(
		ctx,
		claim,
		expectedRevision,
		run,
		events,
		receipt,
	); err != nil {
		return err
	}
	if run.Checkpoint == nil || run.Checkpoint.BudgetReceiptSeq <= 0 {
		return nil
	}
	repository.mu.Lock()
	defer repository.mu.Unlock()
	if repository.ackLost {
		return nil
	}
	repository.ackLost = true
	return errVerificationBudgetReceiptAckLost
}

func (repository *verificationBudgetAckLossRepository) lostAck() bool {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	return repository.ackLost
}

func TestVerificationModelUsageIsDurableAcrossVerdictsAndRestart(
	t *testing.T,
) {
	t.Run("production marker fails closed when callback is skipped", func(t *testing.T) {
		repository := newMemoryRunRepository()
		queue := newMemoryWorkQueue()
		model := &verificationBudgetModel{steps: []verificationBudgetStep{{
			passed: true,
			tokens: 11,
		}}}
		executor := &verificationBudgetMissingCallbackExecutor{}
		run := startVerificationBudgetRun(t, repository, "missing-callback")
		queue.enqueue(run.RunID)
		worker := newVerificationBudgetWorker(
			t,
			repository,
			queue,
			executor,
			model,
			"worker-verification-budget-missing-callback",
		)

		if worked, err := worker.ProcessNext(t.Context()); err != nil || !worked {
			t.Fatalf("process missing callback: worked=%t err=%v", worked, err)
		}
		failed := loadVerificationBudgetRun(t, repository, run.RunID)
		if failed.State != generated.AssistantRunStateFailed ||
			failed.TerminalReason !=
				"completion_verification_budget_ledger_missing" ||
			executor.calls != 1 || model.callCount() != 0 {
			t.Fatalf(
				"production executor silently bypassed budgeted verification: run=%#v executorCalls=%d modelCalls=%d",
				failed,
				executor.calls,
				model.callCount(),
			)
		}
	})

	t.Run("accepted receipt survives commit acknowledgement loss", func(t *testing.T) {
		base := newMemoryRunRepository()
		repository := &verificationBudgetAckLossRepository{
			memoryRunRepository: base,
		}
		queue := newMemoryWorkQueue()
		model := &verificationBudgetModel{steps: []verificationBudgetStep{{
			passed: true,
			tokens: 101,
		}}}
		executor := newVerificationBudgetProductionExecutor()
		run := startVerificationBudgetRun(t, base, "accepted-ack-loss")
		queue.enqueue(run.RunID)
		worker := newVerificationBudgetWorker(
			t,
			repository,
			queue,
			executor,
			model,
			"worker-verification-budget-accepted",
		)

		if worked, err := worker.ProcessNext(t.Context()); err != nil || !worked {
			t.Fatalf("process accepted verification: worked=%t err=%v", worked, err)
		}
		stored := loadVerificationBudgetRun(t, base, run.RunID)
		if stored.State != generated.AssistantRunStateCompleted ||
			stored.Checkpoint == nil ||
			stored.Checkpoint.BudgetConsumption.Tokens != 101 ||
			stored.Checkpoint.BudgetConsumption.CostUnits != 101 ||
			stored.Checkpoint.BudgetReceiptSeq != 1 ||
			model.callCount() != 1 || executor.callCount() != 1 ||
			!repository.lostAck() {
			t.Fatalf(
				"accepted verification was not exactly-once durable: run=%#v modelCalls=%d executorCalls=%d ackLost=%t",
				stored,
				model.callCount(),
				executor.callCount(),
				repository.lostAck(),
			)
		}
	})

	t.Run("rejected usage remains absolute across worker repair restart", func(t *testing.T) {
		repository := newMemoryRunRepository()
		queue := newMemoryWorkQueue()
		model := &verificationBudgetModel{steps: []verificationBudgetStep{
			{passed: false, tokens: 97},
			{passed: true, tokens: 103},
		}}
		executor := newVerificationBudgetProductionExecutor()
		run := startVerificationBudgetRun(t, repository, "repair-restart")
		queue.enqueue(run.RunID)
		firstWorker := newVerificationBudgetWorker(
			t,
			repository,
			queue,
			executor,
			model,
			"worker-verification-budget-repair-a",
		)

		if worked, err := firstWorker.ProcessNext(t.Context()); err != nil || !worked {
			t.Fatalf("process rejected verification: worked=%t err=%v", worked, err)
		}
		repairing := loadVerificationBudgetRun(t, repository, run.RunID)
		if repairing.State != generated.AssistantRunStateExecuting ||
			repairing.Checkpoint == nil ||
			repairing.Checkpoint.BudgetConsumption.Tokens != 97 ||
			repairing.Checkpoint.BudgetConsumption.CostUnits != 97 ||
			verifierRepairRootTask(t, repairing).Attempt != 2 ||
			model.callCount() != 1 || executor.callCount() != 1 {
			t.Fatalf(
				"rejected verification usage was not durably requeued: run=%#v modelCalls=%d executorCalls=%d",
				repairing,
				model.callCount(),
				executor.callCount(),
			)
		}

		restartedWorker := newVerificationBudgetWorker(
			t,
			repository,
			queue,
			executor,
			model,
			"worker-verification-budget-repair-b",
		)
		if worked, err := restartedWorker.ProcessNext(t.Context()); err != nil || !worked {
			t.Fatalf("process repaired verification: worked=%t err=%v", worked, err)
		}
		completed := loadVerificationBudgetRun(t, repository, run.RunID)
		if completed.State != generated.AssistantRunStateCompleted ||
			completed.Checkpoint == nil ||
			completed.Checkpoint.BudgetConsumption.Tokens != 200 ||
			completed.Checkpoint.BudgetConsumption.CostUnits != 200 ||
			completed.Checkpoint.BudgetReceiptSeq != 1 ||
			!strings.HasSuffix(
				completed.Checkpoint.BudgetReceiptScope,
				":task:task_root:attempt:2",
			) || model.callCount() != 2 || executor.callCount() != 2 {
			t.Fatalf(
				"repair restart reset or omitted absolute usage: run=%#v modelCalls=%d executorCalls=%d",
				completed,
				model.callCount(),
				executor.callCount(),
			)
		}
	})

	t.Run("verification overrun fails terminal without executor requeue", func(t *testing.T) {
		repository := newMemoryRunRepository()
		queue := newMemoryWorkQueue()
		model := &verificationBudgetModel{steps: []verificationBudgetStep{{
			passed: true,
			tokens: 1_000_000,
		}}}
		executor := newVerificationBudgetProductionExecutor()
		run := startVerificationBudgetRun(t, repository, "terminal-overrun")
		queue.enqueue(run.RunID)
		worker := newVerificationBudgetWorker(
			t,
			repository,
			queue,
			executor,
			model,
			"worker-verification-budget-overrun",
		)

		if worked, err := worker.ProcessNext(t.Context()); err != nil || !worked {
			t.Fatalf("process verification overrun: worked=%t err=%v", worked, err)
		}
		failed := loadVerificationBudgetRun(t, repository, run.RunID)
		if failed.State != generated.AssistantRunStateFailed ||
			failed.TerminalReason != "verification_budget_exhausted" ||
			failed.Checkpoint == nil ||
			failed.Checkpoint.BudgetConsumption.Tokens != 1_000_000 ||
			failed.Checkpoint.BudgetConsumption.CostUnits != 1_000_000 ||
			failed.Checkpoint.RemainingBudget["tokens"] != 0 ||
			failed.Checkpoint.RemainingBudget["costUnits"] != 0 ||
			model.callCount() != 1 || executor.callCount() != 1 {
			t.Fatalf(
				"verification overrun was not terminal and durable: run=%#v modelCalls=%d executorCalls=%d",
				failed,
				model.callCount(),
				executor.callCount(),
			)
		}
		if worked, err := worker.ProcessNext(t.Context()); err != nil || worked ||
			model.callCount() != 1 || executor.callCount() != 1 {
			t.Fatalf(
				"terminal overrun was requeued: worked=%t err=%v modelCalls=%d executorCalls=%d",
				worked,
				err,
				model.callCount(),
				executor.callCount(),
			)
		}
	})
}

func startVerificationBudgetRun(
	t *testing.T,
	repository *memoryRunRepository,
	suffix string,
) runruntime.Run {
	t.Helper()
	run, err := workerCommandService(repository).Start(
		t.Context(),
		runruntime.StartCommand{
			UserID:          "user-verification-budget-" + suffix,
			SessionID:       "session-verification-budget-" + suffix,
			ClientRequestID: "request-verification-budget-" + suffix,
			InputText:       "完成公开答案并接受受限模型核验",
			DefinitionOfDone: runruntime.DefinitionOfDone{
				Outcome: "公开答案满足冻结目标",
				VerificationRequirements: []string{
					"answer_satisfies_user_goal",
				},
			},
		},
	)
	if err != nil {
		t.Fatalf("start verification budget run: %v", err)
	}
	return run
}

func newVerificationBudgetWorker(
	t *testing.T,
	repository runruntime.WorkerRepository,
	queue runruntime.WorkQueue,
	executor runruntime.RunExecutor,
	model runruntime.ConstrainedVerificationModel,
	workerID string,
) *runruntime.DurableWorker {
	t.Helper()
	profiles, err := runruntime.DefaultReasoningProfileCatalog()
	if err != nil {
		t.Fatalf("default reasoning profiles: %v", err)
	}
	hooks, err := runruntime.NewProductionHookRegistry(
		model,
		runruntime.HookAuditSinkFunc(func(
			context.Context,
			runruntime.HookAuditRecord,
		) error {
			return nil
		}),
	)
	if err != nil {
		t.Fatalf("production hook registry: %v", err)
	}
	return runruntime.NewConfiguredDurableWorker(
		repository,
		queue,
		executor,
		workerID,
		profiles,
		hooks,
	)
}

func loadVerificationBudgetRun(
	t *testing.T,
	repository *memoryRunRepository,
	runID string,
) runruntime.Run {
	t.Helper()
	run, err := repository.Load(t.Context(), runID)
	if err != nil {
		t.Fatalf("load verification budget run: %v", err)
	}
	return run
}

var _ runruntime.InExecutionCompletionVerifier = (*orchestration.DurableRunExecutor)(nil)
var _ runruntime.InExecutionCompletionVerifier = (*verificationBudgetProductionExecutor)(nil)
var _ runruntime.InExecutionCompletionVerifier = (*verificationBudgetMissingCallbackExecutor)(nil)
var _ runruntime.WorkerRepository = (*verificationBudgetAckLossRepository)(nil)
