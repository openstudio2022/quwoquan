package testsupport

import (
	"context"
	"testing"
	"time"

	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
)

func TestPostStoreExpiredReceiptDoesNotReplayNewCommand(t *testing.T) {
	t.Parallel()

	store := NewPostStore(nil)
	store.receipts["expired-key"] = postReceipt{
		commandName:   "CreatePost",
		commandDigest: "old-digest",
		post:          postmodel.Post{ID: "old-post"},
		expiresAt:     time.Now().UTC().Add(-time.Second),
	}

	result, err := store.Commit(context.Background(), postports.Commit{
		Post:             &postmodel.Post{ID: "new-post"},
		ExpectedVersion:  0,
		IdempotencyKey:   "expired-key",
		CommandName:      "CreatePost",
		CommandDigest:    "new-digest",
		ReceiptExpiresAt: time.Now().UTC().Add(time.Hour),
	})
	if err != nil {
		t.Fatalf("Commit() error = %v", err)
	}
	if result.Replayed {
		t.Fatal("expired receipt must not replay the old post command")
	}
	if result.Post == nil || result.Post.ID != "new-post" {
		t.Fatalf("Commit() post = %#v, want new-post", result.Post)
	}
}

func TestPostStoreOutboxUsesDurableConsumerCheckpoint(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.July, 13, 10, 0, 0, 0, time.UTC)
	store := NewPostStore(nil)
	store.outbox = []postports.OutboxEvent{
		{EventID: "event-1", OccurredAt: now},
		{EventID: "event-2", OccurredAt: now.Add(time.Second)},
	}

	events, err := store.ReadAfter(context.Background(), "", 1)
	if err != nil {
		t.Fatalf("ReadAfter() error = %v", err)
	}
	if len(events) != 1 || events[0].Checkpoint == "" {
		t.Fatalf("first outbox page = %#v", events)
	}
	if err := store.SaveCheckpoint(
		context.Background(),
		"test-consumer",
		events[0].Checkpoint,
	); err != nil {
		t.Fatalf("SaveCheckpoint() error = %v", err)
	}

	checkpoint, err := store.LoadCheckpoint(context.Background(), "test-consumer")
	if err != nil {
		t.Fatalf("LoadCheckpoint() error = %v", err)
	}
	events, err = store.ReadAfter(context.Background(), checkpoint, 10)
	if err != nil {
		t.Fatalf("ReadAfter(after checkpoint) error = %v", err)
	}
	if len(events) != 1 || events[0].EventID != "event-2" {
		t.Fatalf("remaining outbox page = %#v", events)
	}
}
