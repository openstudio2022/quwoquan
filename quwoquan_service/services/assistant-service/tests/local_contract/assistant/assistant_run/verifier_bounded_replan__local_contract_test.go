// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
package assistant_run_test

import (
	"context"
	"encoding/json"
	"errors"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	orchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

func TestVerifierRepairKeepsGoalFrozenAndCompletesOnSecondAttempt(t *testing.T) {
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	run := startVerifierRepairRun(
		t,
		repository,
		generated.AssistantReasoningProfileBalanced,
		"verifier-repair-pass",
	)
	originalDefinition := runruntime.DefinitionOfDone{
		Outcome:                  run.DefinitionOfDone.Outcome,
		Constraints:              append([]string(nil), run.DefinitionOfDone.Constraints...),
		VerificationRequirements: append([]string(nil), run.DefinitionOfDone.VerificationRequirements...),
		FrozenAt:                 run.DefinitionOfDone.FrozenAt,
	}
	originalGoalHistory := append([]runruntime.GoalRevision(nil), run.GoalHistory...)
	executor := &verifierSequenceExecutor{budgetPerCall: 100}
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository,
		queue,
		executor,
		"worker-verifier-repair-pass",
	)

	if worked, err := worker.ProcessNext(context.Background()); err != nil || !worked {
		t.Fatalf("first verifier attempt: worked=%t err=%v", worked, err)
	}
	repairing := loadVerifierRepairRun(t, repository, run.RunID)
	root := verifierRepairRootTask(t, repairing)
	if repairing.State != generated.AssistantRunStateExecuting || root.Attempt != 2 ||
		root.Status != generated.AssistantTaskStatusRunning ||
		root.Verification.Passed || root.Verification.Summary == "" ||
		!strings.HasPrefix(root.BlockReason, "verification_rejected:") {
		t.Fatalf("first rejection was not durably requeued: run=%#v root=%#v", repairing, root)
	}
	if repairing.GoalRevision != 1 ||
		!sameVerifierGoalHistory(repairing.GoalHistory, originalGoalHistory) ||
		!sameVerifierDefinition(repairing.DefinitionOfDone, originalDefinition) ||
		len(repairing.PendingSteer) != 0 {
		t.Fatalf("verifier repair mutated frozen goal facts: %#v", repairing)
	}
	item := verifierItemForAttempt(t, repairing, 1)
	fingerprint, ok := item.Payload["failureFingerprint"].(string)
	if !ok || len(fingerprint) != 64 ||
		item.Payload["accepted"] != false || payloadAttempt(item.Payload) != 1 {
		t.Fatalf("authoritative verifier audit is incomplete: %#v", item)
	}
	contextSummary := orchestration.ProjectVerificationRepairContextSummary(
		repairing.RunID,
		nil,
		repairing.TaskGraph,
	)
	if contextSummary == nil ||
		!strings.Contains(contextSummary.Text, "系统验证修复约束") ||
		!strings.Contains(contextSummary.Text, root.Verification.Summary) {
		t.Fatalf("repair constraint did not enter trusted context: %#v", contextSummary)
	}

	if worked, err := worker.ProcessNext(context.Background()); err != nil || !worked {
		t.Fatalf("second verifier attempt: worked=%t err=%v", worked, err)
	}
	completed := loadVerifierRepairRun(t, repository, run.RunID)
	root = verifierRepairRootTask(t, completed)
	requests := executor.snapshotRequests()
	if len(requests) != 2 || requests[0].Goal != requests[1].Goal ||
		requests[0].Goal != run.InputText ||
		!strings.HasSuffix(
			requests[1].IdempotencyPrefix,
			":task:task_root:attempt:2",
		) || requests[0].IdempotencyPrefix == requests[1].IdempotencyPrefix {
		t.Fatalf("repair request changed goal or reused attempt scope: %#v", requests)
	}
	if runruntime.ContextProgressScope(repairing) != requests[1].IdempotencyPrefix ||
		requests[1].BudgetConsumption.Tokens != 100 ||
		requests[1].BudgetConsumption.CostUnits != 100 ||
		requests[1].BudgetReceiptSequence != 0 || completed.Checkpoint == nil ||
		completed.Checkpoint.BudgetConsumption.Tokens != 200 ||
		completed.Checkpoint.BudgetConsumption.CostUnits != 200 ||
		completed.Checkpoint.BudgetReceiptScope != requests[1].IdempotencyPrefix {
		t.Fatalf("attempt receipt scope reset cumulative budget: requests=%#v run=%#v", requests, completed)
	}
	if completed.State != generated.AssistantRunStateCompleted ||
		root.Attempt != 2 || !root.Verification.Passed || root.BlockReason != "" ||
		completed.GoalRevision != 1 ||
		!sameVerifierGoalHistory(completed.GoalHistory, originalGoalHistory) ||
		!sameVerifierDefinition(completed.DefinitionOfDone, originalDefinition) {
		t.Fatalf("accepted repair did not close cleanly: run=%#v root=%#v", completed, root)
	}
}

