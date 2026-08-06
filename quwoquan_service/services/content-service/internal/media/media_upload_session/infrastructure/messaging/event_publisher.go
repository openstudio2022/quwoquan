package messaging

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/content-service/internal/media/media_upload_session/domain/ports"
)

const (
	MediaUploadSessionEventStream    = "events.content.media_upload_sessions"
	MediaUploadSessionEventRetention = 7 * 24 * time.Hour
)

type EventPublisher struct {
	transport runtimemessaging.DurableRecordAppender
}

func NewEventPublisher(transport runtimemessaging.DurableRecordAppender) (*EventPublisher, error) {
	if transport == nil {
		return nil, errors.New("media upload session durable transport is required")
	}
	return &EventPublisher{transport: transport}, nil
}

func (publisher *EventPublisher) PublishMediaUploadSession(
	ctx context.Context,
	event ports.OutboxEvent,
) error {
	if err := runtimemessaging.AppendDurableRecord(ctx, publisher.transport,
		MediaUploadSessionEventStream,
		map[string]string{
			"eventId": event.EventID, "eventName": event.EventType,
			"aggregateType": event.AggregateType, "aggregateId": event.AggregateID,
			"aggregateVersion": strconv.FormatInt(event.AggregateVersion, 10),
			"occurredAt":       event.OccurredAt.UTC().Format(time.RFC3339Nano),
			"payload":          string(event.Payload),
		}, MediaUploadSessionEventRetention,
	); err != nil {
		return fmt.Errorf("append media upload session event: %w", err)
	}
	return nil
}
