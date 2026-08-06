package messaging

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/ports"
)

const (
	SkillUserSettingEventStream    = "assistant.skill_user_setting"
	SkillUserSettingEventRetention = 7 * 24 * time.Hour
)

type EventPublisher struct {
	transport runtimemessaging.DurableRecordAppender
}

func NewEventPublisher(transport runtimemessaging.DurableRecordAppender) (*EventPublisher, error) {
	if transport == nil {
		return nil, errors.New("skill user setting durable transport is required")
	}
	return &EventPublisher{transport: transport}, nil
}

func (publisher *EventPublisher) PublishSkillUserSetting(
	ctx context.Context,
	event ports.OutboxEvent,
) error {
	if err := runtimemessaging.AppendDurableRecord(ctx, publisher.transport,
		SkillUserSettingEventStream,
		map[string]string{
			"eventId": event.EventID, "eventName": event.EventType,
			"aggregateType": "SkillUserSetting", "aggregateId": event.AggregateID,
			"aggregateRevision": strconv.FormatInt(event.AggregateVersion, 10),
			"occurredAt":        event.OccurredAt.UTC().Format(time.RFC3339Nano),
			"payload":           string(event.Payload),
		}, SkillUserSettingEventRetention,
	); err != nil {
		return fmt.Errorf("append skill user setting event: %w", err)
	}
	return nil
}