func TestVerifierRepairStopsAtSameFailureFingerprint(t *testing.T) {
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	run := startVerifierRepairRun(
		t,
		repository,
		generated.AssistantReasoningProfileBalanced,
		"verifier-repair-no-progress",
	)
	executor := &verifierSequenceExecutor{alwaysReject: true}
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository,
		queue,
		executor,
		"worker-verifier-repair-no-progress",
	)
	for attempt := 0; attempt < 2; attempt++ {
		if worked, err := worker.ProcessNext(context.Background()); err != nil || !worked {
			t.Fatalf("process verifier attempt %d: worked=%t err=%v", attempt+1, worked, err)
		}
	}
	failed := loadVerifierRepairRun(t, repository, run.RunID)
	first := verifierItemForAttempt(t, failed, 1)
	second := verifierItemForAttempt(t, failed, 2)
	if failed.State != generated.AssistantRunStateFailed ||
		failed.TerminalReason != "verification_no_progress" ||
		executor.callCount() != 2 ||
		first.Payload["failureFingerprint"] != second.Payload["failureFingerprint"] {
		t.Fatalf("same verifier gap was not stopped: run=%#v items=%#v", failed, failed.Items)
	}
	if worked, err := worker.ProcessNext(context.Background()); err != nil || worked {
		t.Fatalf("terminal verifier run was claimed again: worked=%t err=%v", worked, err)
	}
}

