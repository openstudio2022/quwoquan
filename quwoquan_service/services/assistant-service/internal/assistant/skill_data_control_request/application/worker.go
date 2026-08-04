package application

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/ports"
)

const defaultWorkerBatchSize = 64

type ActionExecutor interface {
	ExecuteSkillDataControlAction(context.Context, model.Request, string) error
}

// Worker is the only execution owner for confirmed SkillDataControlRequest
// aggregates. Every semantic action is fenced by a persisted lease while the
// owner command itself uses requestId+action as its stable idempotency key.
type Worker struct {
	store        ports.Store
	executor     ActionExecutor
	workerID     string
	pollInterval time.Duration
	leaseTTL     time.Duration
	now          func() time.Time

	healthMu           sync.RWMutex
	lastSuccessfulScan time.Time
	lastFailure        error
}

func NewWorker(
	store ports.Store,
	executor ActionExecutor,
	workerID string,
	pollInterval time.Duration,
	leaseTTL time.Duration,
	now func() time.Time,
) (*Worker, error) {
	workerID = strings.TrimSpace(workerID)
	if store == nil || executor == nil || workerID == "" ||
		pollInterval <= 0 || leaseTTL <= pollInterval {
		return nil, model.ErrInvalidArgument
	}
	if now == nil {
		now = time.Now
	}
	return &Worker{
		store:        store,
		executor:     executor,
		workerID:     workerID,
		pollInterval: pollInterval,
		leaseTTL:     leaseTTL,
		now:          now,
	}, nil
}

func (worker *Worker) Run(ctx context.Context) {
	worker.scanAndObserve(ctx)
	ticker := time.NewTicker(worker.pollInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			worker.scanAndObserve(ctx)
		}
	}
}

// RunOnce atomically claims and advances at most one durable request.
func (worker *Worker) RunOnce(ctx context.Context) (bool, error) {
	if worker == nil || worker.store == nil || worker.executor == nil {
		return false, model.ErrStorageUnavailable
	}
	claim, found, err := worker.store.ClaimNextExecution(
		ctx,
		worker.workerID,
		worker.now().UTC(),
		worker.leaseTTL,
	)
	if err != nil || !found {
		return found, err
	}
	current := claim.Request
	fence := claim.Fence
	for _, action := range current.RequestedActions {
		if current.HasCompleted(action) {
			continue
		}
		var executeErr error
		fence, executeErr = worker.executeWithHeartbeat(ctx, fence, current, action)
		if executeErr != nil {
			if ctx.Err() != nil {
				return true, ctx.Err()
			}
			failed, markErr := worker.store.MarkFailed(
				ctx,
				fence,
				action,
				"owner_action_failed",
				current.Revision,
				worker.now().UTC(),
			)
			if markErr != nil {
				return true, errors.Join(executeErr, markErr)
			}
			return true, errors.Join(
				model.ErrActionFailed,
				fmt.Errorf("%s at revision %d: %w", action, failed.Revision, executeErr),
			)
		}
		current, err = worker.store.MarkActionCompleted(
			ctx,
			fence,
			action,
			current.Revision,
			worker.now().UTC(),
		)
		if err != nil {
			return true, err
		}
	}
	_, err = worker.store.MarkCompleted(
		ctx,
		fence,
		current.Revision,
		worker.now().UTC(),
	)
	return true, err
}

func (worker *Worker) executeWithHeartbeat(
	ctx context.Context,
	fence model.ExecutionFence,
	request model.Request,
	action string,
) (model.ExecutionFence, error) {
	executionCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	result := make(chan error, 1)
	go func() {
		result <- worker.executor.ExecuteSkillDataControlAction(
			executionCtx,
			request,
			action,
		)
	}()

	heartbeatInterval := worker.leaseTTL / 3
	if heartbeatInterval <= 0 {
		heartbeatInterval = worker.pollInterval
	}
	ticker := time.NewTicker(heartbeatInterval)
	defer ticker.Stop()
	currentFence := fence
	for {
		select {
		case err := <-result:
			return currentFence, err
		case <-ctx.Done():
			return currentFence, ctx.Err()
		case <-ticker.C:
			nextFence, err := worker.store.HeartbeatExecution(
				ctx,
				currentFence,
				worker.now().UTC(),
				worker.leaseTTL,
			)
			if err != nil {
				cancel()
				return currentFence, err
			}
			currentFence = nextFence
		}
	}
}

func (worker *Worker) scanAndObserve(ctx context.Context) {
	for processed := 0; processed < defaultWorkerBatchSize; processed++ {
		found, err := worker.RunOnce(ctx)
		if err != nil {
			worker.recordFailure(err)
			return
		}
		if !found {
			worker.recordSuccessfulScan()
			return
		}
	}
	worker.recordSuccessfulScan()
}

func (worker *Worker) Healthy(_ context.Context, maxStaleness time.Duration) error {
	if worker == nil {
		return errors.New("skill data control worker is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	worker.healthMu.RLock()
	lastSuccessfulScan := worker.lastSuccessfulScan
	lastFailure := worker.lastFailure
	worker.healthMu.RUnlock()
	if lastFailure != nil {
		return lastFailure
	}
	if lastSuccessfulScan.IsZero() {
		return errors.New("skill data control worker has not completed a scan")
	}
	if worker.now().UTC().Sub(lastSuccessfulScan) > maxStaleness {
		return errors.New("skill data control worker heartbeat is stale")
	}
	return nil
}

func (worker *Worker) recordSuccessfulScan() {
	worker.healthMu.Lock()
	defer worker.healthMu.Unlock()
	worker.lastSuccessfulScan = worker.now().UTC()
	worker.lastFailure = nil
}

func (worker *Worker) recordFailure(err error) {
	worker.healthMu.Lock()
	defer worker.healthMu.Unlock()
	worker.lastFailure = err
}
