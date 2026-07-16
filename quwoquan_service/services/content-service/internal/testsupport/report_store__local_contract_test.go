package testsupport

import (
	"context"
	"reflect"
	"testing"
	"time"

	reportports "quwoquan_service/services/content-service/internal/domain/report/ports"
)

func TestReportStoreExpiredReceiptIsNotReplayed(t *testing.T) {
	t.Parallel()

	store := NewReportStore()
	store.receipts["expired-key"] = reportReceipt{
		commandName:   "CreateReport",
		commandDigest: "digest",
		expiresAt:     time.Now().UTC().Add(-time.Second),
	}

	_, found, err := store.FindReceipt(
		context.Background(),
		"expired-key",
		"CreateReport",
		"digest",
	)
	if err != nil {
		t.Fatalf("FindReceipt() error = %v", err)
	}
	if found {
		t.Fatal("expired receipt must not replay a command")
	}
	if _, exists := store.receipts["expired-key"]; exists {
		t.Fatal("expired receipt must be purged after lookup")
	}
}

func TestReportStoreOutboxReaderUsesStableTransactionalSequenceOrder(t *testing.T) {
	t.Parallel()

	store := NewReportStore()
	occurredAt := time.Date(2026, time.July, 13, 12, 0, 0, 0, time.UTC)
	store.outbox = []reportOutboxRecord{
		{event: reportports.OutboxEvent{EventID: "evt-z", OccurredAt: occurredAt}, sequence: 2},
		{event: reportports.OutboxEvent{EventID: "evt-a", OccurredAt: occurredAt}, sequence: 1},
		{event: reportports.OutboxEvent{EventID: "evt-later", OccurredAt: occurredAt.Add(time.Nanosecond)}, sequence: 3},
	}

	events, err := store.ReadAfter(context.Background(), "", 10)
	if err != nil {
		t.Fatalf("ReadAfter() error = %v", err)
	}
	gotIDs := make([]string, 0, len(events))
	for _, event := range events {
		gotIDs = append(gotIDs, event.EventID)
		if event.Checkpoint == "" {
			t.Fatalf("event %q has no replay checkpoint", event.EventID)
		}
	}
	if want := []string{"evt-a", "evt-z", "evt-later"}; !reflect.DeepEqual(gotIDs, want) {
		t.Fatalf("ReadAfter() ids = %v, want %v", gotIDs, want)
	}

	events, err = store.ReadAfter(context.Background(), events[1].Checkpoint, 10)
	if err != nil {
		t.Fatalf("ReadAfter(after checkpoint) error = %v", err)
	}
	if len(events) != 1 || events[0].EventID != "evt-later" {
		t.Fatalf("ReadAfter(after checkpoint) = %#v, want evt-later only", events)
	}
}

func TestReportStoreCheckpointLeaseIsConsumerScopedAndRollbackSafe(t *testing.T) {
	t.Parallel()

	store := NewReportStore()
	occurredAt := time.Date(2026, time.July, 13, 12, 0, 0, 0, time.UTC)
	store.outbox = []reportOutboxRecord{{
		event:    reportports.OutboxEvent{EventID: "evt-1", OccurredAt: occurredAt},
		sequence: 1,
	}}
	events, err := store.ReadAfter(context.Background(), "", 1)
	if err != nil {
		t.Fatalf("ReadAfter() error = %v", err)
	}
	checkpoint := events[0].Checkpoint

	first, acquired, err := store.AcquireCheckpoint(context.Background(), "consumer-a")
	if err != nil || !acquired {
		t.Fatalf("first AcquireCheckpoint() = (%v, %t, %v), want acquired", first, acquired, err)
	}
	if _, acquired, err := store.AcquireCheckpoint(context.Background(), "consumer-a"); err != nil || acquired {
		t.Fatalf("same consumer must not acquire while locked, acquired=%t err=%v", acquired, err)
	}
	other, acquired, err := store.AcquireCheckpoint(context.Background(), "consumer-b")
	if err != nil || !acquired {
		t.Fatalf("other consumer must use an independent checkpoint, acquired=%t err=%v", acquired, err)
	}
	if err := other.Rollback(); err != nil {
		t.Fatalf("other Rollback() error = %v", err)
	}
	if err := first.SaveCheckpoint(context.Background(), checkpoint); err != nil {
		t.Fatalf("first SaveCheckpoint() error = %v", err)
	}
	if err := first.Rollback(); err != nil {
		t.Fatalf("first Rollback() error = %v", err)
	}

	retry, acquired, err := store.AcquireCheckpoint(context.Background(), "consumer-a")
	if err != nil || !acquired {
		t.Fatalf("retry AcquireCheckpoint() acquired=%t err=%v", acquired, err)
	}
	if got := retry.Checkpoint(); got != "" {
		t.Fatalf("checkpoint after rollback = %q, want empty", got)
	}
	if err := retry.SaveCheckpoint(context.Background(), checkpoint); err != nil {
		t.Fatalf("retry SaveCheckpoint() error = %v", err)
	}
	if err := retry.Commit(context.Background()); err != nil {
		t.Fatalf("retry Commit() error = %v", err)
	}

	committed, acquired, err := store.AcquireCheckpoint(context.Background(), "consumer-a")
	if err != nil || !acquired {
		t.Fatalf("committed AcquireCheckpoint() acquired=%t err=%v", acquired, err)
	}
	if got := committed.Checkpoint(); got != checkpoint {
		t.Fatalf("consumer-a checkpoint = %q, want %q", got, checkpoint)
	}
	if err := committed.Rollback(); err != nil {
		t.Fatalf("committed Rollback() error = %v", err)
	}
}
