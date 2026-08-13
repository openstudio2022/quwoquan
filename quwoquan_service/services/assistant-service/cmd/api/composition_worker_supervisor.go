package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

type assistantBackgroundWorkerSpec struct {
	name   string
	run    func(context.Context)
	health func(context.Context) error
}

type supervisedAssistantWorker struct {
	spec assistantBackgroundWorkerSpec

	stateMu sync.RWMutex
	exited  bool
	failure error
}

type assistantBackgroundWorkers struct {
	ctx             context.Context
	cancel          context.CancelFunc
	logger          *slog.Logger
	shutdownTimeout time.Duration
	workers         []*supervisedAssistantWorker
	waitGroup       sync.WaitGroup
	done            chan struct{}
	started         atomic.Bool
	startOnce       sync.Once
	closeOnce       sync.Once
	closeErr        error
}

func newAssistantBackgroundWorkers(
	specs []assistantBackgroundWorkerSpec,
	shutdownTimeout time.Duration,
	logger *slog.Logger,
) (*assistantBackgroundWorkers, error) {
	if len(specs) == 0 {
		return nil, errors.New("assistant background worker specs are required")
	}
	if shutdownTimeout <= 0 {
		return nil, errors.New("assistant background worker shutdown timeout must be positive")
	}
	if logger == nil {
		logger = slog.Default()
	}
	workerContext, cancel := context.WithCancel(context.Background())
	supervisor := &assistantBackgroundWorkers{
		ctx:             workerContext,
		cancel:          cancel,
		logger:          logger,
		shutdownTimeout: shutdownTimeout,
		workers:         make([]*supervisedAssistantWorker, 0, len(specs)),
		done:            make(chan struct{}),
	}
	names := make(map[string]struct{}, len(specs))
	for _, spec := range specs {
		spec.name = strings.TrimSpace(spec.name)
		if spec.name == "" || spec.run == nil || spec.health == nil {
			cancel()
			return nil, errors.New(
				"assistant background worker name, run, and health are required",
			)
		}
		if _, exists := names[spec.name]; exists {
			cancel()
			return nil, fmt.Errorf(
				"assistant background worker %q is registered more than once",
				spec.name,
			)
		}
		names[spec.name] = struct{}{}
		supervisor.workers = append(
			supervisor.workers,
			&supervisedAssistantWorker{spec: spec},
		)
	}
	return supervisor, nil
}

func (workers *assistantBackgroundWorkers) Start() {
	if workers == nil {
		return
	}
	workers.startOnce.Do(func() {
		workers.started.Store(true)
		workers.waitGroup.Add(len(workers.workers))
		for _, worker := range workers.workers {
			worker := worker
			go workers.run(worker)
		}
		go func() {
			workers.waitGroup.Wait()
			close(workers.done)
		}()
	})
}

func (workers *assistantBackgroundWorkers) run(
	worker *supervisedAssistantWorker,
) {
	defer workers.waitGroup.Done()
	defer func() {
		worker.stateMu.Lock()
		worker.exited = true
		worker.stateMu.Unlock()
		if recovered := recover(); recovered != nil {
			err := fmt.Errorf("worker panicked: %v", recovered)
			worker.recordFailure(err)
			workers.logger.Error(
				"assistant background worker panicked",
				slog.String("worker", worker.spec.name),
				slog.String("error", err.Error()),
			)
			workers.cancel()
			return
		}
		if workers.ctx.Err() == nil {
			err := errors.New("worker exited before supervisor cancellation")
			worker.recordFailure(err)
			workers.logger.Error(
				"assistant background worker exited unexpectedly",
				slog.String("worker", worker.spec.name),
			)
			workers.cancel()
		}
	}()
	worker.spec.run(workers.ctx)
}

func (worker *supervisedAssistantWorker) Healthy(ctx context.Context) error {
	if worker == nil {
		return errors.New("assistant background worker is not configured")
	}
	worker.stateMu.RLock()
	exited := worker.exited
	failure := worker.failure
	worker.stateMu.RUnlock()
	if failure != nil {
		return fmt.Errorf("%s: %w", worker.spec.name, failure)
	}
	if exited {
		return fmt.Errorf("%s: worker is not running", worker.spec.name)
	}
	if err := worker.spec.health(ctx); err != nil {
		return fmt.Errorf("%s: %w", worker.spec.name, err)
	}
	return nil
}

func (worker *supervisedAssistantWorker) recordFailure(err error) {
	worker.stateMu.Lock()
	defer worker.stateMu.Unlock()
	worker.failure = errors.Join(worker.failure, err)
}

func (workers *assistantBackgroundWorkers) Close() error {
	if workers == nil {
		return nil
	}
	workers.closeOnce.Do(func() {
		workers.cancel()
		if !workers.started.Load() {
			close(workers.done)
			return
		}
		timer := time.NewTimer(workers.shutdownTimeout)
		defer timer.Stop()
		select {
		case <-workers.done:
			return
		case <-timer.C:
			workers.closeErr = fmt.Errorf(
				"assistant background workers exceeded shutdown timeout %s",
				workers.shutdownTimeout,
			)
			workers.logger.Error(
				"assistant background worker shutdown timed out; waiting before dependency close",
				slog.String("timeout", workers.shutdownTimeout.String()),
			)
		}
		// Dependency stores must remain open until every worker has observed
		// cancellation and returned. A timeout is reported after the join rather
		// than trading a bounded wait for a use-after-close race.
		<-workers.done
	})
	return workers.closeErr
}
