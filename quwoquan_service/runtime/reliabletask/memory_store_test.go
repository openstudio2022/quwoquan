package reliabletask

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestMemoryStoreMergesDelayedOutboxAndDispatchesOnlyDue(t *testing.T) {
	store := NewMemoryStore()
	now := time.Date(2026, 5, 1, 10, 0, 0, 0, time.UTC)
	req := DeclareTaskRequest{
		TaskType:      "chat.group_avatar.recompute",
		OwnerDomain:   "chat",
		AggregateType: "conversationId",
		AggregateID:   "conv-1",
		DedupeKey:     "chat.group_avatar.recompute:conv-1",
		PartitionKey:  "conv-1",
		Payload:       map[string]string{"rosterRevision": "1", "triggers": "created"},
		PayloadAllow:  []string{"rosterRevision", "triggers"},
		Trigger:       "created",
		StartAt:       now.Add(time.Minute),
		MaxDelayUntil: now.Add(10 * time.Minute),
	}
	if _, err := store.DeclareTask(context.Background(), req); err != nil {
		t.Fatalf("declare first task: %v", err)
	}
	req.Payload = map[string]string{"rosterRevision": "2", "triggers": "members.added"}
	req.Trigger = "members.added"
	req.StartAt = now.Add(2 * time.Minute)
	record, err := store.DeclareTask(context.Background(), req)
	if err != nil {
		t.Fatalf("declare merged task: %v", err)
	}
	if got := record.Payload["rosterRevision"]; got != "2" {
		t.Fatalf("merged rosterRevision = %s, want 2", got)
	}
	if got := record.Payload["triggers"]; got != "created,members.added" {
		t.Fatalf("merged triggers = %s", got)
	}

	tasks, err := store.DispatchDueTasks(context.Background(), now.Add(30*time.Second), 10)
	if err != nil {
		t.Fatalf("dispatch early: %v", err)
	}
	if len(tasks) != 0 {
		t.Fatalf("early dispatch produced %d tasks", len(tasks))
	}

	tasks, err = store.DispatchDueTasks(context.Background(), now.Add(2*time.Minute), 10)
	if err != nil {
		t.Fatalf("dispatch due: %v", err)
	}
	if len(tasks) != 1 {
		t.Fatalf("due dispatch produced %d tasks", len(tasks))
	}
}

func TestMemoryStoreLeaseAckRetryAndDLQ(t *testing.T) {
	store := NewMemoryStore()
	now := time.Now().UTC()
	req := DeclareTaskRequest{
		TaskType:      "chat.group_avatar.recompute",
		OwnerDomain:   "chat",
		AggregateType: "conversationId",
		AggregateID:   "conv-1",
		DedupeKey:     "chat.group_avatar.recompute:conv-1",
		PartitionKey:  "conv-1",
		Payload:       map[string]string{"rosterRevision": "1"},
		PayloadAllow:  []string{"rosterRevision"},
		StartAt:       now,
	}
	if _, err := store.DeclareTask(context.Background(), req); err != nil {
		t.Fatalf("declare task: %v", err)
	}
	if _, err := store.DispatchDueTasks(context.Background(), now, 10); err != nil {
		t.Fatalf("dispatch task: %v", err)
	}
	task, err := store.ClaimReadyTask(context.Background(), []string{"chat.group_avatar.recompute"}, "worker-a", time.Second, now)
	if err != nil || task == nil {
		t.Fatalf("claim task = %v, %v", task, err)
	}
	if err := store.CompleteTask(context.Background(), task.TaskID, "bad-token"); !errors.Is(err, ErrLeaseMismatch) {
		t.Fatalf("bad ack err = %v, want lease mismatch", err)
	}
	if err := store.FailTask(context.Background(), task.TaskID, task.LeaseToken, RuntimeFailure{Code: "CHAT.GROUP_AVATAR.transient"}, RetryPolicy{MaxAttempts: 1}, now); err != nil {
		t.Fatalf("fail task: %v", err)
	}
	claimed, err := store.ClaimReadyTask(context.Background(), []string{"chat.group_avatar.recompute"}, "worker-b", time.Second, now.Add(time.Hour))
	if err != nil {
		t.Fatalf("claim after dlq: %v", err)
	}
	if claimed != nil {
		t.Fatalf("dead task should not be claimable: %#v", claimed)
	}
}

