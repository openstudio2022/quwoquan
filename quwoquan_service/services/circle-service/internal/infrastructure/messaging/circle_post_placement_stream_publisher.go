package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	placementports "quwoquan_service/services/circle-service/internal/domain/circle/circle_post_placement/ports"
)

const (
	CirclePostPlacementStream          = "events.circle.post_placements"
	CirclePostPlacementStreamRetention = 7 * 24 * time.Hour
)

type CirclePostPlacementStreamPublisher struct {
	transport durableStreamTransport
}

func NewCirclePostPlacementStreamPublisher(transport durableStreamTransport) *CirclePostPlacementStreamPublisher {
	return &CirclePostPlacementStreamPublisher{transport: transport}
}

func (publisher *CirclePostPlacementStreamPublisher) Publish(ctx context.Context, event placementports.OutboxEvent) error {
	if publisher == nil || publisher.transport == nil {
		return fmt.Errorf("CirclePostPlacement stream publisher is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 || event.OccurredAt.IsZero() {
		return fmt.Errorf("CirclePostPlacement event identity is incomplete")
	}
	if !json.Valid(event.Payload) {
		return fmt.Errorf("CirclePostPlacement event payload is not valid JSON")
	}
	if err := appendCircleDurableRecord(ctx, publisher.transport, CirclePostPlacementStream, map[string]string{
		"eventId": event.EventID, "eventType": event.EventType,
		"aggregateType": "CirclePostPlacement", "aggregateId": event.AggregateID,
		"aggregateVersion": strconv.FormatInt(event.AggregateVersion, 10),
		"payload":          string(event.Payload), "occurredAt": event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}, CirclePostPlacementStreamRetention); err != nil {
		return fmt.Errorf("append CirclePostPlacement stream: %w", err)
	}
	return nil
}

var _ placementports.OutboxPublisher = (*CirclePostPlacementStreamPublisher)(nil)
