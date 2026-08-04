// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

func TestWaitingBoundaryPersistsOnlyCurrentRunConfirmedSlots(t *testing.T) {
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	run, err := workerCommandService(repository).Start(
		t.Context(),
		runruntime.StartCommand{
			UserID:          "user-workshop-waiting",
			SessionID:       "session-workshop-waiting",
			ClientRequestID: "request-workshop-waiting",
			InputText:       "议题是依赖反转，继续准备工作坊",
		},
	)
	if err != nil {
		t.Fatalf("start Run: %v", err)
	}
	slots := mustConfirmedSlots(t, map[string]string{
		"workshop_topic": "依赖反转",
	})
	executor := &waitingConfirmedSlotExecutor{slots: slots}
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository,
		queue,
		executor,
		"worker-workshop-waiting",
	)
	if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
		t.Fatalf("process waiting Run: worked=%t err=%v", worked, processErr)
	}

	stored, err := repository.Load(t.Context(), run.RunID)
	if err != nil {
		t.Fatalf("load waiting Run: %v", err)
	}
	if stored.State != generated.AssistantRunStateWaitingUser ||
		stored.Checkpoint == nil ||
		stored.ConfirmedSlots["workshop_topic"] != "依赖反转" {
		t.Fatalf("waiting slot checkpoint=%#v", stored)
	}
	executor.slots["workshop_topic"] = "外部突变"
	if stored.ConfirmedSlots["workshop_topic"] != "依赖反转" {
		t.Fatalf("Run retained executor-owned mutable slots: %#v", stored.ConfirmedSlots)
	}
	if stored.SessionContinuity != nil &&
		len(stored.SessionContinuity.ConfirmedSlots) != 0 {
		t.Fatalf(
			"current Run confirmation leaked into frozen SessionContinuity: %#v",
			stored.SessionContinuity,
		)
	}
}

