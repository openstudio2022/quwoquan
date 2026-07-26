package reliabletask

import (
	"context"
	"errors"
	"sort"
	"strings"
	"sync"
	"time"
)

type MemoryStore struct {
	mu                  sync.Mutex
	outboxes            map[string]TaskOutboxRecord
	outboxByDedupe      map[string]string
	outboxByIdempotency map[string]string
	tasks               map[string]ReliableAsyncTask
	taskByDedupe        map[string]string
	notifications       map[string]NotificationOutboxRecord
	ledgers             map[string]NotificationDeliveryLedgerRecord
	attempts            map[string]ProviderAttemptRecord
	leases              map[string]TaskLease
}

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{
		outboxes:            map[string]TaskOutboxRecord{},
		outboxByDedupe:      map[string]string{},
		outboxByIdempotency: map[string]string{},
		tasks:               map[string]ReliableAsyncTask{},
		taskByDedupe:        map[string]string{},
		notifications:       map[string]NotificationOutboxRecord{},
		ledgers:             map[string]NotificationDeliveryLedgerRecord{},
		attempts:            map[string]ProviderAttemptRecord{},
		leases:              map[string]TaskLease{},
	}
}

func (s *MemoryStore) RunInTransaction(ctx context.Context, fn func(context.Context) error) error {
	return fn(ctx)
}

func (s *MemoryStore) EnsureIndexes(ctx context.Context) error {
	_ = ctx
	return nil
}

