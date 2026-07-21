package messaging

import (
	"context"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
)

func TestRedisEventPublisherUsesInjectedMessageTransport(t *testing.T) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"assistant-service-test",
		runtimemessaging.RedisMessageTransportFixture,
		client,
		client,
	)
	if err != nil {
		t.Fatalf("NewRedisMessageTransportForRoot() error = %v", err)
	}
	const channel = "events.assistant.PreferenceCaptured"
	subscription, err := client.Subscribe(ctx, channel)
	if err != nil {
		t.Fatalf("Subscribe() error = %v", err)
	}
	t.Cleanup(func() { _ = subscription.Close() })

	publisher := NewRedisEventPublisherWithTransport(
		transport,
		"assistant-service",
		nil,
	)
	if err := publisher.Publish(ctx, runtimemessaging.DomainEvent{
		Type:          "PreferenceCaptured",
		AggregateType: "assistant.preference",
		AggregateID:   "preference-1",
		Payload:       map[string]any{"interest": "摄影"},
		OccurredAt:    "2026-07-21T08:00:00Z",
	}); err != nil {
		t.Fatalf("Publish() error = %v", err)
	}
	select {
	case message := <-subscription.Channel():
		if message.Channel != channel || message.Payload == "" {
			t.Fatalf("published message = %#v", message)
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for injected transport publication")
	}
}
