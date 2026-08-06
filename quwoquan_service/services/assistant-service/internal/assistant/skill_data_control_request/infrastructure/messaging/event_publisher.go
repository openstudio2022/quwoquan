package messaging

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/ports"
)

const (
	SkillDataControlEventStream    = "assistant.skill_data_control_request"
	SkillDataControlEventRetention = 7 * 24 * time.Hour
)

type EventPublisher struct {
	transport runtimemessaging.DurableRecordAppender
}

func NewEventPublisher(transport runtimemessaging.DurableRecordAppender) (*EventPublisher, error) {
	if transport == nil {
		return nil, errors.New("skill data control durable transport is required")
	}
	return &EventPublisher{transport: transport}, nil
}

func (publisher *EventPublisher) PublishSkillDataControl(
	ctx context.Context,
	event ports.OutboxEvent,
) error {
	if err := runtimemessaging.AppendDurableRecord(ctx, publisher.transport,
		SkillDataControlEventStream,
		map[string]string{
			"eventId": event.EventID, "eventName": event.EventType,
			"aggregateType": "SkillDataControlRequest", "aggregateId": event.AggregateID,
			"aggregateRevision": strconv.FormatInt(event.AggregateVersion, 10),
			"occurredAt":        event.OccurredAt.UTC().Format(time.RFC3339Nano),
			"payload":           string(event.Payload),
		}, SkillDataControlEventRetention,
	); err != nil {
		return fmt.Errorf("append skill data control event: %w", err)
	}
	return nil
}
