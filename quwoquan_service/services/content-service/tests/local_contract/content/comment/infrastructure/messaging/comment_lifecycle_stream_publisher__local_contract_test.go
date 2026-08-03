package messaging_test

import (
	"context"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
	. "quwoquan_service/services/content-service/internal/content/comment/infrastructure/messaging"
)

func TestCommentLifecycleStreamPublisherPreservesPostScopedTombstoneIdentity(t *testing.T) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	publisher := NewCommentLifecycleStreamPublisher(client)
	occurredAt := time.Date(2026, 7, 29, 8, 30, 0, 0, time.UTC)

	if err := publisher.Publish(ctx, commentports.OutboxEvent{
		EventID:          "comments-tombstoned:post-42:7:PostDeleted",
		EventType:        "CommentsTombstoned",
		AggregateID:      "post-42",
		AggregateVersion: 7,
		Payload:          []byte(`{"postId":"post-42","tombstonedCount":3,"occurredAt":"2026-07-29T08:30:00Z"}`),
		OccurredAt:       occurredAt,
	}); err != nil {
		t.Fatalf("Publish() error = %v", err)
	}
	if err := client.XGroupCreateMkStream(ctx, CommentLifecycleStream, "test-group", "0"); err != nil {
		t.Fatal(err)
	}
	messages, err := client.XReadGroup(
		ctx,
		"test-group",
		"test-consumer",
		map[string]string{CommentLifecycleStream: ">"},
		1,
		0,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(messages) != 1 {
		t.Fatalf("messages=%d want=1", len(messages))
	}
	values := messages[0].Values
	if values["aggregateType"] != "Post" || values["aggregateId"] != "post-42" ||
		values["aggregateVersion"] != "7" || values["occurredAt"] != occurredAt.Format(time.RFC3339Nano) {
		t.Fatalf("tombstone stream identity drift: %#v", values)
	}
}

func TestCommentLifecycleStreamPublisherRejectsUnversionedTombstone(t *testing.T) {
	err := NewCommentLifecycleStreamPublisher(rtredis.NewMemoryClient()).Publish(
		context.Background(),
		commentports.OutboxEvent{
			EventID: "evt", EventType: "CommentsTombstoned", AggregateID: "post-42",
			AggregateVersion: 0, Payload: []byte(`{"postId":"post-42"}`), OccurredAt: time.Now().UTC(),
		},
	)
	if err == nil {
		t.Fatal("unversioned tombstone must fail before XADD")
	}
}