func TestMemoryStoreNotificationRecipientLedgerRetriesOnlyFailedRecipients(t *testing.T) {
	store := NewMemoryStore()
	notification, err := store.CreateNotification(context.Background(), NotificationOutboxRecord{
		EventType:     "conversation.avatar.updated",
		OwnerDomain:   "chat",
		AggregateType: "conversation",
		AggregateID:   "conv-1",
		Payload:       map[string]string{"avatarUrl": "https://cdn/avatar.png"},
		RecipientIDs:  []string{"u1", "u2", "u1"},
	})
	if err != nil {
		t.Fatalf("create notification: %v", err)
	}
	if err := store.EnsureRecipientLedgers(context.Background(), notification.NotificationID, notification.EventType, notification.RecipientIDs); err != nil {
		t.Fatalf("ensure ledger: %v", err)
	}
	if err := store.MarkRecipientDelivered(context.Background(), notification.NotificationID, "u1", 1); err != nil {
		t.Fatalf("mark u1 delivered: %v", err)
	}
	if err := store.MarkRecipientFailed(context.Background(), notification.NotificationID, "u2", RuntimeFailure{Code: "MQ.MIDDLEWARE.transient"}); err != nil {
		t.Fatalf("mark u2 failed: %v", err)
	}
	pending, err := store.ListPendingRecipients(context.Background(), notification.NotificationID)
	if err != nil {
		t.Fatalf("list pending: %v", err)
	}
	if len(pending) != 1 || pending[0].RecipientID != "u2" {
		t.Fatalf("pending recipients = %#v, want u2 only", pending)
	}
}

