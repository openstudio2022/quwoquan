package local_contract

import (
	"context"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	eventmessaging "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/messaging"
)

type captureEventTransport struct {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
	ephemeral []runtimemessaging.EphemeralMessage
	durable   []runtimemessaging.DurableMessage
	retained  map[string]time.Duration
}

func (transport *captureEventTransport) PublishEphemeral(
	_ context.Context,
	message runtimemessaging.EphemeralMessage,
) error {
	transport.ephemeral = append(transport.ephemeral, message)
	return nil
}

func (transport *captureEventTransport) AppendDurable(
	_ context.Context,
	message runtimemessaging.DurableMessage,
) (string, error) {
	transport.durable = append(transport.durable, message)
	return "1000-0", nil
}

func (transport *captureEventTransport) SetDurableRetention(
	_ context.Context,
	stream string,
	ttl time.Duration,
) error {
	if transport.retained == nil {
		transport.retained = make(map[string]time.Duration)
	}
	transport.retained[stream] = ttl
	return nil
}

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/product-control-plane-contract/spec.md#gwt-002
func TestPremiumPoolEventUsesOneDurableTypedStream(t *testing.T) {
	transport := &captureEventTransport{}
	publisher := eventmessaging.NewRedisEventPublisherWithTransport(
		transport,
		"product-ops-service",
		nil,
	)
	err := publisher.Publish(context.Background(), runtimemessaging.DomainEvent{
		EventID:       "premium-event-001",
		Type:          "PremiumPoolEntryUpserted",
		AggregateType: "PremiumPoolEntry",
		AggregateID:   "post-001",
		OccurredAt:    "2026-07-31T11:00:00Z",
		Payload: map[string]any{
			"contentId": "post-001",
			"status":    "active",
		},
	})
	if err != nil {
		t.Fatalf("Publish: %v", err)
	}
	if len(transport.ephemeral) != 0 {
		t.Fatalf("premium event must not use ephemeral Pub/Sub: %+v", transport.ephemeral)
	}
	if len(transport.durable) != 1 || transport.durable[0].Stream != "events.ops.premium_pool_entry" {
		t.Fatalf("premium event durable stream mismatch: %+v", transport.durable)
	}
	fields := make(map[string]string, len(transport.durable[0].Fields))
	for _, field := range transport.durable[0].Fields {
		fields[field.Name] = field.Value
	}
	if fields["eventId"] != "premium-event-001" || fields["producer"] != "product-ops-service" {
		t.Fatalf("premium event identity mismatch: %+v", fields)
	}
	if transport.retained["events.ops.premium_pool_entry"] != 7*24*time.Hour {
		t.Fatalf("premium stream retention mismatch: %+v", transport.retained)
	}
}