func (s *MemoryStore) DeclareTask(ctx context.Context, req DeclareTaskRequest) (TaskOutboxRecord, error) {
	_ = ctx
	if err := ValidatePayloadAllowlist(req.Payload, req.PayloadAllow); err != nil {
		return TaskOutboxRecord{}, err
	}
	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now().UTC()
	startAt, maxDelayUntil := ResolveTaskSchedule(req, now)
	idempotencyKey := strings.TrimSpace(req.IdempotencyKey)
	if idempotencyKey != "" {
		if existingID := s.outboxByIdempotency[idempotencyKey]; existingID != "" {
			return s.outboxes[existingID], nil
		}
	}
	dedupeKey := strings.TrimSpace(req.DedupeKey)
	if dedupeKey == "" {
		dedupeKey = strings.TrimSpace(req.TaskType) + ":" + strings.TrimSpace(req.AggregateID)
	}
	if existingID := s.outboxByDedupe[dedupeKey]; existingID != "" {
		existing := s.outboxes[existingID]
		if existing.Status == TaskOutboxStatusPending {
			existing.Payload = MergeTaskPayload(existing.Payload, req.Payload)
			existing.Trigger = MergeCSVValues(existing.Trigger, req.Trigger)
			existing.StartAt = ExtendTaskStartAt(existing, req, now)
			if existing.MaxDelayUntil.IsZero() && !maxDelayUntil.IsZero() {
				existing.MaxDelayUntil = maxDelayUntil
			}
			existing.UpdatedAt = now
			s.outboxes[existingID] = existing
			return existing, nil
		}
	}

	record := TaskOutboxRecord{
		OutboxID:        NewRecordID("outbox"),
		TaskType:        strings.TrimSpace(req.TaskType),
		OwnerDomain:     strings.TrimSpace(req.OwnerDomain),
		AggregateType:   strings.TrimSpace(req.AggregateType),
		AggregateID:     strings.TrimSpace(req.AggregateID),
		DedupeKey:       dedupeKey,
		IdempotencyKey:  strings.TrimSpace(req.IdempotencyKey),
		PartitionKey:    strings.TrimSpace(req.PartitionKey),
		ShardID:         ResolveTaskShardID(req),
		Payload:         CloneStringMap(req.Payload),
		Trigger:         strings.TrimSpace(req.Trigger),
		Status:          TaskOutboxStatusPending,
		StartAt:         startAt,
		MaxDelayUntil:   maxDelayUntil,
		CreatedByModule: strings.TrimSpace(req.CreatedByModule),
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	s.outboxes[record.OutboxID] = record
	s.outboxByDedupe[record.DedupeKey] = record.OutboxID
	if record.IdempotencyKey != "" {
		s.outboxByIdempotency[record.IdempotencyKey] = record.OutboxID
	}
	return record, nil
}

func (s *MemoryStore) DispatchDueTasks(ctx context.Context, now time.Time, limit int) ([]ReliableAsyncTask, error) {
	return s.DispatchDueTasksForShard(ctx, now, limit, -1)
}

func (s *MemoryStore) DispatchDueTasksForShard(ctx context.Context, now time.Time, limit int, shardID int) ([]ReliableAsyncTask, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.dispatchDueTasksLocked(now, limit, func(record TaskOutboxRecord) bool {
		return shardID < 0 || record.ShardID == shardID
	})
}

// DispatchDataContentExecution mirrors the production Mongo execution scope.
func (s *MemoryStore) DispatchDataContentExecution(
	ctx context.Context,
	executionID string,
	now time.Time,
	limit int,
) ([]ReliableAsyncTask, error) {
	_ = ctx
	executionID = strings.TrimSpace(executionID)
	if executionID == "" {
		return nil, errors.New("data content executionId is required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.dispatchDueTasksLocked(now, limit, func(record TaskOutboxRecord) bool {
		return record.TaskType == DataContentTaskType &&
			record.Payload["executionId"] == executionID
	})
}

func (s *MemoryStore) dispatchDueTasksLocked(
	now time.Time,
	limit int,
	include func(TaskOutboxRecord) bool,
) ([]ReliableAsyncTask, error) {
	if limit <= 0 {
		limit = 100
	}
	outboxes := make([]TaskOutboxRecord, 0, len(s.outboxes))
	for _, record := range s.outboxes {
		if !include(record) {
			continue
		}
		if (record.Status == TaskOutboxStatusPending || record.Status == TaskOutboxStatusFailed) && !record.StartAt.After(now) {
			outboxes = append(outboxes, record)
		}
	}
	sort.Slice(outboxes, func(i, j int) bool {
		return outboxes[i].StartAt.Before(outboxes[j].StartAt)
	})
	if len(outboxes) > limit {
		outboxes = outboxes[:limit]
	}
	tasks := make([]ReliableAsyncTask, 0, len(outboxes))
	for _, outbox := range outboxes {
		taskID := s.taskByDedupe[outbox.DedupeKey]
		var task ReliableAsyncTask
		if taskID != "" {
			task = s.tasks[taskID]
			if task.Status == TaskStatusSucceeded || task.Status == TaskStatusDead {
				taskID = ""
			}
		}
		if taskID == "" {
			task = ReliableAsyncTask{
				TaskID:         NewRecordID("task"),
				OutboxID:       outbox.OutboxID,
				TaskType:       outbox.TaskType,
				OwnerDomain:    outbox.OwnerDomain,
				AggregateType:  outbox.AggregateType,
				AggregateID:    outbox.AggregateID,
				DedupeKey:      outbox.DedupeKey,
				IdempotencyKey: outbox.IdempotencyKey,
				PartitionKey:   outbox.PartitionKey,
				ShardID:        outbox.ShardID,
				Payload:        CloneStringMap(outbox.Payload),
				Status:         TaskStatusReady,
				NextAttemptAt:  now.UTC(),
				CreatedAt:      now.UTC(),
				UpdatedAt:      now.UTC(),
			}
			s.taskByDedupe[task.DedupeKey] = task.TaskID
		} else {
			task.Payload = MergeTaskPayload(task.Payload, outbox.Payload)
			if task.Status == TaskStatusRetryWait && !task.NextAttemptAt.After(now) {
				task.Status = TaskStatusReady
			}
			task.UpdatedAt = now.UTC()
		}
		s.tasks[task.TaskID] = task
		outbox.Status = TaskOutboxStatusDispatched
		outbox.DispatchAttempts++
		outbox.UpdatedAt = now.UTC()
		s.outboxes[outbox.OutboxID] = outbox
		tasks = append(tasks, task)
	}
	return tasks, nil
}

func (s *MemoryStore) ClaimReadyTask(ctx context.Context, taskTypes []string, workerID string, leaseTTL time.Duration, now time.Time) (*ReliableAsyncTask, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	ids := make([]string, 0, len(s.tasks))
	for id := range s.tasks {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		task := s.tasks[id]
		if !contains(task.TaskType, taskTypes) {
			continue
		}
		leaseExpired := !task.LeaseUntil.IsZero() && !task.LeaseUntil.After(now)
		if (task.Status == TaskStatusReady || task.Status == TaskStatusRetryWait || (task.Status == TaskStatusProcessing && leaseExpired)) && !task.NextAttemptAt.After(now) {
			task.Status = TaskStatusProcessing
			task.LeaseOwner = strings.TrimSpace(workerID)
			task.LeaseToken = NewRecordID("lease")
			task.LeaseUntil = now.Add(leaseTTL).UTC()
			task.UpdatedAt = now.UTC()
			s.tasks[id] = task
			return &task, nil
		}
	}
	return nil, nil
}

func (s *MemoryStore) ClaimReadyTaskByID(ctx context.Context, taskID string, workerID string, leaseTTL time.Duration, now time.Time) (*ReliableAsyncTask, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	task, ok := s.tasks[strings.TrimSpace(taskID)]
	if !ok {
		return nil, nil
	}
	leaseExpired := !task.LeaseUntil.IsZero() && !task.LeaseUntil.After(now)
	if !(task.Status == TaskStatusReady || task.Status == TaskStatusRetryWait || (task.Status == TaskStatusProcessing && leaseExpired)) || task.NextAttemptAt.After(now) {
		return nil, nil
	}
	task.Status = TaskStatusProcessing
	task.LeaseOwner = strings.TrimSpace(workerID)
	task.LeaseToken = NewRecordID("lease")
	task.LeaseUntil = now.Add(leaseTTL).UTC()
	task.UpdatedAt = now.UTC()
	s.tasks[task.TaskID] = task
	return &task, nil
}

func (s *MemoryStore) ListReadyTasks(
	ctx context.Context,
	taskTypes []string,
	limit int,
	now time.Time,
) ([]ReliableAsyncTask, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.listReadyTasksLocked(taskTypes, limit, now, func(ReliableAsyncTask) bool { return true }), nil
}

// ListReadyDataContentExecution mirrors the production Mongo execution scope.
func (s *MemoryStore) ListReadyDataContentExecution(
	ctx context.Context,
	executionID string,
	limit int,
	now time.Time,
) ([]ReliableAsyncTask, error) {
	_ = ctx
	executionID = strings.TrimSpace(executionID)
	if executionID == "" {
		return nil, errors.New("data content executionId is required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.listReadyTasksLocked(
		[]string{DataContentTaskType},
		limit,
		now,
		func(task ReliableAsyncTask) bool {
			return task.Payload["executionId"] == executionID
		},
	), nil
}

// PurgeDataContentExecution mirrors the production exact execution cleanup.
func (s *MemoryStore) PurgeDataContentExecution(
	ctx context.Context,
	executionID string,
) (DataContentExecutionPurgeResult, error) {
	_ = ctx
	executionID = strings.TrimSpace(executionID)
	if executionID == "" {
		return DataContentExecutionPurgeResult{}, errors.New("data content executionId is required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	result := DataContentExecutionPurgeResult{}
	for taskID, task := range s.tasks {
		if task.TaskType != DataContentTaskType || task.Payload["executionId"] != executionID {
			continue
		}
		delete(s.tasks, taskID)
		delete(s.taskByDedupe, task.DedupeKey)
		result.TaskIDs = append(result.TaskIDs, taskID)
		result.TasksDeleted++
	}
	for outboxID, outbox := range s.outboxes {
		if outbox.TaskType != DataContentTaskType || outbox.Payload["executionId"] != executionID {
			continue
		}
		delete(s.outboxes, outboxID)
		delete(s.outboxByDedupe, outbox.DedupeKey)
		if outbox.IdempotencyKey != "" {
			delete(s.outboxByIdempotency, outbox.IdempotencyKey)
		}
		result.OutboxesDeleted++
	}
	return result, nil
}

func (s *MemoryStore) listReadyTasksLocked(
	taskTypes []string,
	limit int,
	now time.Time,
	include func(ReliableAsyncTask) bool,
) []ReliableAsyncTask {
	if limit <= 0 {
		limit = 100
	}
	tasks := make([]ReliableAsyncTask, 0, limit)
	for _, task := range s.tasks {
		if len(taskTypes) > 0 && !contains(task.TaskType, taskTypes) {
			continue
		}
		if !include(task) {
			continue
		}
		leaseExpired := !task.LeaseUntil.IsZero() && !task.LeaseUntil.After(now)
		eligible := task.Status == TaskStatusReady ||
			task.Status == TaskStatusRetryWait ||
			(task.Status == TaskStatusProcessing && leaseExpired)
		if !eligible || task.NextAttemptAt.After(now) {
			continue
		}
		task.Payload = CloneStringMap(task.Payload)
		tasks = append(tasks, task)
	}
	sort.Slice(tasks, func(i, j int) bool {
		if tasks[i].NextAttemptAt.Equal(tasks[j].NextAttemptAt) {
			return tasks[i].TaskID < tasks[j].TaskID
		}
		return tasks[i].NextAttemptAt.Before(tasks[j].NextAttemptAt)
	})
	if len(tasks) > limit {
		tasks = tasks[:limit]
	}
	return tasks
}

func (s *MemoryStore) RenewTaskLease(
	ctx context.Context,
	taskID string,
	leaseToken string,
	leaseTTL time.Duration,
	now time.Time,
) (time.Time, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	task, ok := s.tasks[strings.TrimSpace(taskID)]
	if !ok {
		return time.Time{}, ErrTaskNotFound
	}
	now = now.UTC()
	if task.Status != TaskStatusProcessing ||
		task.LeaseToken != strings.TrimSpace(leaseToken) ||
		!task.LeaseUntil.After(now) {
		return time.Time{}, ErrLeaseMismatch
	}
	if leaseTTL <= 0 {
		leaseTTL = 30 * time.Second
	}
	task.LeaseUntil = now.Add(leaseTTL).UTC()
	task.UpdatedAt = now
	s.tasks[task.TaskID] = task
	return task.LeaseUntil, nil
}

func (s *MemoryStore) RecordTaskResult(
	ctx context.Context,
	taskID string,
	leaseToken string,
	result map[string]string,
	now time.Time,
) error {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	task, ok := s.tasks[strings.TrimSpace(taskID)]
	if !ok {
		return ErrTaskNotFound
	}
	if task.Status != TaskStatusProcessing ||
		task.LeaseToken != strings.TrimSpace(leaseToken) ||
		!task.LeaseUntil.After(now.UTC()) {
		return ErrLeaseMismatch
	}
	task.Result = CloneStringMap(result)
	task.UpdatedAt = now.UTC()
	s.tasks[task.TaskID] = task
	return nil
}

func (s *MemoryStore) CompleteTask(ctx context.Context, taskID string, leaseToken string) error {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	task, ok := s.tasks[taskID]
	if !ok {
		return ErrTaskNotFound
	}
	if task.Status != TaskStatusProcessing ||
		task.LeaseToken != leaseToken ||
		!task.LeaseUntil.After(time.Now().UTC()) {
		return ErrLeaseMismatch
	}
	task.Status = TaskStatusSucceeded
	task.LeaseOwner = ""
	task.LeaseToken = ""
	task.UpdatedAt = time.Now().UTC()
	s.tasks[taskID] = task
	return nil
}

func (s *MemoryStore) FailTask(ctx context.Context, taskID string, leaseToken string, failure RuntimeFailure, policy RetryPolicy, now time.Time) error {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	task, ok := s.tasks[taskID]
	if !ok {
		return ErrTaskNotFound
	}
	if task.Status != TaskStatusProcessing ||
		task.LeaseToken != leaseToken ||
		!task.LeaseUntil.After(now.UTC()) {
		return ErrLeaseMismatch
	}
	task.Attempts++
	task.LastFailure = &failure
	task.LeaseOwner = ""
	task.LeaseToken = ""
	task.UpdatedAt = now.UTC()
	if delay, retry := policy.NextDelay(task.Attempts); retry {
		task.Status = TaskStatusRetryWait
		task.NextAttemptAt = now.Add(delay).UTC()
	} else {
		task.Status = TaskStatusDead
	}
	s.tasks[taskID] = task
	return nil
}

func (s *MemoryStore) CreateNotification(ctx context.Context, record NotificationOutboxRecord) (NotificationOutboxRecord, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	now := time.Now().UTC()
	if record.NotificationID == "" {
		record.NotificationID = NewRecordID("notification")
	}
	if record.Status == "" {
		record.Status = NotificationStatusPending
	}
	if record.CreatedAt.IsZero() {
		record.CreatedAt = now
	}
	record.UpdatedAt = now
	record.Payload = CloneStringMap(record.Payload)
	s.notifications[record.NotificationID] = record
	return record, nil
}

func (s *MemoryStore) ClaimNotification(ctx context.Context, eventTypes []string, workerID string, leaseTTL time.Duration, now time.Time) (*NotificationOutboxRecord, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	ids := make([]string, 0, len(s.notifications))
	for id := range s.notifications {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		n := s.notifications[id]
		if !contains(n.EventType, eventTypes) {
			continue
		}
		leaseExpired := !n.LeaseUntil.IsZero() && !n.LeaseUntil.After(now)
		if (n.Status == NotificationStatusPending || n.Status == NotificationStatusRetryWait || (n.Status == NotificationStatusProcessing && leaseExpired)) && !n.NextAttemptAt.After(now) {
			n.Status = NotificationStatusProcessing
			n.LeaseOwner = workerID
			n.LeaseToken = NewRecordID("notification-lease")
			n.LeaseUntil = now.Add(leaseTTL).UTC()
			n.UpdatedAt = now.UTC()
			s.notifications[id] = n
			return &n, nil
		}
	}
	return nil, nil
}

func (s *MemoryStore) EnsureRecipientLedgers(ctx context.Context, notificationID string, eventType string, recipientIDs []string) error {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	now := time.Now().UTC()
	for _, recipientID := range DedupeStrings(recipientIDs) {
		id := DeliveryLedgerID(notificationID, recipientID)
		if _, ok := s.ledgers[id]; ok {
			continue
		}
		s.ledgers[id] = NotificationDeliveryLedgerRecord{
			LedgerID:       id,
			NotificationID: notificationID,
			EventType:      eventType,
			RecipientID:    recipientID,
			Status:         RecipientStatusPending,
			UpdatedAt:      now,
		}
	}
	return nil
}

func (s *MemoryStore) ListPendingRecipients(ctx context.Context, notificationID string) ([]NotificationDeliveryLedgerRecord, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	records := make([]NotificationDeliveryLedgerRecord, 0)
	for _, record := range s.ledgers {
		if record.NotificationID == notificationID && record.Status != RecipientStatusDelivered {
			records = append(records, record)
		}
	}
	sort.Slice(records, func(i, j int) bool {
		return records[i].RecipientID < records[j].RecipientID
	})
	return records, nil
}

func (s *MemoryStore) MarkRecipientDelivered(ctx context.Context, notificationID string, recipientID string, syncSeq int64) error {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	id := DeliveryLedgerID(notificationID, recipientID)
	record := s.ledgers[id]
	record.LedgerID = id
	record.NotificationID = notificationID
	record.RecipientID = recipientID
	record.Status = RecipientStatusDelivered
	record.DeliveredSeq = syncSeq
	record.UpdatedAt = time.Now().UTC()
	record.LastFailure = nil
	s.ledgers[id] = record
	return nil
}

func (s *MemoryStore) MarkRecipientFailed(ctx context.Context, notificationID string, recipientID string, failure RuntimeFailure) error {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	id := DeliveryLedgerID(notificationID, recipientID)
	record := s.ledgers[id]
	record.LedgerID = id
	record.NotificationID = notificationID
	record.RecipientID = recipientID
	record.Status = RecipientStatusFailed
	record.Attempts++
	record.UpdatedAt = time.Now().UTC()
	record.LastFailure = &failure
	s.ledgers[id] = record
	return nil
}

func (s *MemoryStore) RecordProviderAttempt(ctx context.Context, record ProviderAttemptRecord) (ProviderAttemptRecord, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	if strings.TrimSpace(record.AttemptID) == "" {
		record.AttemptID = NewRecordID("attempt")
	}
	if record.CreatedAt.IsZero() {
		record.CreatedAt = time.Now().UTC()
	}
	record.Attributes = CloneStringMap(record.Attributes)
	s.attempts[record.AttemptID] = record
	return record, nil
}

func (s *MemoryStore) ListProviderAttempts(ctx context.Context, requestID string) ([]ProviderAttemptRecord, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	records := make([]ProviderAttemptRecord, 0)
	for _, record := range s.attempts {
		if record.RequestID == strings.TrimSpace(requestID) {
			records = append(records, record)
		}
	}
	sort.Slice(records, func(i, j int) bool {
		return records[i].CreatedAt.Before(records[j].CreatedAt)
	})
	return records, nil
}

func (s *MemoryStore) CompleteNotification(ctx context.Context, notificationID string, leaseToken string) error {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	n, ok := s.notifications[notificationID]
	if !ok {
		return ErrNotificationNotFound
	}
	if n.LeaseToken != leaseToken {
		return ErrLeaseMismatch
	}
	n.Status = NotificationStatusSucceeded
	n.LeaseOwner = ""
	n.LeaseToken = ""
	n.UpdatedAt = time.Now().UTC()
	s.notifications[notificationID] = n
	return nil
}

func (s *MemoryStore) RetryNotification(ctx context.Context, notificationID string, leaseToken string, failure RuntimeFailure, policy RetryPolicy, now time.Time) error {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	n, ok := s.notifications[notificationID]
	if !ok {
		return ErrNotificationNotFound
	}
	if n.LeaseToken != leaseToken {
		return ErrLeaseMismatch
	}
	n.Attempts++
	n.LastFailure = &failure
	n.LeaseOwner = ""
	n.LeaseToken = ""
	n.UpdatedAt = now.UTC()
	if delay, retry := policy.NextDelay(n.Attempts); retry {
		n.Status = NotificationStatusRetryWait
		n.NextAttemptAt = now.Add(delay).UTC()
	} else {
		n.Status = NotificationStatusDead
	}
	s.notifications[notificationID] = n
	return nil
}

func (s *MemoryStore) ClaimShardLease(ctx context.Context, req ClaimShardLeaseRequest) (*TaskLease, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	now := req.Now.UTC()
	if now.IsZero() {
		now = time.Now().UTC()
	}
	ttl := req.LeaseTTL
	if ttl <= 0 {
		ttl = 30 * time.Second
	}
	id := ShardLeaseID(req.Env, req.Domain, req.Module, req.ShardID)
	current := s.leases[id]
	if current.Token != "" && current.Owner != req.Owner && current.LeaseUntil.After(now) {
		return nil, nil
	}
	next := TaskLease{
		Env:        strings.TrimSpace(req.Env),
		Domain:     strings.TrimSpace(req.Domain),
		Module:     strings.TrimSpace(req.Module),
		Owner:      strings.TrimSpace(req.Owner),
		Token:      NewRecordID("shard-lease"),
		ShardID:    req.ShardID,
		LeaseUntil: now.Add(ttl).UTC(),
		UpdatedAt:  now,
	}
	s.leases[id] = next
	return &next, nil
}

func (s *MemoryStore) ListDeadTasks(ctx context.Context, taskTypes []string, limit int) ([]DeadTaskRecord, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]DeadTaskRecord, 0)
	for _, task := range s.tasks {
		if task.Status != TaskStatusDead || !contains(task.TaskType, taskTypes) {
			continue
		}
		out = append(out, DeadTaskRecord{
			TaskID:      task.TaskID,
			TaskType:    task.TaskType,
			AggregateID: task.AggregateID,
			Attempts:    task.Attempts,
			LastFailure: task.LastFailure,
			Payload:     CloneStringMap(task.Payload),
			UpdatedAt:   task.UpdatedAt,
		})
		if limit > 0 && len(out) >= limit {
			break
		}
	}
	return out, nil
}

// FindLatestTaskOutboxByAggregateID 与 Mongo store 行为对齐：返回聚合的
// 最新任务 outbox 记录，供外部交互请求状态查询派生归一化状态。
func (s *MemoryStore) FindLatestTaskOutboxByAggregateID(
	ctx context.Context,
	aggregateID string,
) (TaskOutboxRecord, bool, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	aggregateID = strings.TrimSpace(aggregateID)
	var latest TaskOutboxRecord
	found := false
	for _, record := range s.outboxes {
		if record.AggregateID != aggregateID {
			continue
		}
		if !found || record.UpdatedAt.After(latest.UpdatedAt) {
			latest = record
			found = true
		}
	}
	return latest, found, nil
}

func (s *MemoryStore) RecoverDeadTask(ctx context.Context, taskID string, now time.Time) error {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	task, ok := s.tasks[strings.TrimSpace(taskID)]
	if !ok {
		return ErrTaskNotFound
	}
	if task.Status != TaskStatusDead {
		return nil
	}
	task.Status = TaskStatusReady
	task.NextAttemptAt = now.UTC()
	task.LeaseOwner = ""
	task.LeaseToken = ""
	task.LeaseUntil = time.Time{}
	task.UpdatedAt = now.UTC()
	s.tasks[task.TaskID] = task
	return nil
}

func (s *MemoryStore) ListDeadNotifications(ctx context.Context, eventTypes []string, limit int) ([]DeadNotificationRecord, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]DeadNotificationRecord, 0)
	for _, notification := range s.notifications {
		if notification.Status != NotificationStatusDead || !contains(notification.EventType, eventTypes) {
			continue
		}
		out = append(out, DeadNotificationRecord{
			NotificationID: notification.NotificationID,
			EventType:      notification.EventType,
			AggregateID:    notification.AggregateID,
			Attempts:       notification.Attempts,
			LastFailure:    notification.LastFailure,
			UpdatedAt:      notification.UpdatedAt,
		})
		if limit > 0 && len(out) >= limit {
			break
		}
	}
	return out, nil
}

