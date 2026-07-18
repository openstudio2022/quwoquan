package messaging

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
)

func TestPostLifecycleStreamPublisherPreservesDurableIdentity(t *testing.T) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	publisher := NewPostLifecycleStreamPublisher(client)
	occurredAt := time.Date(2026, 7, 14, 8, 30, 0, 0, time.UTC)
	payload, _ := json.Marshal(map[string]any{"postId": "post-42", "authorId": "persona-7", "status": "published"})
	if err := publisher.Publish(ctx, postports.OutboxEvent{
		EventID: "post-42:2:PostPublished", EventType: "PostPublished",
		AggregateType: "Post", AggregateID: "post-42", AggregateVersion: 2,
		Payload: payload, OccurredAt: occurredAt,
	}); err != nil {
		t.Fatalf("Publish() error = %v", err)
	}
	if err := client.XGroupCreateMkStream(ctx, PostLifecycleStream, "circle-service", "0"); err != nil {
		t.Fatal(err)
	}
	messages, err := client.XReadGroup(ctx, "circle-service", "test", map[string]string{PostLifecycleStream: ">"}, 1, 0)
	if err != nil {
		t.Fatal(err)
	}
	if len(messages) != 1 {
		t.Fatalf("messages=%d want=1", len(messages))
	}
	values := messages[0].Values
	if values["eventId"] != "post-42:2:PostPublished" || values["aggregateVersion"] != "2" ||
		values["occurredAt"] != occurredAt.Format(time.RFC3339Nano) {
		t.Fatalf("stream identity drift: %#v", values)
	}
}

func TestPostLifecycleStreamPublisherRejectsInvalidPayload(t *testing.T) {
	publisher := NewPostLifecycleStreamPublisher(rtredis.NewMemoryClient())
	err := publisher.Publish(context.Background(), postports.OutboxEvent{
		EventID: "evt", EventType: "PostPublished", AggregateType: "Post",
		AggregateID: "post", AggregateVersion: 1, Payload: []byte("not-json"), OccurredAt: time.Now().UTC(),
	})
	if err == nil {
		t.Fatal("invalid payload must fail before XADD")
	}
}
