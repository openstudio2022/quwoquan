package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	moderationports "quwoquan_service/services/content-service/internal/domain/moderation/ports"
)

// ModerationOutboxPublisher translates durable PostModerationCase facts into
// the shared runtime envelope, preserving the immutable outbox EventID so
// downstream consumers can de-duplicate at-least-once relay delivery.
type ModerationOutboxPublisher struct {
	publisher runtimemessaging.EventPublisher
}

func NewModerationOutboxPublisher(
	publisher runtimemessaging.EventPublisher,
) *ModerationOutboxPublisher {
	return &ModerationOutboxPublisher{publisher: publisher}
}

func (p *ModerationOutboxPublisher) Publish(
	ctx context.Context,
	event moderationports.OutboxEvent,
) error {
	if p == nil || p.publisher == nil {
		return fmt.Errorf("moderation outbox publisher is not configured")
	}
	if event.EventID == "" {
		return fmt.Errorf("moderation outbox event has no stable event id")
	}
	var payload map[string]any
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode moderation outbox payload: %w", err)
	}
	if payload == nil {
		payload = map[string]any{}
	}
	return p.publisher.Publish(ctx, runtimemessaging.DomainEvent{
		EventID:       event.EventID,
		Type:          event.EventType,
		AggregateType: "PostModerationCase",
		AggregateID:   event.AggregateID,
		Payload:       payload,
		OccurredAt:    event.OccurredAt.UTC().Format(time.RFC3339Nano),
	})
}

var _ moderationports.OutboxPublisher = (*ModerationOutboxPublisher)(nil)
