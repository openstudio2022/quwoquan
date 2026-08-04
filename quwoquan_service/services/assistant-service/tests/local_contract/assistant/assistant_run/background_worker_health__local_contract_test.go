// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

type terminalLearningHealthStore struct {
	mu       sync.Mutex
	claimErr error
}

func (store *terminalLearningHealthStore) setClaimError(err error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.claimErr = err
}

func (store *terminalLearningHealthStore) ClaimPendingTerminalEvents(
	context.Context,
	string,
	time.Duration,
	int,
) ([]runruntime.TerminalEvent, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	return nil, store.claimErr
}

func (*terminalLearningHealthStore) MarkTerminalEventProcessed(
	context.Context,
	string,
	string,
	time.Time,
) error {
	return nil
}

func (*terminalLearningHealthStore) ReleaseTerminalEventClaim(
	context.Context,
	string,
	string,
) error {
	return nil
}

type durableWorkerHealthQueue struct {
	mu       sync.Mutex
	claimErr error
}

func (queue *durableWorkerHealthQueue) setClaimError(err error) {
	queue.mu.Lock()
	defer queue.mu.Unlock()
	queue.claimErr = err
}

func (queue *durableWorkerHealthQueue) ClaimNext(
	context.Context,
	string,
	time.Duration,
) (runruntime.WorkClaim, error) {
	queue.mu.Lock()
	defer queue.mu.Unlock()
	if queue.claimErr != nil {
		return runruntime.WorkClaim{}, queue.claimErr
	}
	return runruntime.WorkClaim{}, runruntime.ErrNoWork
}

func (*durableWorkerHealthQueue) HeartbeatClaim(
	_ context.Context,
	runtimeClaim runruntime.WorkClaim,
	_ time.Duration,
) (runruntime.WorkClaim, error) {
	return runtimeClaim, nil
}

func (*durableWorkerHealthQueue) CompleteClaim(
	_ context.Context,
	_ runruntime.WorkClaim,
	_ bool,
	_ time.Time,
) error {
	return nil
}

func TestTerminalRunRelayHealthTracksCompletedBusinessScans(t *testing.T) {
	store := &terminalLearningHealthStore{}
	relay := runruntime.NewTerminalRunRelay(
		store,
		[]runruntime.TerminalEventHandler{runruntime.TerminalEventHandlerFunc(func(
			context.Context,
			runruntime.TerminalEvent,
		) error {
			return nil
		})},
		"terminal-health-worker",
		time.Hour,
		8,
	)
	if err := relay.Healthy(t.Context(), time.Second); err == nil {
		t.Fatal("relay must be unhealthy before its first canonical outbox scan")
	}
	runCancelledRelayTick(t, relay)
	if err := relay.Healthy(t.Context(), time.Second); err != nil {
		t.Fatalf("empty successful scan must establish liveness: %v", err)
	}

	scanErr := errors.New("terminal outbox unavailable")
	store.setClaimError(scanErr)
	runCancelledRelayTick(t, relay)
	if err := relay.Healthy(t.Context(), time.Second); !errors.Is(err, scanErr) {
		t.Fatalf("failed scan must fail health, got %v", err)
	}

	store.setClaimError(nil)
	runCancelledRelayTick(t, relay)
	if err := relay.Healthy(t.Context(), time.Second); err != nil {
		t.Fatalf("later successful scan must recover health: %v", err)
	}
}

func TestDurableWorkerHealthTracksQueuePollOutcome(t *testing.T) {
	queue := &durableWorkerHealthQueue{}
	worker := runruntime.NewDurableWorker(
		newMemoryRunRepository(),
		queue,
		&successfulRunExecutor{},
		"durable-health-worker",
	)
	if err := worker.Healthy(t.Context(), time.Second); err == nil {
		t.Fatal("worker must be unhealthy before its first durable queue poll")
	}
	if worked, err := worker.ProcessNext(t.Context()); err != nil || worked {
		t.Fatalf("empty queue poll worked=%t error=%v", worked, err)
	}
	if err := worker.Healthy(t.Context(), time.Second); err != nil {
		t.Fatalf("empty successful queue poll must establish liveness: %v", err)
	}

	pollErr := errors.New("durable queue unavailable")
	queue.setClaimError(pollErr)
	if _, err := worker.ProcessNext(t.Context()); !errors.Is(err, pollErr) {
		t.Fatalf("queue error=%v want %v", err, pollErr)
	}
	if err := worker.Healthy(t.Context(), time.Second); !errors.Is(err, pollErr) {
		t.Fatalf("failed queue poll must fail health, got %v", err)
	}

	queue.setClaimError(nil)
	if _, err := worker.ProcessNext(t.Context()); err != nil {
		t.Fatalf("recovery queue poll: %v", err)
	}
	if err := worker.Healthy(t.Context(), time.Second); err != nil {
		t.Fatalf("later successful queue poll must recover health: %v", err)
	}
}

func TestDurableWorkerHealthRemainsLiveWhileClaimIsExecuting(t *testing.T) {
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	run, err := workerCommandService(repository).Start(
		t.Context(),
		runruntime.StartCommand{
			UserID:          "user-active-worker-health",
			SessionID:       "session-active-worker-health",
			ClientRequestID: "request-active-worker-health",
			InputText:       "执行长任务并保持租约",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	queue.enqueue(run.RunID)
	executor := &blockingRunExecutor{started: make(chan struct{})}
	worker := runruntime.NewDurableWorker(
		repository,
		queue,
		executor,
		"durable-active-health-worker",
	)
	ctx, cancel := context.WithCancel(t.Context())
	done := make(chan error, 1)
	go func() {
		_, processErr := worker.ProcessNext(ctx)
		done <- processErr
	}()
	select {
	case <-executor.started:
	case <-time.After(3 * time.Second):
		cancel()
		t.Fatal("durable worker did not enter active execution")
	}
	if err := worker.Healthy(t.Context(), time.Second); err != nil {
		cancel()
		t.Fatalf("successful durable claim must establish active liveness: %v", err)
	}
	cancel()
	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatal("durable worker did not stop after cancellation")
	}
}

func runCancelledRelayTick(
	t *testing.T,
	relay *runruntime.TerminalRunRelay,
) {
	t.Helper()
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	relay.Run(ctx)
}

var _ runruntime.TerminalEventStore = (*terminalLearningHealthStore)(nil)
var _ runruntime.WorkQueue = (*durableWorkerHealthQueue)(nil)