func (s *MemoryStore) RecoverDeadNotification(ctx context.Context, notificationID string, now time.Time) error {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	notification, ok := s.notifications[strings.TrimSpace(notificationID)]
	if !ok {
		return ErrNotificationNotFound
	}
	if notification.Status != NotificationStatusDead {
		return nil
	}
	notification.Status = NotificationStatusPending
	notification.NextAttemptAt = now.UTC()
	notification.LeaseOwner = ""
	notification.LeaseToken = ""
	notification.LeaseUntil = time.Time{}
	notification.UpdatedAt = now.UTC()
	s.notifications[notification.NotificationID] = notification
	return nil
}

func (s *MemoryStore) CleanupReliableTaskRetention(ctx context.Context, policy RetentionPolicy, now time.Time) (RetentionCleanupResult, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	var result RetentionCleanupResult
	for id, outbox := range s.outboxes {
		if policy.Outbox.DispatchedTTL > 0 && outbox.Status == TaskOutboxStatusDispatched && outbox.UpdatedAt.Before(now.Add(-policy.Outbox.DispatchedTTL)) {
			delete(s.outboxes, id)
			result.OutboxesDeleted++
		}
	}
	for id, task := range s.tasks {
		if (policy.Task.DoneTTL > 0 && task.Status == TaskStatusSucceeded && task.UpdatedAt.Before(now.Add(-policy.Task.DoneTTL))) ||
			(policy.Task.DeadTTL > 0 && task.Status == TaskStatusDead && task.UpdatedAt.Before(now.Add(-policy.Task.DeadTTL))) {
			delete(s.tasks, id)
			result.TasksDeleted++
		}
	}
	for id, notification := range s.notifications {
		if (policy.Notification.DoneTTL > 0 && notification.Status == NotificationStatusSucceeded && notification.UpdatedAt.Before(now.Add(-policy.Notification.DoneTTL))) ||
			(policy.Notification.DeadTTL > 0 && notification.Status == NotificationStatusDead && notification.UpdatedAt.Before(now.Add(-policy.Notification.DeadTTL))) {
			delete(s.notifications, id)
			result.NotificationsDeleted++
		}
	}
	for id, ledger := range s.ledgers {
		if policy.DeliveryLedger.DeliveredTTL > 0 && ledger.Status == RecipientStatusDelivered && ledger.UpdatedAt.Before(now.Add(-policy.DeliveryLedger.DeliveredTTL)) {
			delete(s.ledgers, id)
			result.LedgersDeleted++
		}
	}
	for id, attempt := range s.attempts {
		if policy.DeliveryLedger.DeliveredTTL > 0 && attempt.CreatedAt.Before(now.Add(-policy.DeliveryLedger.DeliveredTTL)) {
			delete(s.attempts, id)
			result.AttemptsDeleted++
		}
	}
	return result, nil
}

func (s *MemoryStore) ReliableTaskMetrics(ctx context.Context) (MetricsSnapshot, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	snapshot := MetricsSnapshot{
		TasksByStatus:         map[string]int64{},
		NotificationsByStatus: map[string]int64{},
		ProviderAttempts:      map[string]int64{},
		UpdatedAt:             time.Now().UTC(),
	}
	for _, task := range s.tasks {
		snapshot.TasksByStatus[task.Status]++
		if task.Status == TaskStatusDead {
			snapshot.DeadTasks++
		}
	}
	for _, notification := range s.notifications {
		snapshot.NotificationsByStatus[notification.Status]++
		if notification.Status == NotificationStatusDead {
			snapshot.DeadNotifications++
		}
	}
	for _, attempt := range s.attempts {
		key := attempt.Operation + ":" + attempt.Provider + ":" + attempt.Status
		snapshot.ProviderAttempts[key]++
	}
	return snapshot, nil
}