func TestVerifierRepairHonorsProfileAndBudgetBoundaries(t *testing.T) {
	t.Run("fast profile has no repair iteration", func(t *testing.T) {
		repository := newMemoryRunRepository()
		queue := newMemoryWorkQueue()
		run := startVerifierRepairRun(
			t,
			repository,
			generated.AssistantReasoningProfileFast,
			"verifier-repair-fast-cap",
		)
		executor := &verifierSequenceExecutor{alwaysReject: true}
		queue.enqueue(run.RunID)
		worker := runruntime.NewDurableWorker(
			repository,
			queue,
			executor,
			"worker-verifier-repair-fast-cap",
		)
		if worked, err := worker.ProcessNext(context.Background()); err != nil || !worked {
			t.Fatalf("process fast verifier: worked=%t err=%v", worked, err)
		}
		failed := loadVerifierRepairRun(t, repository, run.RunID)
		if failed.State != generated.AssistantRunStateFailed ||
			failed.TerminalReason != "verification_repair_exhausted" ||
			verifierRepairRootTask(t, failed).Attempt != 1 {
			t.Fatalf("fast verifier exceeded repair cap: %#v", failed)
		}
	})

	t.Run("cumulative token and cost exhaustion prevents repair", func(t *testing.T) {
		repository := newMemoryRunRepository()
		queue := newMemoryWorkQueue()
		run := startVerifierRepairRun(
			t,
			repository,
			generated.AssistantReasoningProfileBalanced,
			"verifier-repair-budget",
		)
		executor := &verifierSequenceExecutor{
			alwaysReject:  true,
			exhaustBudget: true,
		}
		queue.enqueue(run.RunID)
		worker := runruntime.NewDurableWorker(
			repository,
			queue,
			executor,
			"worker-verifier-repair-budget",
		)
		if worked, err := worker.ProcessNext(context.Background()); err != nil || !worked {
			t.Fatalf("process exhausted verifier: worked=%t err=%v", worked, err)
		}
		failed := loadVerifierRepairRun(t, repository, run.RunID)
		if failed.State != generated.AssistantRunStateFailed ||
			failed.TerminalReason != "verification_budget_exhausted" ||
			failed.Checkpoint == nil ||
			failed.Checkpoint.BudgetConsumption.Tokens !=
				failed.ReasoningPolicy.Budget.MaxTokens ||
			failed.Checkpoint.BudgetConsumption.CostUnits !=
				failed.ReasoningPolicy.Budget.MaxCostUnits {
			t.Fatalf("budget exhaustion did not remain cumulative: %#v", failed)
		}
	})

	t.Run("deadline crossing during verification prevents repair", func(t *testing.T) {
		repository := newMemoryRunRepository()
		queue := newMemoryWorkQueue()
		run := startVerifierRepairRun(
			t,
			repository,
			generated.AssistantReasoningProfileBalanced,
			"verifier-repair-deadline",
		)
		executor := &verifierSequenceExecutor{waitForDeadline: true, alwaysReject: true}
		profiles := verifierProfilesWithBalancedDeadline(t, 15*time.Millisecond)
		hooks, err := runruntime.NewHookRegistry()
		if err != nil {
			t.Fatalf("new hook registry: %v", err)
		}
		queue.enqueue(run.RunID)
		worker := runruntime.NewConfiguredDurableWorker(
			repository,
			queue,
			executor,
			"worker-verifier-repair-deadline",
			profiles,
			hooks,
		)
		if worked, err := worker.ProcessNext(context.Background()); err != nil || !worked {
			t.Fatalf("process deadline verifier: worked=%t err=%v", worked, err)
		}
		failed := loadVerifierRepairRun(t, repository, run.RunID)
		if failed.State != generated.AssistantRunStateFailed ||
			failed.TerminalReason != "verification_budget_exhausted" ||
			verifierRepairRootTask(t, failed).Attempt != 1 {
			t.Fatalf("deadline crossing incorrectly requeued: %#v", failed)
		}
	})
}