func TestNotificationWorkerRetriesOnlyFailedRecipients(t *testing.T) {
	store := NewMemoryStore()
	notification, err := store.CreateNotification(context.Background(), NotificationOutboxRecord{
		EventType:     "conversation.avatar.updated",
		OwnerDomain:   "chat",
		AggregateType: "conversation",
		AggregateID:   "conv-notify",
		Payload:       map[string]string{"avatarUrl": "https://cdn/avatar.png"},
		RecipientIDs:  []string{"u1", "u2"},
		Status:        NotificationStatusPending,
		NextAttemptAt: time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("create notification: %v", err)
	}
	worker := NotificationWorker{
		Store:      store,
		EventTypes: []string{"conversation.avatar.updated"},
		WorkerID:   "notification-worker",
		LeaseTTL:   time.Minute,
		Retry:      RetryPolicy{MaxAttempts: 3, Backoff: []time.Duration{time.Millisecond}},
	}
	workerNow := time.Now().UTC()
	worker.Now = func() time.Time { return workerNow }
	first := true
	processed, err := worker.ProcessOne(context.Background(), func(ctx context.Context, n NotificationOutboxRecord, recipientID string) (int64, error) {
		_ = ctx
		if n.NotificationID != notification.NotificationID {
			t.Fatalf("notification id = %s, want %s", n.NotificationID, notification.NotificationID)
		}
		if recipientID == "u2" && first {
			return 0, errors.New("transient fanout failure")
		}
		return 100, nil
	})
	if err != nil || !processed {
		t.Fatalf("first process = %v, %v", processed, err)
	}
	pending, err := store.ListPendingRecipients(context.Background(), notification.NotificationID)
	if err != nil {
		t.Fatalf("list after partial failure: %v", err)
	}
	if len(pending) != 1 || pending[0].RecipientID != "u2" {
		t.Fatalf("pending after partial failure = %#v, want u2 only", pending)
	}
	first = false
	workerNow = workerNow.Add(time.Second)
	processed, err = worker.ProcessOne(context.Background(), func(ctx context.Context, n NotificationOutboxRecord, recipientID string) (int64, error) {
		_, _ = ctx, n
		if recipientID != "u2" {
			t.Fatalf("second pass recipient = %s, want u2 only", recipientID)
		}
		return 101, nil
	})
	if err != nil || !processed {
		t.Fatalf("second process = %v, %v", processed, err)
	}
	pending, err = store.ListPendingRecipients(context.Background(), notification.NotificationID)
	if err != nil {
		t.Fatalf("list after retry: %v", err)
	}
	if len(pending) != 0 {
		t.Fatalf("pending after retry = %#v, want none", pending)
	}
}

func TestCatalogLoaderValidatesChatAvatarTask(t *testing.T) {
	catalog, err := LoadCatalog("../../../deploy/shared/reliable_task_module_catalog.yaml")
	if err != nil {
		t.Fatalf("load catalog: %v", err)
	}
	req, err := catalog.DeclareRequestForTask(
		"chat.group_avatar.recompute",
		"conv-1",
		map[string]string{"rosterRevision": "1", "triggers": "members.added", "actorID": "user-1"},
		"members.added",
		time.Now().UTC(),
	)
	if err != nil {
		t.Fatalf("build declare request: %v", err)
	}
	if req.StartAt.Before(time.Now().UTC().Add(55 * time.Second)) {
		t.Fatalf("startAt did not apply catalog delay: %s", req.StartAt)
	}
	policy := catalog.Tasks["chat.group_avatar.recompute"].RetryPolicyConfig()
	if policy.MaxAttempts != 8 {
		t.Fatalf("retry max attempts = %d, want 8", policy.MaxAttempts)
	}
	if delay, retry := policy.NextDelay(3); !retry || delay <= 0 {
		t.Fatalf("exponential retry policy did not return delay: delay=%s retry=%v", delay, retry)
	}
	_, err = catalog.DeclareRequestForTask(
		"chat.group_avatar.recompute",
		"conv-1",
		map[string]string{"conversationId": "conv-1"},
		"bad",
		time.Now().UTC(),
	)
	if !errors.Is(err, ErrPayloadNotAllowed) {
		t.Fatalf("invalid payload err = %v", err)
	}
}

type failingTransactionStore struct {
	*MemoryStore
	err error
}

func (s failingTransactionStore) RunInTransaction(ctx context.Context, fn func(context.Context) error) error {
	_ = fn
	return s.err
}

func TestTaskOutboxWriterUsesTransactionBoundary(t *testing.T) {
	store := NewMemoryStore()
	writer := NewTaskOutboxWriter(store)
	req := DeclareTaskRequest{
		TaskType:      "chat.group_avatar.recompute",
		OwnerDomain:   "chat",
		AggregateType: "conversationId",
		AggregateID:   "conv-writer",
		PartitionKey:  "conv-writer",
		Payload:       map[string]string{"rosterRevision": "1"},
		PayloadAllow:  []string{"rosterRevision"},
		StartAt:       time.Now().UTC(),
	}
	record, err := writer.AddTask(context.Background(), req)
	if err != nil {
		t.Fatalf("writer add task: %v", err)
	}
	if record.OutboxID == "" {
		t.Fatalf("writer returned empty outbox id")
	}

	txErr := errors.New("transaction unavailable")
	failing := failingTransactionStore{MemoryStore: NewMemoryStore(), err: txErr}
	_, err = NewTaskOutboxWriter(failing).AddTask(context.Background(), req)
	if !errors.Is(err, txErr) {
		t.Fatalf("writer error = %v, want %v", err, txErr)
	}
	tasks, err := failing.DispatchDueTasks(context.Background(), time.Now().UTC().Add(time.Hour), 10)
	if err != nil {
		t.Fatalf("dispatch failing store: %v", err)
	}
	if len(tasks) != 0 {
		t.Fatalf("failed transaction should not declare tasks: %#v", tasks)
	}
}

func TestDispatcherUsesShardLeaseAndShardFilter(t *testing.T) {
	store := NewMemoryStore()
	now := time.Now().UTC()
	for _, req := range []DeclareTaskRequest{
		{
			TaskType:      "chat.group_avatar.recompute",
			OwnerDomain:   "chat",
			AggregateType: "conversationId",
			AggregateID:   "conv-shard-7",
			DedupeKey:     "chat.group_avatar.recompute:conv-shard-7",
			PartitionKey:  "conv-shard-7",
			ShardID:       7,
			Payload:       map[string]string{"rosterRevision": "1"},
			PayloadAllow:  []string{"rosterRevision"},
			StartAt:       now,
		},
		{
			TaskType:      "chat.group_avatar.recompute",
			OwnerDomain:   "chat",
			AggregateType: "conversationId",
			AggregateID:   "conv-shard-8",
			DedupeKey:     "chat.group_avatar.recompute:conv-shard-8",
			PartitionKey:  "conv-shard-8",
			ShardID:       8,
			Payload:       map[string]string{"rosterRevision": "1"},
			PayloadAllow:  []string{"rosterRevision"},
			StartAt:       now,
		},
	} {
		if _, err := store.DeclareTask(context.Background(), req); err != nil {
			t.Fatalf("declare %s: %v", req.AggregateID, err)
		}
	}

	dispatcher := Dispatcher{
		Store:    store,
		Env:      "alpha",
		Domain:   "chat",
		Module:   "chat.task_outbox_dispatcher",
		Owner:    "dispatcher-a",
		ShardID:  7,
		LeaseTTL: time.Minute,
		Now:      func() time.Time { return now },
	}
	tasks, err := dispatcher.DispatchDue(context.Background(), 10)
	if err != nil {
		t.Fatalf("dispatch shard 7: %v", err)
	}
	if len(tasks) != 1 || tasks[0].ShardID != 7 || tasks[0].AggregateID != "conv-shard-7" {
		t.Fatalf("shard dispatch tasks = %#v, want only shard 7", tasks)
	}

	blocked := dispatcher
	blocked.Owner = "dispatcher-b"
	tasks, err = blocked.DispatchDue(context.Background(), 10)
	if err != nil {
		t.Fatalf("blocked dispatch: %v", err)
	}
	if len(tasks) != 0 {
		t.Fatalf("blocked dispatcher should not dispatch tasks: %#v", tasks)
	}

	takeover := blocked
	takeover.Now = func() time.Time { return now.Add(2 * time.Minute) }
	takeover.ShardID = 8
	tasks, err = takeover.DispatchDue(context.Background(), 10)
	if err != nil {
		t.Fatalf("takeover shard 8: %v", err)
	}
	if len(tasks) != 1 || tasks[0].ShardID != 8 || tasks[0].AggregateID != "conv-shard-8" {
		t.Fatalf("takeover tasks = %#v, want only shard 8", tasks)
	}
}

type memoryReadyIndex struct {
	messages []ReadyIndexMessage
	acked    []string
}

func (i *memoryReadyIndex) Ensure(ctx context.Context) error {
	_ = ctx
	return nil
}

func (i *memoryReadyIndex) EnqueueReadyOrMerge(ctx context.Context, task ReliableAsyncTask) error {
	_ = ctx
	i.messages = append(i.messages, ReadyIndexMessage{
		StreamID: "test-stream",
		TaskID:   task.TaskID,
		TaskType: task.TaskType,
		RawID:    "msg-" + task.TaskID,
	})
	return nil
}

func (i *memoryReadyIndex) Claim(ctx context.Context, consumer string, count int64, block time.Duration) ([]ReadyIndexMessage, error) {
	_, _, _ = ctx, consumer, block
	if count <= 0 {
		count = 1
	}
	if len(i.messages) == 0 {
		return nil, nil
	}
	if int(count) > len(i.messages) {
		count = int64(len(i.messages))
	}
	out := append([]ReadyIndexMessage(nil), i.messages[:count]...)
	i.messages = i.messages[count:]
	return out, nil
}

func (i *memoryReadyIndex) Ack(ctx context.Context, message ReadyIndexMessage) error {
	_ = ctx
	i.acked = append(i.acked, message.RawID)
	return nil
}

func TestDispatcherReadyIndexAndWorkerProcessOne(t *testing.T) {
	store := NewMemoryStore()
	ready := &memoryReadyIndex{}
	now := time.Now().UTC()
	if _, err := store.DeclareTask(context.Background(), DeclareTaskRequest{
		TaskType:      "chat.group_avatar.recompute",
		OwnerDomain:   "chat",
		AggregateType: "conversationId",
		AggregateID:   "conv-ready",
		DedupeKey:     "chat.group_avatar.recompute:conv-ready",
		PartitionKey:  "conv-ready",
		Payload:       map[string]string{"rosterRevision": "1"},
		PayloadAllow:  []string{"rosterRevision"},
		StartAt:       now,
	}); err != nil {
		t.Fatalf("declare task: %v", err)
	}

	dispatcher := Dispatcher{
		Store: store,
		Ready: ready,
		Now:   func() time.Time { return now },
	}
	tasks, err := dispatcher.DispatchDue(context.Background(), 10)
	if err != nil {
		t.Fatalf("dispatch due: %v", err)
	}
	if len(tasks) != 1 || len(ready.messages) != 1 {
		t.Fatalf("dispatch tasks=%d ready=%d, want 1/1", len(tasks), len(ready.messages))
	}

	worker := Worker{
		Store:     store,
		Ready:     ready,
		TaskTypes: []string{"chat.group_avatar.recompute"},
		WorkerID:  "worker-ready",
		LeaseTTL:  time.Minute,
		Now:       func() time.Time { return now },
	}
	processed, err := worker.ProcessOne(context.Background(), func(ctx context.Context, task ReliableAsyncTask) error {
		_ = ctx
		if task.AggregateID != "conv-ready" {
			t.Fatalf("worker got aggregate %s, want conv-ready", task.AggregateID)
		}
		return nil
	})
	if err != nil || !processed {
		t.Fatalf("process one = %v, %v", processed, err)
	}
	if len(ready.acked) != 1 {
		t.Fatalf("ready index acked %d messages, want 1", len(ready.acked))
	}
	claimed, err := store.ClaimReadyTask(context.Background(), []string{"chat.group_avatar.recompute"}, "worker-b", time.Minute, now.Add(time.Minute))
	if err != nil {
		t.Fatalf("claim completed task: %v", err)
	}
	if claimed != nil {
		t.Fatalf("completed task should not be claimable: %#v", claimed)
	}
}

func TestPolicyCatalogLoaderAndShardLease(t *testing.T) {
	policies, err := LoadPolicyCatalog("../../../deploy/shared/reliable_task_retention_policy.yaml")
	if err != nil {
		t.Fatalf("load policy catalog: %v", err)
	}
	if policies.Policies["reliabletask.retention.standard.v1"].DLQ.TTL <= 0 {
		t.Fatalf("expected standard dlq ttl")
	}
	if policies.RateLimits["reliabletask.rate.chat_avatar.v1"].ClaimPerSecond <= 0 {
		t.Fatalf("expected chat avatar rate limit")
	}
	catalog, err := LoadCatalogWithPolicies(
		"../../../deploy/shared/reliable_task_module_catalog.yaml",
		"../../../deploy/shared/reliable_task_retention_policy.yaml",
	)
	if err != nil {
		t.Fatalf("load catalog with policies: %v", err)
	}
	if len(catalog.Policies.Policies) == 0 {
		t.Fatalf("expected policies attached to catalog")
	}

	store := NewMemoryStore()
	now := time.Now().UTC()
	lease, err := store.ClaimShardLease(context.Background(), ClaimShardLeaseRequest{
		Env:      "alpha",
		Domain:   "chat",
		Module:   "chat.task_outbox_dispatcher",
		Owner:    "dispatcher-a",
		ShardID:  0,
		LeaseTTL: time.Minute,
		Now:      now,
	})
	if err != nil || lease == nil {
		t.Fatalf("claim shard lease: %#v %v", lease, err)
	}
	blocked, err := store.ClaimShardLease(context.Background(), ClaimShardLeaseRequest{
		Env:      "alpha",
		Domain:   "chat",
		Module:   "chat.task_outbox_dispatcher",
		Owner:    "dispatcher-b",
		ShardID:  0,
		LeaseTTL: time.Minute,
		Now:      now.Add(time.Second),
	})
	if err != nil {
		t.Fatalf("claim blocked lease: %v", err)
	}
	if blocked != nil {
		t.Fatalf("expected active lease to block other owner: %#v", blocked)
	}
	taken, err := store.ClaimShardLease(context.Background(), ClaimShardLeaseRequest{
		Env:      "alpha",
		Domain:   "chat",
		Module:   "chat.task_outbox_dispatcher",
		Owner:    "dispatcher-b",
		ShardID:  0,
		LeaseTTL: time.Minute,
		Now:      now.Add(2 * time.Minute),
	})
	if err != nil || taken == nil || taken.Owner != "dispatcher-b" {
		t.Fatalf("expected expired lease takeover: %#v %v", taken, err)
	}
}
