package reliabletask

import (
	"context"
	"testing"
	"time"
)

func TestDLQRecoveryAndRetentionCleanup(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	now := time.Now().UTC()
	record, err := store.DeclareTask(ctx, DeclareTaskRequest{
		TaskType:       "integration.sms_otp.send",
		OwnerDomain:    "integration",
		AggregateType:  "external_interaction",
		AggregateID:    "req-1",
		DedupeKey:      "req-1",
		IdempotencyKey: "req-1",
		PartitionKey:   "req-1",
		Payload:        map[string]string{"requestId": "req-1"},
		PayloadAllow:   []string{"requestId"},
		StartAt:        now,
	})
	if err != nil {
		t.Fatalf("declare task: %v", err)
	}
	if _, err := store.DispatchDueTasks(ctx, now, 10); err != nil {
		t.Fatalf("dispatch task: %v", err)
	}
	task, err := store.ClaimReadyTask(ctx, []string{"integration.sms_otp.send"}, "worker", time.Second, now)
	if err != nil {
		t.Fatalf("claim task: %v", err)
	}
	if task == nil {
		t.Fatal("expected task")
	}
	if err := store.FailTask(ctx, task.TaskID, task.LeaseToken, RuntimeFailure{Code: "TEST.dead", Message: "dead"}, RetryPolicy{MaxAttempts: 1}, now); err != nil {
		t.Fatalf("fail task: %v", err)
	}
	dead, err := store.ListDeadTasks(ctx, []string{"integration.sms_otp.send"}, 10)
	if err != nil {
		t.Fatalf("list dead tasks: %v", err)
	}
	if len(dead) != 1 || dead[0].TaskID != task.TaskID {
		t.Fatalf("unexpected dead tasks: %#v", dead)
	}
	if err := store.RecoverDeadTask(ctx, task.TaskID, now.Add(time.Second)); err != nil {
		t.Fatalf("recover task: %v", err)
	}
	recovered, err := store.ClaimReadyTask(ctx, []string{"integration.sms_otp.send"}, "worker-2", time.Second, now.Add(time.Second))
	if err != nil {
		t.Fatalf("claim recovered task: %v", err)
	}
	if recovered == nil || recovered.TaskID != task.TaskID {
		t.Fatalf("unexpected recovered task: %#v", recovered)
	}
	if err := store.CompleteTask(ctx, recovered.TaskID, recovered.LeaseToken); err != nil {
		t.Fatalf("complete recovered task: %v", err)
	}
	cleanup, err := store.CleanupReliableTaskRetention(ctx, RetentionPolicy{
		Outbox: RetentionBucket{DispatchedTTL: time.Nanosecond},
		Task:   RetentionBucket{DoneTTL: time.Nanosecond},
	}, now.Add(time.Hour))
	if err != nil {
		t.Fatalf("cleanup: %v", err)
	}
	if cleanup.OutboxesDeleted == 0 || cleanup.TasksDeleted == 0 {
		t.Fatalf("cleanup did not remove old records: %#v outbox=%s", cleanup, record.OutboxID)
	}
}

func TestRateLimiterBlocksAfterPerSecondBudget(t *testing.T) {
	limiter := NewRateLimiter()
	if !limiter.Allow("sms", 1) {
		t.Fatal("first claim should pass")
	}
	if limiter.Allow("sms", 1) {
		t.Fatal("second claim in same second should be blocked")
	}
}

func TestReliableTaskMetricsSnapshot(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	now := time.Now().UTC()
	if _, err := store.RecordProviderAttempt(ctx, ProviderAttemptRecord{
		RequestID: "req-1",
		Operation: ExternalInteractionOperationSmsOTP,
		Provider:  "mock_sms",
		Status:    ExternalInteractionStatusDelivered,
		CreatedAt: now,
	}); err != nil {
		t.Fatalf("record attempt: %v", err)
	}
	snapshot, err := store.ReliableTaskMetrics(ctx)
	if err != nil {
		t.Fatalf("metrics: %v", err)
	}
	if snapshot.ProviderAttempts[ExternalInteractionOperationSmsOTP+":mock_sms:"+ExternalInteractionStatusDelivered] != 1 {
		t.Fatalf("missing provider attempt metric: %#v", snapshot.ProviderAttempts)
	}
}