func TestVerifierVerdictSurvivesWorkerRestartBeforeRepairPatch(t *testing.T) {
	base := newMemoryRunRepository()
	repository := &failVerifierPatchRepository{memoryRunRepository: base}
	queue := newMemoryWorkQueue()
	run := startVerifierRepairRun(
		t,
		base,
		generated.AssistantReasoningProfileBalanced,
		"verifier-repair-restart",
	)
	executor := &verifierSequenceExecutor{}
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository,
		queue,
		executor,
		"worker-verifier-repair-restart-a",
	)
	worked, err := worker.ProcessNext(context.Background())
	if !worked || !errors.Is(err, errInjectedVerifierPatch) {
		t.Fatalf("inject patch interruption: worked=%t err=%v", worked, err)
	}
	interrupted := loadVerifierRepairRun(t, base, run.RunID)
	if verifierRepairRootTask(t, interrupted).Attempt != 1 ||
		interrupted.State != generated.AssistantRunStateExecuting {
		t.Fatalf("interruption did not stop after verdict commit: %#v", interrupted)
	}
	first := verifierItemForAttempt(t, interrupted, 1)
	if first.Payload["accepted"] != false {
		t.Fatalf("first authoritative verdict was not rejected: %#v", first)
	}

	worker = runruntime.NewDurableWorker(
		repository,
		queue,
		executor,
		"worker-verifier-repair-restart-b",
	)
	if worked, err = worker.ProcessNext(context.Background()); err != nil || !worked {
		t.Fatalf("recover persisted verdict: worked=%t err=%v", worked, err)
	}
	repairing := loadVerifierRepairRun(t, base, run.RunID)
	if repairing.State != generated.AssistantRunStateExecuting ||
		verifierRepairRootTask(t, repairing).Attempt != 2 ||
		verifierItemForAttempt(t, repairing, 1).Payload["accepted"] != false {
		t.Fatalf("restart overwrote authoritative verdict: %#v", repairing)
	}
	if executor.callCount() != 1 {
		t.Fatalf("restart re-executed tools before applying durable repair: calls=%d", executor.callCount())
	}
	if worked, err = worker.ProcessNext(context.Background()); err != nil || !worked {
		t.Fatalf("complete repaired run: worked=%t err=%v", worked, err)
	}
	completed := loadVerifierRepairRun(t, base, run.RunID)
	if completed.State != generated.AssistantRunStateCompleted ||
		executor.callCount() != 2 {
		t.Fatalf("restarted verifier run did not complete once repaired: %#v", completed)
	}
}

func TestDefaultReasoningProfilesBoundVerifierRepairIterations(t *testing.T) {
	catalog, err := runruntime.DefaultReasoningProfileCatalog()
	if err != nil {
		t.Fatalf("default reasoning profiles: %v", err)
	}
	want := map[generated.AssistantReasoningProfile]int{
		generated.AssistantReasoningProfileFast:           0,
		generated.AssistantReasoningProfileBalanced:       1,
		generated.AssistantReasoningProfileDeep:           2,
		generated.AssistantReasoningProfileBackgroundLong: 3,
	}
	configs := make([]runruntime.ReasoningProfileConfig, 0, len(want))
	for _, profile := range []generated.AssistantReasoningProfile{
		generated.AssistantReasoningProfileFast,
		generated.AssistantReasoningProfileBalanced,
		generated.AssistantReasoningProfileDeep,
		generated.AssistantReasoningProfileBackgroundLong,
	} {
		config, resolveErr := catalog.Resolve(profile)
		if resolveErr != nil || config.StopRules.MaxVerificationRepairs != want[profile] {
			t.Fatalf("profile %s repair cap=%d err=%v", profile, config.StopRules.MaxVerificationRepairs, resolveErr)
		}
		configs = append(configs, config)
	}
	configs[1].StopRules.MaxVerificationRepairs = -1
	if _, err := runruntime.NewReasoningProfileCatalog(configs); err == nil {
		t.Fatal("negative verifier repair cap was accepted")
	}
}

type verifierSequenceExecutor struct {
	mu              sync.Mutex
	requests        []runruntime.ExecutionRequest
	alwaysReject    bool
	exhaustBudget   bool
	waitForDeadline bool
	budgetPerCall   int64
}

func (e *verifierSequenceExecutor) Execute(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	e.mu.Lock()
	e.requests = append(e.requests, request)
	call := len(e.requests)
	e.mu.Unlock()
	if e.waitForDeadline {
		<-ctx.Done()
	}
	if e.exhaustBudget {
		if err := emit(runruntime.ExecutionItemUpdate{
			Budget: &runruntime.BudgetConsumptionReceipt{
				Scope:    request.IdempotencyPrefix,
				Sequence: request.BudgetReceiptSequence + 1,
				Consumption: runruntime.BudgetConsumption{
					Tokens:    request.ReasoningPolicy.Budget.MaxTokens,
					CostUnits: request.ReasoningPolicy.Budget.MaxCostUnits,
				},
			},
		}); err != nil {
			return runruntime.ExecutionResult{}, err
		}
	} else if e.budgetPerCall > 0 {
		if err := emit(runruntime.ExecutionItemUpdate{
			Budget: &runruntime.BudgetConsumptionReceipt{
				Scope:    request.IdempotencyPrefix,
				Sequence: request.BudgetReceiptSequence + 1,
				Consumption: runruntime.BudgetConsumption{
					Tokens:    e.budgetPerCall * int64(call),
					CostUnits: e.budgetPerCall * int64(call),
				},
			},
		}); err != nil {
			return runruntime.ExecutionResult{}, err
		}
	}
	if e.alwaysReject || call == 1 {
		return runruntime.ExecutionResult{}, nil
	}
	return (&successfulRunExecutor{}).Execute(ctx, request, emit)
}

