package messaging

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
)

func TestRedisEventPublisherUsesInjectedMessageTransport(t *testing.T) {
	t.Parallel()

	client := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"product-ops-service-test",
		runtimemessaging.RedisMessageTransportFixture,
		client,
		client,
	)
	if err != nil {
		t.Fatalf("new message transport: %v", err)
	}
	subscription, err := transport.SubscribeEphemeral(
		context.Background(),
		"events.ops.PremiumPoolEntryUpserted",
	)
	if err != nil {
		t.Fatalf("subscribe transport: %v", err)
	}
	t.Cleanup(func() { _ = subscription.Close() })

	publisher := NewRedisEventPublisherWithTransport(transport, "product-ops-service", nil)
	if err := publisher.Publish(context.Background(), runtimemessaging.DomainEvent{
		Type:          "PremiumPoolEntryUpserted",
		AggregateType: "premium_pool_entry",
		AggregateID:   "entry-1",
		Payload:       map[string]any{"taskId": "task-1"},
		OccurredAt:    time.Date(2026, time.July, 21, 12, 0, 0, 0, time.UTC).Format(time.RFC3339),
	}); err != nil {
		t.Fatalf("publish event: %v", err)
	}

	select {
	case delivery := <-subscription.Channel():
		if delivery.Channel != "events.ops.PremiumPoolEntryUpserted" {
			t.Fatalf("event channel = %q", delivery.Channel)
		}
		var envelope struct {
			Payload struct {
				Type string `json:"type"`
			} `json:"payload"`
		}
		if err := json.Unmarshal(delivery.Payload, &envelope); err != nil {
			t.Fatalf("decode envelope: %v", err)
		}
		if envelope.Payload.Type != "PremiumPoolEntryUpserted" {
			t.Fatalf("event type = %q", envelope.Payload.Type)
		}
	case <-time.After(time.Second):
		t.Fatal("transport did not deliver the published event")
	}
}
