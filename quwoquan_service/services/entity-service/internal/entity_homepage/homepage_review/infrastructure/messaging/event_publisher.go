package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	reviewport "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/domain/ports"
)

const (
	HomepageReviewEventStream          = "events.entity.homepage_reviews"
	HomepageReviewEventStreamRetention = 7 * 24 * time.Hour
)

type EventPublisher struct {
	transport runtimemessaging.DurableRecordAppender
}

func NewEventPublisher(
	transport runtimemessaging.DurableRecordAppender,
) (*EventPublisher, error) {
	if transport == nil {
		return nil, fmt.Errorf("HomepageReview durable transport is required")
	}
	return &EventPublisher{transport: transport}, nil
}

func (publisher *EventPublisher) Publish(
	ctx context.Context,
	event reviewport.OutboxEvent,
) error {
	if publisher == nil || publisher.transport == nil {
		return fmt.Errorf("HomepageReview event publisher is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.AggregateID) == "" ||
		event.AggregateVersion <= 0 || event.OccurredAt.IsZero() ||
		!json.Valid(event.Payload) {
		return fmt.Errorf("HomepageReview event identity or payload is invalid")
	}
	payload, err := canonicalHomepageReviewPayload(event.EventType, event.Payload)
	if err != nil {
		return err
	}
	if err := runtimemessaging.AppendDurableRecord(
		ctx,
		publisher.transport,
		HomepageReviewEventStream,
		map[string]string{
			"eventId":          event.EventID,
			"eventType":        event.EventType,
			"aggregateType":    "HomepageReview",
			"aggregateId":      event.AggregateID,
			"aggregateVersion": strconv.FormatInt(event.AggregateVersion, 10),
			"payload":          string(payload),
			"occurredAt":       event.OccurredAt.UTC().Format(time.RFC3339Nano),
		},
		HomepageReviewEventStreamRetention,
	); err != nil {
		return fmt.Errorf("append HomepageReview event stream: %w", err)
	}
	return nil
}

func canonicalHomepageReviewPayload(eventType string, payload []byte) ([]byte, error) {
	fieldsByEvent := map[string][]string{
		"HomepageReviewPublished": {
			"reviewId", "homepageId", "authorPersonaId", "rating", "tagRefs", "status", "createdAt", "version",
		},
		"HomepageReviewUpdated": {
			"reviewId", "homepageId", "authorPersonaId", "rating", "tagRefs", "status", "updatedAt", "version",
		},
		"HomepageReviewRemoved": {"reviewId", "homepageId", "status", "updatedAt", "version"},
	}
	fields, supported := fieldsByEvent[eventType]
	if !supported {
		return nil, fmt.Errorf("HomepageReview event type %q is not canonical", eventType)
	}
	var source map[string]json.RawMessage
	if err := json.Unmarshal(payload, &source); err != nil {
		return nil, fmt.Errorf("decode HomepageReview event payload: %w", err)
	}
	canonical := make(map[string]json.RawMessage, len(fields))
	for _, field := range fields {
		value, found := source[field]
		if !found || len(value) == 0 || string(value) == "null" {
			return nil, fmt.Errorf("HomepageReview %s payload is missing %s", eventType, field)
		}
		canonical[field] = value
	}
	encoded, err := json.Marshal(canonical)
	if err != nil {
		return nil, fmt.Errorf("encode HomepageReview canonical payload: %w", err)
	}
	return encoded, nil
}

var _ reviewport.OutboxPublisher = (*EventPublisher)(nil)
