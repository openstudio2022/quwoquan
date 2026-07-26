package messaging_test

import (
	"context"
	"encoding/json"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/messaging"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
)

func TestRedisEventPublisherPreservesStableOutboxEventID(t *testing.T) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	const channel = "events.content.PostPublished"
	subscription, err := client.Subscribe(ctx, channel)
	if err != nil {
		t.Fatal(err)
	}
	defer subscription.Close()

	transport, err := runtimemessaging.NewRedisMessageTransport(client, client)
	if err != nil {
		t.Fatal(err)
	}
	publisher := NewRedisEventPublisherWithTransport(transport, "content-service", nil)
	if err := publisher.Publish(ctx, runtimemessaging.DomainEvent{
		EventID:       "evt-post-42-v2",
		Type:          "PostPublished",
		AggregateType: "Post",
		AggregateID:   "post-42",
		Payload:       map[string]any{"version": float64(2)},
		OccurredAt:    "2026-07-13T08:00:00Z",
	}); err != nil {
		t.Fatalf("Publish() error = %v", err)
	}

	select {
	case message := <-subscription.Channel():
		var envelope struct {
			Meta struct {
				MessageID string `json:"messageId"`
			} `json:"meta"`
			Payload struct {
				EventID string `json:"eventId"`
			} `json:"payload"`
		}
		if err := json.Unmarshal([]byte(message.Payload), &envelope); err != nil {
			t.Fatalf("decode envelope: %v", err)
		}
		if envelope.Meta.MessageID != "evt-post-42-v2" || envelope.Payload.EventID != "evt-post-42-v2" {
			t.Fatalf("stable identity lost: meta=%q payload=%q", envelope.Meta.MessageID, envelope.Payload.EventID)
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for published event")
	}
}
