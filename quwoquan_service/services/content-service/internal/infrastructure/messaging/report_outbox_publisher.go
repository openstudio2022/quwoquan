package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	reportports "quwoquan_service/services/content-service/internal/domain/report/ports"
)

// ReportOutboxPublisher translates durable Report facts into the shared
// runtime envelope. It preserves the immutable outbox EventID so downstream
// consumers can de-duplicate at least-once relay delivery.
type ReportOutboxPublisher struct {
	publisher runtimemessaging.EventPublisher
}

func NewReportOutboxPublisher(
	publisher runtimemessaging.EventPublisher,
) *ReportOutboxPublisher {
	return &ReportOutboxPublisher{publisher: publisher}
}

func (p *ReportOutboxPublisher) Publish(
	ctx context.Context,
	event reportports.OutboxEvent,
) error {
	if p == nil || p.publisher == nil {
		return fmt.Errorf("report outbox publisher is not configured")
	}
	if event.EventID == "" {
		return fmt.Errorf("report outbox event has no stable event id")
	}
	var payload map[string]any
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode report outbox payload: %w", err)
	}
	if payload == nil {
		payload = map[string]any{}
	}
	return p.publisher.Publish(ctx, runtimemessaging.DomainEvent{
		EventID:       event.EventID,
		Type:          event.EventType,
		AggregateType: "Report",
		AggregateID:   event.AggregateID,
		Payload:       payload,
		OccurredAt:    event.OccurredAt.UTC().Format(time.RFC3339Nano),
	})
}

var _ reportports.OutboxPublisher = (*ReportOutboxPublisher)(nil)