func TestPausedRunSlotsSurviveRepositoryReloadAndAnotherWorker(t *testing.T) {
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	commands := workerCommandService(repository)
	run, err := commands.Start(t.Context(), runruntime.StartCommand{
		UserID:          "user-workshop-restart",
		SessionID:       "session-workshop-restart",
		ClientRequestID: "request-workshop-restart",
		InputText:       "继续工作坊",
	})
	if err != nil {
		t.Fatalf("start Run: %v", err)
	}
	blocking := &pausingConfirmedSlotExecutor{
		started: make(chan struct{}),
		slots: mustConfirmedSlots(t, map[string]string{
			"workshop_topic": "上下文治理",
		}),
	}
	queue.enqueue(run.RunID)
	firstWorker := runruntime.NewDurableWorker(
		repository,
		queue,
		blocking,
		"worker-workshop-before-restart",
	)
	firstDone := make(chan error, 1)
	go func() {
		_, processErr := firstWorker.ProcessNext(context.Background())
		firstDone <- processErr
	}()
	select {
	case <-blocking.started:
	case <-time.After(3 * time.Second):
		t.Fatal("first worker did not reach prepared execution")
	}
	if _, err := commands.Pause(
		t.Context(),
		run.UserID,
		run.RunID,
		"pause-workshop-restart",
		"user_requested",
	); err != nil {
		t.Fatalf("pause Run: %v", err)
	}
	select {
	case processErr := <-firstDone:
		if processErr != nil {
			t.Fatalf("checkpoint prepared slots: %v", processErr)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("first worker did not converge to paused")
	}
	paused, err := repository.Load(t.Context(), run.RunID)
	if err != nil || paused.State != generated.AssistantRunStatePaused ||
		paused.Checkpoint == nil ||
		paused.ConfirmedSlots["workshop_topic"] != "上下文治理" {
		t.Fatalf("paused Run lost prepared slots: run=%#v err=%v", paused, err)
	}
	resumed, err := commands.Resume(
		t.Context(),
		run.UserID,
		run.RunID,
		"resume-workshop-restart",
	)
	if err != nil {
		t.Fatalf("resume Run: %v", err)
	}
	queue.enqueue(resumed.RunID)
	capturing := &confirmedSlotCapturingExecutor{}
	restartedWorker := runruntime.NewDurableWorker(
		repository,
		queue,
		capturing,
		"worker-workshop-restarted",
	)
	if worked, processErr := restartedWorker.ProcessNext(t.Context()); processErr != nil || !worked {
		t.Fatalf("process reloaded Run: worked=%t err=%v", worked, processErr)
	}
	if capturing.request.ConfirmedSlots["workshop_topic"] != "上下文治理" {
		t.Fatalf("restarted worker request=%#v", capturing.request.ConfirmedSlots)
	}
}

func TestConfirmedSlotSetRejectsUnboundedOrNonCanonicalValues(t *testing.T) {
	tooMany := make(map[string]string, 17)
	for index := 0; index < 17; index++ {
		tooMany["slot_"+string(rune('a'+index))] = "value"
	}
	if _, err := assistantmodel.NewAssistantRunConfirmedSlots(tooMany); err == nil {
		t.Fatal("17 confirmed slots were accepted")
	}
	if _, err := assistantmodel.NewAssistantRunConfirmedSlots(map[string]string{
		"workshop_topic": "unsafe\nsummary",
	}); err == nil {
		t.Fatal("control-bearing confirmed slot was accepted")
	}
	if _, err := assistantmodel.NewAssistantRunConfirmedSlots(map[string]string{
		"WorkshopTopic": "value",
	}); err == nil {
		t.Fatal("non-canonical slot id was accepted")
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/long-term-memory-compaction/spec.md#gwt-002
func TestTerminalSlotSourceExcludesFrozenSessionContinuity(t *testing.T) {
	run := runruntime.Run{
		SessionContinuity: &runruntime.SessionContinuity{
			ConfirmedSlots: map[string]string{
				"workshop_topic": "旧议题",
				"meeting_place":  "杭州",
			},
		},
		ConfirmedSlots: mustConfirmedSlots(t, map[string]string{
			"workshop_topic": "依赖反转",
		}),
	}
	source := run.ConfirmedSlotSnapshot()
	if len(source) != 1 || source["workshop_topic"] != "依赖反转" ||
		source["meeting_place"] != "" {
		t.Fatalf("terminal current-Run slot source=%#v", source)
	}
	source["workshop_topic"] = "外部突变"
	if run.ConfirmedSlots["workshop_topic"] != "依赖反转" {
		t.Fatalf("terminal source shared aggregate map: %#v", run.ConfirmedSlots)
	}
}

func mustConfirmedSlots(
	t *testing.T,
	values map[string]string,
) assistantmodel.AssistantRunConfirmedSlots {
	t.Helper()
	slots, err := assistantmodel.NewAssistantRunConfirmedSlots(values)
	if err != nil {
		t.Fatalf("new confirmed slots: %v", err)
	}
	return slots
}

type waitingConfirmedSlotExecutor struct {
	slots assistantmodel.AssistantRunConfirmedSlots
}

func (executor *waitingConfirmedSlotExecutor) Execute(
	context.Context,
	runruntime.ExecutionRequest,
	func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	return runruntime.ExecutionResult{
		WaitingState:   generated.AssistantRunStateWaitingUser,
		WaitReason:     "workshop_detail_required",
		ConfirmedSlots: executor.slots,
	}, nil
}

type confirmedSlotCapturingExecutor struct {
	request runruntime.ExecutionRequest
}

type pausingConfirmedSlotExecutor struct {
	started chan struct{}
	slots   assistantmodel.AssistantRunConfirmedSlots
}

func (executor *pausingConfirmedSlotExecutor) Execute(
	ctx context.Context,
	_ runruntime.ExecutionRequest,
	_ func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	close(executor.started)
	<-ctx.Done()
	return runruntime.ExecutionResult{
		ConfirmedSlots: executor.slots,
	}, ctx.Err()
}

func (executor *confirmedSlotCapturingExecutor) Execute(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	executor.request = request
	return (&successfulRunExecutor{}).Execute(ctx, request, emit)
}
