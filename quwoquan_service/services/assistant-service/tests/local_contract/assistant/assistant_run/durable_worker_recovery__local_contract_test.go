// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
package assistant_run_test

import (
	"context"
	"sync"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

func TestDurableWorkerPersistsTypedItemsAndVerifiedTerminalSnapshot(t *testing.T) {
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	commands := workerCommandService(repository)
	run, err := commands.Start(context.Background(), runruntime.StartCommand{
		UserID:          "user-worker",
		SessionID:       "session-worker",
		ClientRequestID: "request-worker-complete",
		InputText:       "核对证据并给出答案",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository,
		queue,
		&successfulRunExecutor{},
		"worker-a",
	)
	worked, err := worker.ProcessNext(context.Background())
	if err != nil || !worked {
		t.Fatalf("process run: worked=%t err=%v", worked, err)
	}
	stored, err := repository.Load(context.Background(), run.RunID)
	if err != nil {
		t.Fatalf("load completed run: %v", err)
	}
	if stored.State != generated.AssistantRunStateCompleted ||
		stored.CompletedAt == nil ||
		stored.TerminalSnapshot["answerText"] != "可回查答案" {
		t.Fatalf("unexpected terminal run: %#v", stored)
	}
	selectedPolicy, ok := stored.TerminalSnapshot["selectedPolicyRef"].(map[string]any)
	if !ok || selectedPolicy["releaseDigest"] != stored.FrozenPolicySelection.ReleaseDigest {
		t.Fatalf("terminal selectedPolicyRef=%#v", selectedPolicy)
	}
	if _, leaked := stored.TerminalSnapshot["presentationDocument"]; leaked {
		t.Fatalf("terminal snapshot leaked presentation document: %#v", stored.TerminalSnapshot)
	}
	presentation := stored.PresentationDocument
	if presentation["revision"] != int64(2) ||
		stored.PresentationDocument["committedAt"] == "" {
		t.Fatalf("run presentation was not committed: %#v", stored)
	}
	if !stored.TaskGraph.AllCompleted() {
		t.Fatalf("task graph was not completed: %#v", stored.TaskGraph)
	}
	toolStarted := 0
	toolClosed := 0
	for _, item := range stored.Items {
		if item.Kind != generated.AssistantRunItemKindToolUse {
			continue
		}
		toolStarted++
		if item.Status == generated.AssistantRunItemStatusCompleted &&
			!item.CompletedAt.IsZero() {
			toolClosed++
		}
	}
	if toolStarted != 1 || toolClosed != 1 {
		t.Fatalf("tool lifecycle is not closed: %#v", stored.Items)
	}
	events, err := repository.EventsAfter(
		context.Background(),
		run.RunID,
		0,
		128,
	)
	if err != nil {
		t.Fatalf("read worker journal: %v", err)
	}
	if int64(len(events)) != stored.JournalSequence {
		t.Fatalf(
			"journal head mismatch: events=%d head=%d",
			len(events),
			stored.JournalSequence,
		)
	}
	for index, event := range events {
		if event.Sequence != int64(index+1) {
			t.Fatalf("journal gap at %d: %#v", index, events)
		}
	}
	presentationEvents := []string{}
	for _, event := range events {
		if event.Kind == "presentation_snapshot" ||
			event.Kind == "presentation_commit" {
			presentationEvents = append(presentationEvents, event.Kind)
		}
	}
	if len(presentationEvents) != 2 ||
		presentationEvents[0] != "presentation_snapshot" ||
		presentationEvents[1] != "presentation_commit" {
		t.Fatalf("presentation event lifecycle=%v", presentationEvents)
	}
}

func TestManagedExecutorCancelsAgentLoopBeforeTerminalRun(t *testing.T) {
	now := time.Now().UTC()
	repository := newMemoryRunRepository()
	run, err := workerCommandService(repository).Start(
		context.Background(),
		runruntime.StartCommand{
			UserID:          "user-worker",
			SessionID:       "session-worker",
			ClientRequestID: "request-cancel-managed",
			InputText:       "取消长任务",
		},
	)
	if err != nil {
		t.Fatalf("new run: %v", err)
	}
	if err := run.TaskGraph.Start("task_root"); err != nil {
		t.Fatalf("start root task: %v", err)
	}
	if err := run.BeginItem(
		"tool-active",
		generated.AssistantRunItemKindToolUse,
		"task_root",
		"正在执行工具",
		nil,
		now,
	); err != nil {
		t.Fatalf("begin active tool: %v", err)
	}

	delegate := &cancellableRunExecutor{started: make(chan struct{})}
	managed := runruntime.NewManagedRunExecutor(delegate)
	executionResult := make(chan error, 1)
	go func() {
		_, executeErr := managed.Execute(
			context.Background(),
			runruntime.ExecutionRequest{
				RunID:             run.RunID,
				Goal:              run.InputText,
				IdempotencyPrefix: "run-cancel-managed",
			},
			func(runruntime.ExecutionItemUpdate) error { return nil },
		)
		executionResult <- executeErr
	}()
	select {
	case <-delegate.started:
	case <-time.After(time.Second):
		t.Fatal("managed executor did not start")
	}

	coordinator := runruntime.NewCancellationCoordinator(managed, time.Second)
	if err := coordinator.Cancel(
		context.Background(),
		&run,
		"user_cancelled",
		now.Add(time.Second),
	); err != nil {
		t.Fatalf("cancel managed run: %v", err)
	}
	if executeErr := <-executionResult; executeErr != runruntime.ErrExecutionCancelled {
		t.Fatalf("execute error=%v want ErrExecutionCancelled", executeErr)
	}
	if run.State != generated.AssistantRunStateCancelled {
		t.Fatalf("run state=%s want cancelled", run.State)
	}
	for _, item := range run.Items {
		if item.Status == generated.AssistantRunItemStatusStarted {
			t.Fatalf("terminal run retained active item: %#v", run.Items)
		}
	}
}

func TestDurableWorkerCheckpointsPauseAndAnotherWorkerResumes(t *testing.T) {
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	commands := workerCommandService(repository)
	run, err := commands.Start(context.Background(), runruntime.StartCommand{
		UserID:          "user-worker",
		SessionID:       "session-worker",
		ClientRequestID: "request-worker-pause",
		InputText:       "执行可恢复长任务",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	queue.enqueue(run.RunID)
	blocking := &blockingRunExecutor{
		started: make(chan struct{}),
	}
	firstWorker := runruntime.NewDurableWorker(
		repository,
		queue,
		blocking,
		"worker-first",
	)
	firstDone := make(chan error, 1)
	go func() {
		_, processErr := firstWorker.ProcessNext(context.Background())
		firstDone <- processErr
	}()
	select {
	case <-blocking.started:
	case <-time.After(3 * time.Second):
		t.Fatal("first worker did not begin execution")
	}
	if _, err := commands.Pause(
		context.Background(),
		"user-worker",
		run.RunID,
		"pause-worker-run",
		"user_requested",
	); err != nil {
		t.Fatalf("request pause: %v", err)
	}
	select {
	case err := <-firstDone:
		if err != nil {
			t.Fatalf("checkpoint pause: %v", err)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("worker did not converge to paused")
	}
	paused, err := repository.Load(context.Background(), run.RunID)
	if err != nil {
		t.Fatalf("load paused run: %v", err)
	}
	if paused.State != generated.AssistantRunStatePaused ||
		paused.Checkpoint == nil {
		t.Fatalf("pause did not persist checkpoint: %#v", paused)
	}
	resumed, err := commands.Resume(
		context.Background(),
		"user-worker",
		run.RunID,
		"resume-worker-run",
	)
	if err != nil {
		t.Fatalf("resume run: %v", err)
	}
	queue.enqueue(resumed.RunID)
	secondWorker := runruntime.NewDurableWorker(
		repository,
		queue,
		&successfulRunExecutor{},
		"worker-second",
	)
	if worked, err := secondWorker.ProcessNext(context.Background()); err != nil ||
		!worked {
		t.Fatalf("second worker resume: worked=%t err=%v", worked, err)
	}
	completed, err := repository.Load(context.Background(), run.RunID)
	if err != nil {
		t.Fatalf("load resumed run: %v", err)
	}
	if completed.State != generated.AssistantRunStateCompleted ||
		completed.Checkpoint == nil {
		t.Fatalf("resumed run did not complete from checkpoint: %#v", completed)
	}
}

func workerCommandService(
	repository *memoryRunRepository,
) *runruntime.CommandService {
	return runruntime.NewCommandService(
		repository,
		runruntime.SessionAuthorizerFunc(func(
			context.Context,
			string,
			string,
		) error {
			return nil
		}),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		time.Now,
		nil,
		testPolicyResolver(),
	)
}

type successfulRunExecutor struct{}

func (e *successfulRunExecutor) Execute(
	_ context.Context,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	itemID := request.IdempotencyPrefix + ":tool:web_search:1"
	if err := emit(runruntime.ExecutionItemUpdate{
		ItemID:  itemID,
		Kind:    generated.AssistantRunItemKindToolUse,
		Status:  generated.AssistantRunItemStatusStarted,
		TaskID:  "task_root",
		Summary: "检索公开证据",
		Payload: map[string]any{"toolName": "web_search"},
	}); err != nil {
		return runruntime.ExecutionResult{}, err
	}
	if err := emit(runruntime.ExecutionItemUpdate{
		ItemID:       itemID,
		Kind:         generated.AssistantRunItemKindToolUse,
		Status:       generated.AssistantRunItemStatusCompleted,
		TaskID:       "task_root",
		Summary:      "公开证据已验证",
		ArtifactRefs: []string{"artifact:web:1"},
	}); err != nil {
		return runruntime.ExecutionResult{}, err
	}
	return runruntime.ExecutionResult{
		AnswerText:   "可回查答案",
		Processes:    []map[string]any{},
		ArtifactRefs: []string{"artifact:web:1"},
		EvidenceRefs: []string{"source:web:1"},
		Presentation: map[string]any{
			"templateRef":       "assistant.answer.default@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			"templateDigest":    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			"revision":          int64(1),
			"rootNodeId":        "root",
			"nodes":             []map[string]any{{"nodeId": "root", "kind": "markdown", "body": "可回查答案"}},
			"dataDigest":        "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
			"selectedVariant":   "standard",
			"fallbackMarkdown":  "可回查答案",
			"fallbackPlainText": "可回查答案",
			"committedAt":       "",
		},
		Verified:            true,
		VerificationSummary: "证据与答案一致",
	}, nil
}

type blockingRunExecutor struct {
	once    sync.Once
	started chan struct{}
}

type cancellableRunExecutor struct {
	started chan struct{}
}

func (e *cancellableRunExecutor) Execute(
	ctx context.Context,
	_ runruntime.ExecutionRequest,
	_ func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	close(e.started)
	<-ctx.Done()
	return runruntime.ExecutionResult{}, ctx.Err()
}

func (e *blockingRunExecutor) Execute(
	ctx context.Context,
	_ runruntime.ExecutionRequest,
	_ func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	e.once.Do(func() { close(e.started) })
	<-ctx.Done()
	return runruntime.ExecutionResult{}, ctx.Err()
}

type memoryWorkQueue struct {
	mu      sync.Mutex
	ready   []string
	claims  map[string]runruntime.WorkClaim
	fencing int64
}

func newMemoryWorkQueue() *memoryWorkQueue {
	return &memoryWorkQueue{claims: map[string]runruntime.WorkClaim{}}
}

func (q *memoryWorkQueue) enqueue(runID string) {
	q.mu.Lock()
	defer q.mu.Unlock()
	for _, ready := range q.ready {
		if ready == runID {
			return
		}
	}
	q.ready = append(q.ready, runID)
}

func (q *memoryWorkQueue) ClaimNext(
	_ context.Context,
	workerID string,
	ttl time.Duration,
) (runruntime.WorkClaim, error) {
	q.mu.Lock()
	defer q.mu.Unlock()
	if len(q.ready) == 0 {
		return runruntime.WorkClaim{}, runruntime.ErrNoWork
	}
	runID := q.ready[0]
	q.ready = q.ready[1:]
	q.fencing++
	now := time.Now().UTC()
	claim := runruntime.WorkClaim{
		RunID:        runID,
		WorkerID:     workerID,
		FencingToken: q.fencing,
		ClaimedAt:    now,
		ExpiresAt:    now.Add(ttl),
	}
	q.claims[runID] = claim
	return claim, nil
}

func (q *memoryWorkQueue) HeartbeatClaim(
	_ context.Context,
	claim runruntime.WorkClaim,
	ttl time.Duration,
) (runruntime.WorkClaim, error) {
	q.mu.Lock()
	defer q.mu.Unlock()
	current, ok := q.claims[claim.RunID]
	if !ok || current.WorkerID != claim.WorkerID ||
		current.FencingToken != claim.FencingToken {
		return runruntime.WorkClaim{}, runruntime.ErrLeaseConflict
	}
	current.ExpiresAt = time.Now().UTC().Add(ttl)
	q.claims[claim.RunID] = current
	return current, nil
}

func (q *memoryWorkQueue) CompleteClaim(
	_ context.Context,
	claim runruntime.WorkClaim,
	reschedule bool,
	_ time.Time,
) error {
	q.mu.Lock()
	defer q.mu.Unlock()
	current, ok := q.claims[claim.RunID]
	if !ok || current.WorkerID != claim.WorkerID ||
		current.FencingToken != claim.FencingToken {
		return runruntime.ErrLeaseConflict
	}
	delete(q.claims, claim.RunID)
	if reschedule {
		q.ready = append(q.ready, claim.RunID)
	}
	return nil
}

var _ runruntime.WorkQueue = (*memoryWorkQueue)(nil)
var _ runruntime.WorkerRepository = (*memoryRunRepository)(nil)
