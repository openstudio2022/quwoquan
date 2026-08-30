package importer

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"

	"quwoquan_service/runtime/reliabletask"
)

// RunDataContentWorkers executes one frozen fleet through the same bounded
// scheduler used by the production data-content-worker composition root.
func RunDataContentWorkers(
	ctx context.Context,
	request FleetRequest,
	fleet reliabletask.DataContentFleet,
	executor reliabletask.DataContentExecutor,
) ([]reliabletask.ReliableAsyncTask, error) {
	workers := request.FleetMaxConcurrentWorkers
	if workers < 1 || request.TargetObjectCount < len(request.Jobs) {
		return nil, errors.New("data content fleet concurrency contract is invalid")
	}
	objectTimeout := request.ObjectTimeout()
	if objectTimeout <= 0 {
		return nil, errors.New("data content object timeout must be positive")
	}
	workerCtx, cancel := context.WithCancel(ctx)
	checkpointStore, ok := fleet.Store.(reliabletask.DataContentCheckpointStore)
	if !ok {
		cancel()
		return nil, errors.New("data content fleet requires durable checkpoint store")
	}
	checkpointTracker := reliabletask.NewDataContentCheckpointTracker(time.Now().UTC())
	errorsCh := make(chan error, workers)
	var group sync.WaitGroup
	for index := 0; index < workers; index++ {
		group.Add(1)
		go func(workerIndex int) {
			defer group.Done()
			localFleet := fleet
			localFleet.WorkerID = fmt.Sprintf("%s-%04d", fleet.WorkerID, workerIndex)
			for workerCtx.Err() == nil {
				objectCtx, cancelObject := context.WithTimeout(
					workerCtx,
					objectTimeout,
				)
				processed, err := localFleet.ProcessOneContent(objectCtx, executor)
				cancelObject()
				if err != nil {
					select {
					case errorsCh <- err:
					default:
					}
					return
				}
				if !processed {
					time.Sleep(25 * time.Millisecond)
				}
			}
		}(index)
	}
	stopped := false
	stopWorkers := func() {
		if stopped {
			return
		}
		stopped = true
		cancel()
		group.Wait()
	}
	defer stopWorkers()

	loadSelected := func(loadCtx context.Context) ([]reliabletask.ReliableAsyncTask, error) {
		executionTasks, err := fleet.Store.ListDataContentExecutionTasks(
			loadCtx,
			request.ExecutionID,
		)
		if err != nil {
			return nil, err
		}
		return SelectExecutionTasks(executionTasks, request)
	}
	terminalSnapshot := func(runErr error) ([]reliabletask.ReliableAsyncTask, error) {
		stopWorkers()
		auditCtx := context.WithoutCancel(ctx)
		tasks, err := loadSelected(auditCtx)
		if err != nil {
			return nil, err
		}
		if err := flushDataContentPartitionCheckpoints(
			auditCtx,
			checkpointStore,
			checkpointTracker,
			request,
			tasks,
			time.Now().UTC(),
			false,
		); err != nil {
			return tasks, err
		}
		return tasks, runErr
	}

	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()
	for {
		if err := ctx.Err(); err != nil {
			return terminalSnapshot(err)
		}
		tasks, err := loadSelected(ctx)
		if err != nil {
			return nil, err
		}
		terminal := 0
		for _, task := range tasks {
			if task.Status == reliabletask.TaskStatusSucceeded ||
				task.Status == reliabletask.TaskStatusDead {
				terminal++
			}
		}
		allTerminal := len(tasks) == len(request.Jobs) && terminal == len(tasks)
		if err := flushDataContentPartitionCheckpoints(
			ctx,
			checkpointStore,
			checkpointTracker,
			request,
			tasks,
			time.Now().UTC(),
			allTerminal,
		); err != nil {
			return tasks, err
		}
		if allTerminal {
			return tasks, nil
		}
		select {
		case err := <-errorsCh:
			return terminalSnapshot(fmt.Errorf("data content worker: %w", err))
		case <-ctx.Done():
			return terminalSnapshot(ctx.Err())
		case <-ticker.C:
			if _, err := fleet.Dispatch(ctx, len(request.Jobs)); err != nil {
				return tasks, err
			}
			if _, err := fleet.ReconcileReadyIndex(
				ctx,
				len(request.Jobs),
			); err != nil {
				return tasks, err
			}
		}
	}
}

func flushDataContentPartitionCheckpoints(
	ctx context.Context,
	store reliabletask.DataContentCheckpointStore,
	tracker *reliabletask.DataContentCheckpointTracker,
	request FleetRequest,
	tasks []reliabletask.ReliableAsyncTask,
	now time.Time,
	force bool,
) error {
	stage, err := request.Stage()
	if err != nil {
		return err
	}
	due, err := tracker.Due(
		request.ExecutionID,
		stage,
		request.JobSetDigest,
		tasks,
		request.CheckpointPolicy.EveryFinalizedObjects,
		time.Duration(request.CheckpointPolicy.EverySeconds)*time.Second,
		now,
		force,
	)
	if err != nil {
		return err
	}
	for _, checkpoint := range due {
		if err := store.FlushDataContentPartitionCheckpoint(ctx, checkpoint); err != nil {
			return fmt.Errorf("flush data content partition checkpoint: %w", err)
		}
		tracker.Commit(checkpoint)
	}
	return nil
}
