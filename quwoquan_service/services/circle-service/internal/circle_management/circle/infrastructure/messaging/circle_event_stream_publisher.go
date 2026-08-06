package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	circleports "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/ports"
)

const (
	CircleEventStream          = "events.circle.circles"
	CircleEventStreamRetention = 7 * 24 * time.Hour
)

// CircleEventStreamPublisher is the canonical durable handoff for Circle
// aggregate facts. The outbox relay advances its checkpoint only after this
// adapter has appended the complete event identity to the managed stream.
type CircleEventStreamPublisher struct {
	transport runtimemessaging.DurableRecordAppender
}

func NewCircleEventStreamPublisher(
	transport runtimemessaging.DurableRecordAppender,
) (*CircleEventStreamPublisher, error) {
	if transport == nil {
		return nil, fmt.Errorf("Circle durable transport is required")
	}
	return &CircleEventStreamPublisher{transport: transport}, nil
}

func (publisher *CircleEventStreamPublisher) Publish(
	ctx context.Context,
	event circleports.OutboxEvent,
) error {
	if publisher == nil || publisher.transport == nil {
		return fmt.Errorf("Circle event stream publisher is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.AggregateID) == "" ||
		event.AggregateVersion <= 0 || event.OccurredAt.IsZero() ||
		!json.Valid(event.Payload) {
		return fmt.Errorf("Circle event identity or payload is invalid")
	}
	payload, err := canonicalCirclePayload(event.EventType, event.Payload)
	if err != nil {
		return err
	}
	if err := runtimemessaging.AppendDurableRecord(
		ctx,
		publisher.transport,
		CircleEventStream,
		map[string]string{
			"eventId":          event.EventID,
			"eventType":        event.EventType,
			"aggregateType":    "Circle",
			"aggregateId":      event.AggregateID,
			"aggregateVersion": strconv.FormatInt(event.AggregateVersion, 10),
			"payload":          string(payload),
			"occurredAt":       event.OccurredAt.UTC().Format(time.RFC3339Nano),
			"checkpoint":       event.Checkpoint,
		},
		CircleEventStreamRetention,
	); err != nil {
		return fmt.Errorf("append Circle event stream: %w", err)
	}
	return nil
}

func canonicalCirclePayload(eventType string, payload []byte) ([]byte, error) {
	fieldsByEvent := map[string][]string{
		"CircleCreated": {
			"id", "name", "ownerId", "category", "tags", "rulesText",
			"welcomeMessage", "iconUrl", "autoSyncChat",
		},
		"CircleUpdated": {
			"id", "name", "description", "rulesText", "welcomeMessage",
			"iconUrl", "autoSyncChat", "tags", "category",
		},
		"CircleArchived":        {"id", "status"},
		"CircleSectionsUpdated": {"circleId", "sectionConfig"},
	}
	fields, supported := fieldsByEvent[eventType]
	if !supported {
		return nil, fmt.Errorf("Circle event type %q is not canonical", eventType)
	}
	var source map[string]json.RawMessage
	if err := json.Unmarshal(payload, &source); err != nil {
		return nil, fmt.Errorf("decode Circle event payload: %w", err)
	}
	canonical := make(map[string]json.RawMessage, len(fields))
	for _, field := range fields {
		value, exists := source[field]
		if !exists || len(value) == 0 || string(value) == "null" {
			return nil, fmt.Errorf("Circle %s payload is missing %s", eventType, field)
		}
		canonical[field] = value
	}
	encoded, err := json.Marshal(canonical)
	if err != nil {
		return nil, fmt.Errorf("encode Circle canonical payload: %w", err)
	}
	return encoded, nil
}

var _ circleports.OutboxPublisher = (*CircleEventStreamPublisher)(nil)
