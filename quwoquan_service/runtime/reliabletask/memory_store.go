package reliabletask

import (
	"context"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

type MemoryStore struct {
	mu             sync.Mutex
	outboxes       map[string]TaskOutboxRecord
	outboxByDedupe map[string]string
	tasks          map[string]ReliableAsyncTask
	taskByDedupe   map[string]string
	notifications  map[string]NotificationOutboxRecord
	ledgers        map[string]NotificationDeliveryLedgerRecord
	leases         map[string]TaskLease
}

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{
		outboxes:       map[string]TaskOutboxRecord{},
		outboxByDedupe: map[string]string{},
		tasks:          map[string]ReliableAsyncTask{},
		taskByDedupe:   map[string]string{},
		notifications:  map[string]NotificationOutboxRecord{},
		ledgers:        map[string]NotificationDeliveryLedgerRecord{},
		leases:         map[string]TaskLease{},
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
	if err := validatePayloadAllowlist(req.Payload, req.PayloadAllow); err != nil {
		return TaskOutboxRecord{}, err
	}
	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now().UTC()
	startAt, maxDelayUntil := normalizeStartAt(req, now)
	dedupeKey := strings.TrimSpace(req.DedupeKey)
	if dedupeKey == "" {
		dedupeKey = strings.TrimSpace(req.TaskType) + ":" + strings.TrimSpace(req.AggregateID)
	}
	if existingID := s.outboxByDedupe[dedupeKey]; existingID != "" {
		existing := s.outboxes[existingID]
		if existing.Status == TaskOutboxStatusPending {
			existing.Payload = mergePayload(existing.Payload, req.Payload)
			existing.Trigger = mergeCSV(existing.Trigger, req.Trigger)
			existing.StartAt = extendStartAt(existing, req, now)
			if existing.MaxDelayUntil.IsZero() && !maxDelayUntil.IsZero() {
				existing.MaxDelayUntil = maxDelayUntil
			}
			existing.UpdatedAt = now
			s.outboxes[existingID] = existing
			return existing, nil
		}
	}

	record := TaskOutboxRecord{
		OutboxID:        newID("outbox"),
		TaskType:        strings.TrimSpace(req.TaskType),
		OwnerDomain:     strings.TrimSpace(req.OwnerDomain),
		AggregateType:   strings.TrimSpace(req.AggregateType),
		AggregateID:     strings.TrimSpace(req.AggregateID),
		DedupeKey:       dedupeKey,
		IdempotencyKey:  strings.TrimSpace(req.IdempotencyKey),
		PartitionKey:    strings.TrimSpace(req.PartitionKey),
		ShardID:         shardIDForRequest(req),
		Payload:         clonePayload(req.Payload),
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
	return record, nil
}

func (s *MemoryStore) DispatchDueTasks(ctx context.Context, now time.Time, limit int) ([]ReliableAsyncTask, error) {
	return s.DispatchDueTasksForShard(ctx, now, limit, -1)
}

func (s *MemoryStore) DispatchDueTasksForShard(ctx context.Context, now time.Time, limit int, shardID int) ([]ReliableAsyncTask, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	if limit <= 0 {
		limit = 100
	}
	outboxes := make([]TaskOutboxRecord, 0, len(s.outboxes))
	for _, record := range s.outboxes {
		if shardID >= 0 && record.ShardID != shardID {
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
				TaskID:         newID("task"),
				OutboxID:       outbox.OutboxID,
				TaskType:       outbox.TaskType,
				OwnerDomain:    outbox.OwnerDomain,
				AggregateType:  outbox.AggregateType,
				AggregateID:    outbox.AggregateID,
				DedupeKey:      outbox.DedupeKey,
				IdempotencyKey: outbox.IdempotencyKey,
				PartitionKey:   outbox.PartitionKey,
				ShardID:        outbox.ShardID,
				Payload:        clonePayload(outbox.Payload),
				Status:         TaskStatusReady,
				NextAttemptAt:  now.UTC(),
				CreatedAt:      now.UTC(),
				UpdatedAt:      now.UTC(),
			}
			s.taskByDedupe[task.DedupeKey] = task.TaskID
		} else {
			task.Payload = mergePayload(task.Payload, outbox.Payload)
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
			task.LeaseToken = newID("lease")
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
	task.LeaseToken = newID("lease")
	task.LeaseUntil = now.Add(leaseTTL).UTC()
	task.UpdatedAt = now.UTC()
	s.tasks[task.TaskID] = task
	return &task, nil
}

func (s *MemoryStore) CompleteTask(ctx context.Context, taskID string, leaseToken string) error {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	task, ok := s.tasks[taskID]
	if !ok {
		return ErrTaskNotFound
	}
	if task.LeaseToken != leaseToken {
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
	if task.LeaseToken != leaseToken {
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
		record.NotificationID = newID("notification")
	}
	if record.Status == "" {
		record.Status = NotificationStatusPending
	}
	if record.CreatedAt.IsZero() {
		record.CreatedAt = now
	}
	record.UpdatedAt = now
	record.Payload = clonePayload(record.Payload)
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
			n.LeaseToken = newID("notification-lease")
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
	for _, recipientID := range dedupeStrings(recipientIDs) {
		id := ledgerID(notificationID, recipientID)
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
	id := ledgerID(notificationID, recipientID)
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
	id := ledgerID(notificationID, recipientID)
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
	id := shardLeaseID(req.Env, req.Domain, req.Module, req.ShardID)
	current := s.leases[id]
	if current.Token != "" && current.Owner != req.Owner && current.LeaseUntil.After(now) {
		return nil, nil
	}
	next := TaskLease{
		Env:        strings.TrimSpace(req.Env),
		Domain:     strings.TrimSpace(req.Domain),
		Module:     strings.TrimSpace(req.Module),
		Owner:      strings.TrimSpace(req.Owner),
		Token:      newID("shard-lease"),
		ShardID:    req.ShardID,
		LeaseUntil: now.Add(ttl).UTC(),
		UpdatedAt:  now,
	}
	s.leases[id] = next
	return &next, nil
}

func dedupeStrings(values []string) []string {
	seen := map[string]struct{}{}
	out := make([]string, 0, len(values))
	for _, raw := range values {
		value := strings.TrimSpace(raw)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		out = append(out, value)
	}
	sort.Strings(out)
	return out
}

func ledgerID(notificationID string, recipientID string) string {
	return strings.TrimSpace(notificationID) + ":" + strings.TrimSpace(recipientID)
}

func shardLeaseID(env string, domain string, module string, shardID int) string {
	return strings.TrimSpace(env) + ":" + strings.TrimSpace(domain) + ":" + strings.TrimSpace(module) + ":" + strconv.Itoa(shardID)
}
