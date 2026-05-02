package reliabletask

import (
	"context"
	"time"
)

type TransactionRunner interface {
	RunInTransaction(ctx context.Context, fn func(context.Context) error) error
}

type OutboxStore interface {
	DeclareTask(ctx context.Context, req DeclareTaskRequest) (TaskOutboxRecord, error)
	DispatchDueTasks(ctx context.Context, now time.Time, limit int) ([]ReliableAsyncTask, error)
	DispatchDueTasksForShard(ctx context.Context, now time.Time, limit int, shardID int) ([]ReliableAsyncTask, error)
}

type ReadyQueue interface {
	ClaimReadyTask(ctx context.Context, taskTypes []string, workerID string, leaseTTL time.Duration, now time.Time) (*ReliableAsyncTask, error)
	ClaimReadyTaskByID(ctx context.Context, taskID string, workerID string, leaseTTL time.Duration, now time.Time) (*ReliableAsyncTask, error)
	CompleteTask(ctx context.Context, taskID string, leaseToken string) error
	FailTask(ctx context.Context, taskID string, leaseToken string, failure RuntimeFailure, policy RetryPolicy, now time.Time) error
}

type ReadyIndex interface {
	Ensure(ctx context.Context) error
	EnqueueReadyOrMerge(ctx context.Context, task ReliableAsyncTask) error
	Claim(ctx context.Context, consumer string, count int64, block time.Duration) ([]ReadyIndexMessage, error)
	Ack(ctx context.Context, message ReadyIndexMessage) error
}

type ReadyIndexMessage struct {
	StreamID string
	TaskID   string
	TaskType string
	Queue    string
	RawID    string
}

type NotificationStore interface {
	CreateNotification(ctx context.Context, record NotificationOutboxRecord) (NotificationOutboxRecord, error)
	ClaimNotification(ctx context.Context, eventTypes []string, workerID string, leaseTTL time.Duration, now time.Time) (*NotificationOutboxRecord, error)
	CompleteNotification(ctx context.Context, notificationID string, leaseToken string) error
	RetryNotification(ctx context.Context, notificationID string, leaseToken string, failure RuntimeFailure, policy RetryPolicy, now time.Time) error
}

type DeliveryLedgerStore interface {
	EnsureRecipientLedgers(ctx context.Context, notificationID string, eventType string, recipientIDs []string) error
	ListPendingRecipients(ctx context.Context, notificationID string) ([]NotificationDeliveryLedgerRecord, error)
	MarkRecipientDelivered(ctx context.Context, notificationID string, recipientID string, syncSeq int64) error
	MarkRecipientFailed(ctx context.Context, notificationID string, recipientID string, failure RuntimeFailure) error
}

type LeaseStore interface {
	ClaimShardLease(ctx context.Context, req ClaimShardLeaseRequest) (*TaskLease, error)
}

type IndexEnsurer interface {
	EnsureIndexes(ctx context.Context) error
}

type Store interface {
	TransactionRunner
	OutboxStore
	ReadyQueue
	NotificationStore
	DeliveryLedgerStore
	LeaseStore
	IndexEnsurer
}

type Dispatcher struct {
	Store    Store
	Ready    ReadyIndex
	Env      string
	Domain   string
	Module   string
	Owner    string
	ShardID  int
	LeaseTTL time.Duration
	Now      func() time.Time
}

func (d Dispatcher) DispatchDue(ctx context.Context, limit int) ([]ReliableAsyncTask, error) {
	if d.Store == nil {
		return nil, ErrStoreRequired
	}
	now := time.Now().UTC()
	if d.Now != nil {
		now = d.Now().UTC()
	}
	var tasks []ReliableAsyncTask
	var err error
	if d.Module == "" {
		tasks, err = d.Store.DispatchDueTasks(ctx, now, limit)
	} else {
		leaseTTL := d.LeaseTTL
		if leaseTTL <= 0 {
			leaseTTL = 30 * time.Second
		}
		lease, err := d.Store.ClaimShardLease(ctx, ClaimShardLeaseRequest{
			Env:      d.Env,
			Domain:   d.Domain,
			Module:   d.Module,
			Owner:    d.Owner,
			ShardID:  d.ShardID,
			LeaseTTL: leaseTTL,
			Now:      now,
		})
		if err != nil {
			return nil, err
		}
		if lease == nil {
			return nil, nil
		}
		tasks, err = d.Store.DispatchDueTasksForShard(ctx, now, limit, d.ShardID)
	}
	if err != nil {
		return nil, err
	}
	if d.Ready != nil {
		for _, task := range tasks {
			if err := d.Ready.EnqueueReadyOrMerge(ctx, task); err != nil {
				return nil, err
			}
		}
	}
	return tasks, nil
}

