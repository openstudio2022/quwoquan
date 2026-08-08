// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
package assistant_run_test

import (
	"context"
	"strings"
	"sync"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
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
		stored.TerminalSnapshot == nil ||
		stored.TerminalSnapshot.AnswerText != "可回查答案" {
		t.Fatalf("unexpected terminal run: %#v", stored)
	}
	if stored.TerminalSnapshot.SelectedPolicyRef == nil ||
		stored.TerminalSnapshot.SelectedPolicyRef.ReleaseDigest !=
			stored.FrozenPolicySelection.ReleaseDigest {
		t.Fatalf("terminal selectedPolicyRef=%#v", stored.TerminalSnapshot.SelectedPolicyRef)
	}
	if len(stored.TerminalSnapshot.Processes) != 1 ||
		stored.TerminalSnapshot.Processes[0].ProcessID != "process:web:1" ||
		len(stored.TerminalSnapshot.Processes[0].AcceptedReferences) != 1 ||
		stored.TerminalSnapshot.Processes[0].AcceptedReferences[0].SourceID != "source:web:1" {
		t.Fatalf("terminal typed processes=%#v", stored.TerminalSnapshot.Processes)
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
	completedEvent := events[len(events)-1]
	terminalProcesses, ok := completedEvent.Payload["processes"].([]assistantmodel.AssistantRunVisibleProcess)
	if !ok || len(terminalProcesses) != 1 ||
		terminalProcesses[0].ProcessID != "process:web:1" {
		t.Fatalf("terminal journal payload is not typed: %#v", completedEvent.Payload)
	}
	presentationEvents := []string{}
	var presentationSnapshot, presentationCommit *runruntime.JournalEvent
	for _, event := range events {
		if event.Kind == "presentation_snapshot" ||
			event.Kind == "presentation_commit" {
			presentationEvents = append(presentationEvents, event.Kind)
			eventCopy := event
			if event.Kind == "presentation_snapshot" {
				presentationSnapshot = &eventCopy
			} else {
				presentationCommit = &eventCopy
			}
		}
	}
	if len(presentationEvents) != 2 ||
		presentationEvents[0] != "presentation_snapshot" ||
		presentationEvents[1] != "presentation_commit" {
		t.Fatalf("presentation event lifecycle=%v", presentationEvents)
	}
	if presentationSnapshot == nil || presentationCommit == nil {
		t.Fatalf("presentation events were not captured: %v", presentationEvents)
	}
	snapshotDocument, ok := presentationSnapshot.Payload["document"].(map[string]any)
	if !ok || stringFieldForTest(snapshotDocument, "committedAt") != "" {
		t.Fatalf("presentation snapshot must remain uncommitted: %#v", presentationSnapshot.Payload)
	}
	committedAt := stringFieldForTest(presentationCommit.Payload, "committedAt")
	if _, err := time.Parse(time.RFC3339Nano, committedAt); err != nil ||
		committedAt != stringFieldForTest(stored.PresentationDocument, "committedAt") {
		t.Fatalf(
			"presentation commit timestamp is not the persisted fact: payload=%#v stored=%#v err=%v",
			presentationCommit.Payload,
			stored.PresentationDocument,
			err,
		)
	}
}

func stringFieldForTest(values map[string]any, key string) string {
	value, _ := values[key].(string)
	return value
}

func TestDurableWorkerPersistsModelDerivedTaskGraphPatches(t *testing.T) {
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	run, err := workerCommandService(repository).Start(
		context.Background(),
		runruntime.StartCommand{
			UserID:          "user-task-patch",
			SessionID:       "session-task-patch",
			ClientRequestID: "request-task-patch",
			InputText:       "检索并综合证据",
		},
	)
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository,
		queue,
		&taskGraphPatchRunExecutor{},
		"worker-task-patch",
	)
	worked, err := worker.ProcessNext(context.Background())
	if err != nil || !worked {
		t.Fatalf("process run: worked=%t err=%v", worked, err)
	}
	stored, err := repository.Load(context.Background(), run.RunID)
	if err != nil {
		t.Fatalf("load run: %v", err)
	}
	if stored.State != generated.AssistantRunStateCompleted ||
		len(stored.TaskGraph.Tasks) != 3 || !stored.TaskGraph.AllCompleted() {
		t.Fatalf("dynamic task graph did not complete: %#v", stored.TaskGraph)
	}
	planTask := stored.TaskGraph.Tasks[1]
	toolTask := stored.TaskGraph.Tasks[2]
	if len(planTask.Dependencies) != 0 ||
		len(toolTask.Dependencies) != 1 ||
		toolTask.Dependencies[0] != planTask.TaskID {
		t.Fatalf("dynamic dependency frontier=%#v", stored.TaskGraph.Tasks)
	}
	for _, item := range stored.Items {
		if strings.Contains(item.ItemID, ":dynamic:") && item.TaskID == "task_root" {
			t.Fatalf("dynamic process remained attached to task_root: %#v", item)
		}
	}
}

