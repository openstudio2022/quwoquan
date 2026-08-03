package messaging

import (
	"context"
	"encoding/json"
	"fmt"

	runtimemessaging "quwoquan_service/runtime/messaging"
	shareports "quwoquan_service/services/content-service/internal/content/outbound_share_fact/domain/ports"
)

type OutboundShareOutboxPublisher struct {
	publisher runtimemessaging.EventPublisher
}

func NewOutboundShareOutboxPublisher(
	publisher runtimemessaging.EventPublisher,
) *OutboundShareOutboxPublisher {
	return &OutboundShareOutboxPublisher{publisher: publisher}
}

func (p *OutboundShareOutboxPublisher) Publish(
	ctx context.Context,
	event shareports.OutboxEvent,
) error {
	if p == nil || p.publisher == nil {
		return fmt.Errorf("OutboundShareFact runtime publisher is not configured")
	}
	var payload map[string]any
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode OutboundShareFact payload: %w", err)
	}
	return p.publisher.Publish(ctx, runtimemessaging.DomainEvent{
		EventID:       event.EventID,
		Type:          event.EventType,
		AggregateType: "OutboundShareFact",
		AggregateID:   event.EventID,
		Payload:       payload,
		OccurredAt:    event.OccurredAt.UTC().Format("2006-01-02T15:04:05.999999999Z07:00"),
	})
}

var _ shareports.OutboxPublisher = (*OutboundShareOutboxPublisher)(nil)