type TaskHandler func(context.Context, ReliableAsyncTask) error

type Worker struct {
	Store     Store
	Ready     ReadyIndex
	TaskTypes []string
	WorkerID  string
	LeaseTTL  time.Duration
	Retry     RetryPolicy
	Now       func() time.Time
}

func (w Worker) Claim(ctx context.Context) (*ReliableAsyncTask, error) {
	if w.Store == nil {
		return nil, ErrStoreRequired
	}
	now := time.Now().UTC()
	if w.Now != nil {
		now = w.Now().UTC()
	}
	leaseTTL := w.LeaseTTL
	if leaseTTL <= 0 {
		leaseTTL = 30 * time.Second
	}
	if w.Ready == nil {
		return w.Store.ClaimReadyTask(ctx, w.TaskTypes, w.WorkerID, leaseTTL, now)
	}
	messages, err := w.Ready.Claim(ctx, w.WorkerID, 1, 0)
	if err != nil {
		return nil, err
	}
	for _, message := range messages {
		task, err := w.Store.ClaimReadyTaskByID(ctx, message.TaskID, w.WorkerID, leaseTTL, now)
		if err != nil {
			return nil, err
		}
		if task == nil {
			if err := w.Ready.Ack(ctx, message); err != nil {
				return nil, err
			}
			continue
		}
		return task, nil
	}
	return nil, nil
}

func (w Worker) ProcessOne(ctx context.Context, handler TaskHandler) (bool, error) {
	if handler == nil {
		return false, nil
	}
	task, message, err := w.claimWithMessage(ctx)
	if err != nil || task == nil {
		return false, err
	}
	if err := handler(ctx, *task); err != nil {
		policy := w.Retry
		if policy.MaxAttempts <= 0 {
			policy = DefaultRetryPolicy()
		}
		now := time.Now().UTC()
		if w.Now != nil {
			now = w.Now().UTC()
		}
		if failErr := w.Store.FailTask(ctx, task.TaskID, task.LeaseToken, RuntimeFailure{
			Code:    "RELIABLETASK.WORKER.handler_failed",
			Message: err.Error(),
		}, policy, now); failErr != nil {
			return false, failErr
		}
		if w.Ready != nil && message != nil {
			if ackErr := w.Ready.Ack(ctx, *message); ackErr != nil {
				return false, ackErr
			}
		}
		return true, nil
	}
	if err := w.Store.CompleteTask(ctx, task.TaskID, task.LeaseToken); err != nil {
		return false, err
	}
	if w.Ready != nil && message != nil {
		if err := w.Ready.Ack(ctx, *message); err != nil {
			return false, err
		}
	}
	return true, nil
}

func (w Worker) claimWithMessage(ctx context.Context) (*ReliableAsyncTask, *ReadyIndexMessage, error) {
	if w.Store == nil {
		return nil, nil, ErrStoreRequired
	}
	now := time.Now().UTC()
	if w.Now != nil {
		now = w.Now().UTC()
	}
	leaseTTL := w.LeaseTTL
	if leaseTTL <= 0 {
		leaseTTL = 30 * time.Second
	}
	if w.Ready == nil {
		task, err := w.Store.ClaimReadyTask(ctx, w.TaskTypes, w.WorkerID, leaseTTL, now)
		return task, nil, err
	}
	messages, err := w.Ready.Claim(ctx, w.WorkerID, 1, 0)
	if err != nil {
		return nil, nil, err
	}
	for _, message := range messages {
		task, err := w.Store.ClaimReadyTaskByID(ctx, message.TaskID, w.WorkerID, leaseTTL, now)
		if err != nil {
			return nil, nil, err
		}
		if task == nil {
			if err := w.Ready.Ack(ctx, message); err != nil {
				return nil, nil, err
			}
			continue
		}
		return task, &message, nil
	}
	return nil, nil, nil
}
