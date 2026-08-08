// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

var errTransientRunControlRead = errors.New("transient assistant run control read")

func TestDurableWorkerTransientControlReadReschedulesSameRunWithoutTerminalFailure(
	t *testing.T,
) {
	base := newMemoryRunRepository()
	run := startControlObservationRun(t, base, "monitor-transient")
	repository := &singleArmedLoadFailureRepository{
		memoryRunRepository: base,
		failure:             errTransientRunControlRead,
	}
	queue := newMemoryWorkQueue()
	queue.enqueue(run.RunID)
	executor := &blockingRunExecutor{started: make(chan struct{})}
	worker := runruntime.NewDurableWorker(
		repository,
		queue,
		executor,
		"worker-control-observation",
	)
	result := make(chan struct {
		worked bool
		err    error
	}, 1)
	go func() {
		worked, err := worker.ProcessNext(context.Background())
		result <- struct {
			worked bool
			err    error
		}{worked: worked, err: err}
	}()
	select {
	case <-executor.started:
	case <-time.After(3 * time.Second):
		t.Fatal("durable executor did not start")
	}
	repository.armed.Store(true)

	select {
	case outcome := <-result:
		if !outcome.worked || !errors.Is(outcome.err, errTransientRunControlRead) {
			t.Fatalf(
				"control read outcome: worked=%t err=%v",
				outcome.worked,
				outcome.err,
			)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("control read failure did not stop the executor")
	}

	interrupted, err := base.Load(context.Background(), run.RunID)
	if err != nil {
		t.Fatalf("load interrupted run: %v", err)
	}
	if interrupted.State != generated.AssistantRunStateExecuting ||
		interrupted.CompletedAt != nil || interrupted.TerminalSnapshot != nil {
		t.Fatalf("transient control read wrote terminal state: %#v", interrupted)
	}

	recoveryWorker := runruntime.NewDurableWorker(
		repository,
		queue,
		&successfulRunExecutor{},
		"worker-control-recovery",
	)
	if worked, err := recoveryWorker.ProcessNext(context.Background()); err != nil ||
		!worked {
		t.Fatalf("recover same run: worked=%t err=%v", worked, err)
	}
	completed, err := base.Load(context.Background(), run.RunID)
	if err != nil || completed.State != generated.AssistantRunStateCompleted {
		t.Fatalf("same run did not complete after retry: run=%#v err=%v", completed, err)
	}
}

func TestDurableWorkerFinalReadClassifiesTransientAndMissingRun(
	t *testing.T,
) {
	tests := []struct {
		name             string
		failure          error
		expectReschedule bool
	}{
		{
			name:             "transient read preserves runnable claim",
			failure:          errTransientRunControlRead,
			expectReschedule: true,
		},
		{
			name:             "missing aggregate removes orphan claim",
			failure:          runruntime.ErrRunNotFound,
			expectReschedule: false,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			base := newMemoryRunRepository()
			run := startControlObservationRun(t, base, test.name)
			returned := &atomic.Bool{}
			repository := &postExecutionLoadFailureRepository{
				memoryRunRepository: base,
				executorReturned:    returned,
				failure:             test.failure,
			}
			queue := newMemoryWorkQueue()
			queue.enqueue(run.RunID)
			worker := runruntime.NewDurableWorker(
				repository,
				queue,
				&cancelledContextRunExecutor{returned: returned},
				"worker-final-read",
			)
			ctx, cancel := context.WithCancel(context.Background())
			cancel()
			worked, err := worker.ProcessNext(ctx)
			if !worked || !errors.Is(err, context.Canceled) {
				t.Fatalf("interrupted worker: worked=%t err=%v", worked, err)
			}

			if !test.expectReschedule {
				if _, err := queue.ClaimNext(
					context.Background(),
					"orphan-probe",
					time.Second,
				); !errors.Is(err, runruntime.ErrNoWork) {
					t.Fatalf("missing Run retained work claim: %v", err)
				}
				return
			}

			recoveryWorker := runruntime.NewDurableWorker(
				repository,
				queue,
				&successfulRunExecutor{},
				"worker-final-read-recovery",
			)
			if worked, err := recoveryWorker.ProcessNext(context.Background()); err != nil || !worked {
				t.Fatalf("transient final read lost work: worked=%t err=%v", worked, err)
			}
			completed, err := base.Load(context.Background(), run.RunID)
			if err != nil || completed.State != generated.AssistantRunStateCompleted {
				t.Fatalf("rescheduled Run did not complete: run=%#v err=%v", completed, err)
			}
		})
	}
}

func startControlObservationRun(
	t *testing.T,
	repository *memoryRunRepository,
	requestID string,
) runruntime.Run {
	t.Helper()
	run, err := workerCommandService(repository).Start(
		context.Background(),
		runruntime.StartCommand{
			UserID:          "user-control-observation",
			SessionID:       "session-control-observation",
			ClientRequestID: requestID,
			InputText:       "执行可恢复长任务",
		},
	)
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	return run
}

type singleArmedLoadFailureRepository struct {
	*memoryRunRepository
	armed   atomic.Bool
	failed  atomic.Bool
	failure error
}

func (r *singleArmedLoadFailureRepository) Load(
	ctx context.Context,
	runID string,
) (runruntime.Run, error) {
	if r.armed.Load() && r.failed.CompareAndSwap(false, true) {
		return runruntime.Run{}, r.failure
	}
	return r.memoryRunRepository.Load(ctx, runID)
}

type postExecutionLoadFailureRepository struct {
	*memoryRunRepository
	executorReturned *atomic.Bool
	loadsAfterReturn atomic.Int32
	failure          error
}

func (r *postExecutionLoadFailureRepository) Load(
	ctx context.Context,
	runID string,
) (runruntime.Run, error) {
	if r.executorReturned.Load() && r.loadsAfterReturn.Add(1) == 2 {
		return runruntime.Run{}, r.failure
	}
	return r.memoryRunRepository.Load(ctx, runID)
}

type cancelledContextRunExecutor struct {
	returned *atomic.Bool
}

func (e *cancelledContextRunExecutor) Execute(
	ctx context.Context,
	_ runruntime.ExecutionRequest,
	_ func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	e.returned.Store(true)
	return runruntime.ExecutionResult{}, ctx.Err()
}

var _ runruntime.WorkerRepository = (*singleArmedLoadFailureRepository)(nil)
var _ runruntime.WorkerRepository = (*postExecutionLoadFailureRepository)(nil)
