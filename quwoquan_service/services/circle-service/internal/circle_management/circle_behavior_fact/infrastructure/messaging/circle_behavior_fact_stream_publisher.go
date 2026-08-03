package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	behaviorfactports "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/domain/ports"
)

const (
	CircleBehaviorFactStream          = "events.circle.behavior_facts"
	CircleBehaviorFactStreamRetention = 7 * 24 * time.Hour
)

type CircleBehaviorFactStreamPublisher struct {
	transport runtimemessaging.DurableRecordAppender
}

func NewCircleBehaviorFactStreamPublisher(transport runtimemessaging.DurableRecordAppender) *CircleBehaviorFactStreamPublisher {
	return &CircleBehaviorFactStreamPublisher{transport: transport}
}

func (publisher *CircleBehaviorFactStreamPublisher) Publish(ctx context.Context, event behaviorfactports.OutboxEvent) error {
	if publisher == nil || publisher.transport == nil || strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.AggregateID) == "" || event.OccurredAt.IsZero() || !json.Valid(event.Payload) {
		return fmt.Errorf("CircleBehaviorFact stream event is invalid")
	}
	if err := runtimemessaging.AppendDurableRecord(ctx, publisher.transport, CircleBehaviorFactStream, map[string]string{
		"eventId": event.EventID, "eventType": event.EventType,
		"aggregateType": "CircleBehaviorFact", "aggregateId": event.AggregateID,
		"payload": string(event.Payload), "occurredAt": event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}, CircleBehaviorFactStreamRetention); err != nil {
		return fmt.Errorf("append CircleBehaviorFact stream: %w", err)
	}
	return nil
}

var _ behaviorfactports.OutboxPublisher = (*CircleBehaviorFactStreamPublisher)(nil)
