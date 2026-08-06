package messaging

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/ports"
)

const (
	SkillSubscriptionEventStream    = "assistant.skill_subscription"
	SkillSubscriptionEventRetention = 7 * 24 * time.Hour
)

type EventPublisher struct {
	transport runtimemessaging.DurableRecordAppender
}

func NewEventPublisher(transport runtimemessaging.DurableRecordAppender) (*EventPublisher, error) {
	if transport == nil {
		return nil, errors.New("skill subscription durable transport is required")
	}
	return &EventPublisher{transport: transport}, nil
}

func (publisher *EventPublisher) PublishSkillSubscription(
	ctx context.Context,
	event ports.OutboxEvent,
) error {
	if err := runtimemessaging.AppendDurableRecord(ctx, publisher.transport,
		SkillSubscriptionEventStream,
		map[string]string{
			"eventId": event.EventID, "eventName": event.EventType,
			"aggregateType": "SkillSubscription", "aggregateId": event.AggregateID,
			"aggregateRevision": strconv.FormatInt(event.AggregateVersion, 10),
			"occurredAt":        event.OccurredAt.UTC().Format(time.RFC3339Nano),
			"payload":           string(event.Payload),
		}, SkillSubscriptionEventRetention,
	); err != nil {
		return fmt.Errorf("append skill subscription event: %w", err)
	}
	return nil
}