func (e *verifierSequenceExecutor) snapshotRequests() []runruntime.ExecutionRequest {
	e.mu.Lock()
	defer e.mu.Unlock()
	return append([]runruntime.ExecutionRequest{}, e.requests...)
}

func (e *verifierSequenceExecutor) callCount() int {
	e.mu.Lock()
	defer e.mu.Unlock()
	return len(e.requests)
}

var errInjectedVerifierPatch = errors.New("injected verifier patch interruption")

type failVerifierPatchRepository struct {
	*memoryRunRepository
	mu     sync.Mutex
	failed bool
}

func (r *failVerifierPatchRepository) Load(
	ctx context.Context,
	runID string,
) (runruntime.Run, error) {
	run, err := r.memoryRunRepository.Load(ctx, runID)
	if err != nil {
		return runruntime.Run{}, err
	}
	return cloneVerifierRepairRun(run)
}

func (r *failVerifierPatchRepository) LoadByRequest(
	ctx context.Context,
	userID string,
	sessionID string,
	clientRequestID string,
) (runruntime.Run, error) {
	run, err := r.memoryRunRepository.LoadByRequest(
		ctx,
		userID,
		sessionID,
		clientRequestID,
	)
	if err != nil {
		return runruntime.Run{}, err
	}
	return cloneVerifierRepairRun(run)
}

func (r *failVerifierPatchRepository) Commit(
	ctx context.Context,
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if !r.failed && len(events) == 1 && events[0].Kind == "task_graph_patch" &&
		hasVerifierAttemptItem(run, 1) && verifierRepairRootTaskValue(run).Attempt == 2 {
		r.failed = true
		return errInjectedVerifierPatch
	}
	return r.memoryRunRepository.Commit(
		ctx,
		expectedRevision,
		run,
		events,
		receipt,
	)
}

func (r *failVerifierPatchRepository) CommitClaim(
	ctx context.Context,
	claim runruntime.WorkClaim,
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if !r.failed && len(events) == 1 && events[0].Kind == "task_graph_patch" &&
		hasVerifierAttemptItem(run, 1) && verifierRepairRootTaskValue(run).Attempt == 2 {
		r.failed = true
		return errInjectedVerifierPatch
	}
	return r.memoryRunRepository.CommitClaim(
		ctx,
		claim,
		expectedRevision,
		run,
		events,
		receipt,
	)
}

func cloneVerifierRepairRun(run runruntime.Run) (runruntime.Run, error) {
	encoded, err := json.Marshal(run)
	if err != nil {
		return runruntime.Run{}, err
	}
	var cloned runruntime.Run
	if err := json.Unmarshal(encoded, &cloned); err != nil {
		return runruntime.Run{}, err
	}
	return cloned, nil
}

func startVerifierRepairRun(
	t *testing.T,
	repository *memoryRunRepository,
	profile generated.AssistantReasoningProfile,
	suffix string,
) runruntime.Run {
	t.Helper()
	run, err := workerCommandService(repository).Start(
		context.Background(),
		runruntime.StartCommand{
			UserID:           "user-" + suffix,
			SessionID:        "session-" + suffix,
			ClientRequestID:  "request-" + suffix,
			InputText:        "保持原始目标并完成可验证答案",
			ReasoningProfile: profile,
		},
	)
	if err != nil {
		t.Fatalf("start verifier repair run: %v", err)
	}
	return run
}

