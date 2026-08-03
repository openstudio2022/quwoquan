package eventing

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	domaineventing "quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/eventing"
)

const travelEventRetention = 30 * 24 * time.Hour

type durablePublisher interface {
	AppendDurable(context.Context, runtimemessaging.DurableMessage) (string, error)
	SetDurableRetention(context.Context, string, time.Duration) error
}

type StreamPublisher struct {
	transport durablePublisher
}

func NewStreamPublisher(transport durablePublisher) (*StreamPublisher, error) {
	if transport == nil {
		return nil, domaineventing.ErrInvalidTransport
	}
	return &StreamPublisher{transport: transport}, nil
}

func (publisher *StreamPublisher) Publish(ctx context.Context, event domaineventing.Event) error {
	route, found := domaineventing.RouteForEvent(event.EventType)
	if publisher == nil || publisher.transport == nil || !found ||
		strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.AggregateID) == "" ||
		event.AggregateVersion <= 0 || event.OccurredAt.IsZero() {
		return domaineventing.ErrInvalidEvent
	}
	payload, err := json.Marshal(event.Payload)
	if err != nil {
		return fmt.Errorf("marshal Travel event payload: %w", err)
	}
	values := map[string]string{
		"eventId": event.EventID, "eventType": strings.TrimSpace(event.EventType),
		"aggregateType": route.AggregateType, "aggregateId": event.AggregateID,
		"aggregateVersion": strconv.FormatInt(event.AggregateVersion, 10),
		"payloadJson":      string(payload),
		"occurredAt":       event.OccurredAt.UTC().Format(time.RFC3339Nano),
		"producer":         "travel-service",
	}
	if _, err := publisher.transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: route.Stream, Fields: sortedFields(values),
	}); err != nil {
		return fmt.Errorf("append Travel event %s: %w", event.EventID, err)
	}
	if err := publisher.transport.SetDurableRetention(ctx, route.Stream, travelEventRetention); err != nil {
		return fmt.Errorf("retain Travel stream %s: %w", route.Stream, err)
	}
	return nil
}

func sortedFields(values map[string]string) []runtimemessaging.DurableField {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	fields := make([]runtimemessaging.DurableField, 0, len(keys))
	for _, key := range keys {
		fields = append(fields, runtimemessaging.DurableField{Name: key, Value: values[key]})
	}
	return fields
}

var _ domaineventing.Publisher = (*StreamPublisher)(nil)
