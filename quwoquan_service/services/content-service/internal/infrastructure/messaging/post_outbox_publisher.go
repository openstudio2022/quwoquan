package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
)

// PostOutboxPublisher is the infrastructure translation from the durable,
// typed Post outbox record to the shared messaging transport envelope.
type PostOutboxPublisher struct {
	publisher runtimemessaging.EventPublisher
}

func NewPostOutboxPublisher(
	publisher runtimemessaging.EventPublisher,
) *PostOutboxPublisher {
	return &PostOutboxPublisher{publisher: publisher}
}

func (p *PostOutboxPublisher) Publish(
	ctx context.Context,
	event postports.OutboxEvent,
) error {
	if p == nil || p.publisher == nil {
		return fmt.Errorf("post outbox publisher is not configured")
	}
	if event.EventID == "" {
		return fmt.Errorf("post outbox event has no stable event id")
	}
	var payload map[string]any
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode post outbox payload: %w", err)
	}
	if payload == nil {
		payload = map[string]any{}
	}
	return p.publisher.Publish(ctx, runtimemessaging.DomainEvent{
		EventID:       event.EventID,
		Type:          event.EventType,
		AggregateType: event.AggregateType,
		AggregateID:   event.AggregateID,
		Payload:       payload,
		OccurredAt:    event.OccurredAt.UTC().Format(time.RFC3339Nano),
	})
}

var _ postports.OutboxPublisher = (*PostOutboxPublisher)(nil)