func loadVerifierRepairRun(
	t *testing.T,
	repository *memoryRunRepository,
	runID string,
) runruntime.Run {
	t.Helper()
	run, err := repository.Load(context.Background(), runID)
	if err != nil {
		t.Fatalf("load verifier repair run: %v", err)
	}
	return run
}

func verifierRepairRootTask(t *testing.T, run runruntime.Run) runruntime.TaskNode {
	t.Helper()
	root := verifierRepairRootTaskValue(run)
	if root.TaskID == "" {
		t.Fatalf("root task missing: %#v", run.TaskGraph)
	}
	return root
}

func verifierRepairRootTaskValue(run runruntime.Run) runruntime.TaskNode {
	for _, task := range run.TaskGraph.Tasks {
		if task.TaskID == "task_root" {
			return task
		}
	}
	return runruntime.TaskNode{}
}

func verifierItemForAttempt(
	t *testing.T,
	run runruntime.Run,
	attempt int,
) runruntime.RunItem {
	t.Helper()
	want := "verification:" + run.RunID + ":task:task_root:attempt:" +
		strconv.Itoa(attempt)
	for _, item := range run.Items {
		if item.ItemID == want {
			return item
		}
	}
	t.Fatalf("verification item %q missing: %#v", want, run.Items)
	return runruntime.RunItem{}
}

func hasVerifierAttemptItem(run runruntime.Run, attempt int) bool {
	wantSuffix := ":task:task_root:attempt:" + strconv.Itoa(attempt)
	for _, item := range run.Items {
		if strings.HasSuffix(item.ItemID, wantSuffix) {
			return true
		}
	}
	return false
}

func payloadAttempt(payload map[string]any) int {
	switch value := payload["taskAttempt"].(type) {
	case int:
		return value
	case int64:
		return int(value)
	case float64:
		return int(value)
	default:
		return 0
	}
}

func sameVerifierDefinition(
	left runruntime.DefinitionOfDone,
	right runruntime.DefinitionOfDone,
) bool {
	return left.Outcome == right.Outcome && left.FrozenAt.Equal(right.FrozenAt) &&
		strings.Join(left.Constraints, "\x00") == strings.Join(right.Constraints, "\x00") &&
		strings.Join(left.VerificationRequirements, "\x00") ==
			strings.Join(right.VerificationRequirements, "\x00")
}

func sameVerifierGoalHistory(
	left []runruntime.GoalRevision,
	right []runruntime.GoalRevision,
) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}

func verifierProfilesWithBalancedDeadline(
	t *testing.T,
	duration time.Duration,
) *runruntime.ReasoningProfileCatalog {
	t.Helper()
	defaults, err := runruntime.DefaultReasoningProfileCatalog()
	if err != nil {
		t.Fatalf("default reasoning profiles: %v", err)
	}
	configs := make([]runruntime.ReasoningProfileConfig, 0, 4)
	for _, profile := range []generated.AssistantReasoningProfile{
		generated.AssistantReasoningProfileFast,
		generated.AssistantReasoningProfileBalanced,
		generated.AssistantReasoningProfileDeep,
		generated.AssistantReasoningProfileBackgroundLong,
	} {
		config, resolveErr := defaults.Resolve(profile)
		if resolveErr != nil {
			t.Fatalf("resolve reasoning profile %s: %v", profile, resolveErr)
		}
		if profile == generated.AssistantReasoningProfileBalanced {
			config.Budget.MaxDuration = duration
		}
		configs = append(configs, config)
	}
	catalog, err := runruntime.NewReasoningProfileCatalog(configs)
	if err != nil {
		t.Fatalf("deadline reasoning profiles: %v", err)
	}
	return catalog
}