func TestDurableWorkerExecutesCumulativeGoalAfterSteerSafeBoundary(t *testing.T) {
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	commands := workerCommandService(repository)
	run, err := commands.Start(context.Background(), runruntime.StartCommand{
		UserID:          "user-worker",
		SessionID:       "session-worker",
		ClientRequestID: "request-worker-steer-goal",
		InputText:       "规划杭州一日游",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	run, err = commands.Steer(
		context.Background(),
		"user-worker",
		run.RunID,
		"command-worker-steer-goal",
		"只安排步行可达且适合雨天的地点",
	)
	if err != nil {
		t.Fatalf("steer run: %v", err)
	}
	if run.GoalRevision != 2 || len(run.GoalHistory) != 1 {
		t.Fatalf("steer was not applied at accepted safe boundary: %#v", run)
	}

	capturing := &goalCapturingRunExecutor{}
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository,
		queue,
		capturing,
		"worker-steered-goal",
	)
	worked, err := worker.ProcessNext(context.Background())
	if err != nil || !worked {
		t.Fatalf("process steered run: worked=%t err=%v", worked, err)
	}
	if capturing.request.Goal == "规划杭州一日游" ||
		!strings.Contains(capturing.request.Goal, "规划杭州一日游") ||
		!strings.Contains(
			capturing.request.Goal,
			"修订 2：只安排步行可达且适合雨天的地点",
		) {
		t.Fatalf("execution goal ignored applied steer: %q", capturing.request.Goal)
	}
	if len(capturing.request.GoalHistory) != 1 ||
		capturing.request.GoalHistory[0].Instruction !=
			"只安排步行可达且适合雨天的地点" {
		t.Fatalf("execution goal history = %#v", capturing.request.GoalHistory)
	}
}

func TestDurableWorkerReplansAfterSteerAtCompletedItemBoundary(t *testing.T) {
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	commands := workerCommandService(repository)
	run, err := commands.Start(context.Background(), runruntime.StartCommand{
		UserID:          "user-boundary-steer",
		SessionID:       "session-boundary-steer",
		ClientRequestID: "request-boundary-steer",
		InputText:       "规划杭州周末行程",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	executor := &boundarySteeringRunExecutor{commands: commands}
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository,
		queue,
		executor,
		"worker-boundary-steer",
	)
	worked, err := worker.ProcessNext(context.Background())
	if err != nil || !worked {
		t.Fatalf("first process: worked=%t err=%v", worked, err)
	}
	steered, err := repository.Load(context.Background(), run.RunID)
	if err != nil {
		t.Fatalf("load steered run: %v", err)
	}
	if steered.State != generated.AssistantRunStateExecuting ||
		steered.GoalRevision != 2 || len(steered.PendingSteer) != 0 {
		t.Fatalf("steer did not cross durable boundary: %#v", steered)
	}
	planRevisionFound := false
	for _, item := range steered.Items {
		if item.ItemID == "plan:"+run.RunID+":goal:2" &&
			item.Status == generated.AssistantRunItemStatusCompleted {
			planRevisionFound = true
		}
	}
	if !planRevisionFound {
		t.Fatalf("goal revision plan audit item missing: %#v", steered.Items)
	}
	worked, err = worker.ProcessNext(context.Background())
	if err != nil || !worked {
		t.Fatalf("second process: worked=%t err=%v", worked, err)
	}
	if !strings.Contains(executor.lastRequest.Goal, "只保留步行可达地点") ||
		executor.lastRequest.IdempotencyPrefix ==
			"run:"+run.RunID+":goal:1" {
		t.Fatalf("replanned request ignored revised goal: %#v", executor.lastRequest)
	}
	completed, err := repository.Load(context.Background(), run.RunID)
	if err != nil || completed.State != generated.AssistantRunStateCompleted ||
		!completed.TaskGraph.AllCompleted() {
		t.Fatalf("replanned run did not complete: run=%#v err=%v", completed, err)
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
		runruntime.SessionResolverFunc(func(
			context.Context,
			string,
			string,
		) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		time.Now,
		nil,
		runruntime.WithPolicyResolver(testPolicyResolver()),
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
		AnswerText: "可回查答案",
		Processes: []assistantmodel.AssistantRunVisibleProcess{{
			ProcessID:              "process:web:1",
			Scope:                  "tool",
			Stage:                  "searching",
			ActionCode:             "invoke_tool",
			Status:                 "completed",
			Order:                  1,
			Summary:                "公开证据已验证",
			SearchedDocumentCount:  1,
			ProcessedDocumentCount: 1,
			AcceptedDocumentCount:  1,
			AcceptedReferences: []assistantmodel.AssistantRunVisibleReference{{
				SourceID: "source:web:1",
				Title:    "公开证据",
				Destination: assistantmodel.CitationDestination{
					Kind: "public_web_source",
					URL:  "https://example.com/evidence",
				},
				Source:  "example.com",
				Snippet: "公开证据摘要",
			}},
		}},
		ArtifactRefs: []string{
			"artifact:web:1",
			"assistant_run_item:answer:" + request.RunID,
		},
		EvidenceRefs: []string{"source:web:1"},
		VerificationEvidence: []runruntime.VerificationEvidence{{
			Requirement:  "answer_present",
			Passed:       true,
			ArtifactRefs: []string{"assistant_run_item:answer:" + request.RunID},
			Summary:      "durable final answer item is present",
		}},
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
	}, nil
}

type taskGraphPatchRunExecutor struct{}

func (e *taskGraphPatchRunExecutor) Execute(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	planTaskID := request.IdempotencyPrefix + ":task:planning"
	toolTaskID := request.IdempotencyPrefix + ":task:tool"
	updates := []runruntime.ExecutionItemUpdate{
		{
			ItemID:  request.IdempotencyPrefix + ":dynamic:planning",
			Kind:    generated.AssistantRunItemKindTask,
			Status:  generated.AssistantRunItemStatusStarted,
			TaskID:  planTaskID,
			Summary: "形成执行计划",
			Task: &runruntime.ExecutionTaskUpdate{
				Goal:       "形成执行计划",
				OwnerAgent: "manager",
			},
		},
		{
			ItemID:  request.IdempotencyPrefix + ":dynamic:planning",
			Kind:    generated.AssistantRunItemKindTask,
			Status:  generated.AssistantRunItemStatusCompleted,
			TaskID:  planTaskID,
			Summary: "执行计划已形成",
			Task: &runruntime.ExecutionTaskUpdate{
				Goal:       "形成执行计划",
				OwnerAgent: "manager",
			},
		},
		{
			ItemID:  request.IdempotencyPrefix + ":dynamic:tool",
			Kind:    generated.AssistantRunItemKindToolUse,
			Status:  generated.AssistantRunItemStatusStarted,
			TaskID:  toolTaskID,
			Summary: "检索公开证据",
			Task: &runruntime.ExecutionTaskUpdate{
				Goal:         "检索公开证据",
				Dependencies: []string{planTaskID},
				OwnerAgent:   "manager",
			},
		},
		{
			ItemID:       request.IdempotencyPrefix + ":dynamic:tool",
			Kind:         generated.AssistantRunItemKindToolUse,
			Status:       generated.AssistantRunItemStatusCompleted,
			TaskID:       toolTaskID,
			Summary:      "公开证据已验证",
			ArtifactRefs: []string{"artifact:web:dynamic"},
			Task: &runruntime.ExecutionTaskUpdate{
				Goal:         "检索公开证据",
				Dependencies: []string{planTaskID},
				OwnerAgent:   "manager",
			},
		},
	}
	for index, update := range updates {
		if err := emit(update); err != nil {
			return runruntime.ExecutionResult{}, err
		}
		// Worker retry/replay may deliver the same lifecycle edge more than
		// once. The aggregate must treat an identical edge as idempotent.
		if index < 2 {
			if err := emit(update); err != nil {
				return runruntime.ExecutionResult{}, err
			}
		}
	}
	return (&successfulRunExecutor{}).Execute(ctx, request, emit)
}

type boundarySteeringRunExecutor struct {
	commands    *runruntime.CommandService
	calls       int
	lastRequest runruntime.ExecutionRequest
}

func (e *boundarySteeringRunExecutor) Execute(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	e.calls++
	e.lastRequest = request
	if e.calls > 1 {
		return (&successfulRunExecutor{}).Execute(ctx, request, emit)
	}
	taskID := request.IdempotencyPrefix + ":task:planning"
	itemID := request.IdempotencyPrefix + ":dynamic:steer-boundary"
	task := &runruntime.ExecutionTaskUpdate{
		Goal:       "形成初始行程计划",
		OwnerAgent: "manager",
	}
	if err := emit(runruntime.ExecutionItemUpdate{
		ItemID: itemID, Kind: generated.AssistantRunItemKindTask,
		Status: generated.AssistantRunItemStatusStarted,
		TaskID: taskID, Summary: "形成初始行程计划", Task: task,
	}); err != nil {
		return runruntime.ExecutionResult{}, err
	}
	if _, err := e.commands.Steer(
		ctx,
		request.UserID,
		request.RunID,
		"command-boundary-steer",
		"只保留步行可达地点",
	); err != nil {
		return runruntime.ExecutionResult{}, err
	}
	err := emit(runruntime.ExecutionItemUpdate{
		ItemID: itemID, Kind: generated.AssistantRunItemKindTask,
		Status: generated.AssistantRunItemStatusCompleted,
		TaskID: taskID, Summary: "初始计划阶段已完成", Task: task,
	})
	return runruntime.ExecutionResult{}, err
}

type goalCapturingRunExecutor struct {
	request runruntime.ExecutionRequest
}

func (e *goalCapturingRunExecutor) Execute(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	e.request = request
	return (&successfulRunExecutor{}).Execute(ctx, request, emit)
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
