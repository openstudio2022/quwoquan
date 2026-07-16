package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	placementports "quwoquan_service/services/circle-service/internal/domain/circle/circle_post_placement/ports"
)

const (
	CirclePostPlacementStream          = "events.circle.post_placements"
	CirclePostPlacementStreamRetention = 7 * 24 * time.Hour
)

type CirclePostPlacementStreamPublisher struct {
	redis rtredis.Client
}

func NewCirclePostPlacementStreamPublisher(redis rtredis.Client) *CirclePostPlacementStreamPublisher {
	return &CirclePostPlacementStreamPublisher{redis: redis}
}

func (publisher *CirclePostPlacementStreamPublisher) Publish(ctx context.Context, event placementports.OutboxEvent) error {
	if publisher == nil || publisher.redis == nil {
		return fmt.Errorf("CirclePostPlacement stream publisher is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 || event.OccurredAt.IsZero() {
		return fmt.Errorf("CirclePostPlacement event identity is incomplete")
	}
	if !json.Valid(event.Payload) {
		return fmt.Errorf("CirclePostPlacement event payload is not valid JSON")
	}
	if _, err := publisher.redis.XAdd(ctx, CirclePostPlacementStream, map[string]string{
		"eventId": event.EventID, "eventType": event.EventType,
		"aggregateType": "CirclePostPlacement", "aggregateId": event.AggregateID,
		"aggregateVersion": strconv.FormatInt(event.AggregateVersion, 10),
		"payload":          string(event.Payload), "occurredAt": event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}); err != nil {
		return fmt.Errorf("append CirclePostPlacement stream: %w", err)
	}
	if err := publisher.redis.Expire(ctx, CirclePostPlacementStream, CirclePostPlacementStreamRetention); err != nil {
		return fmt.Errorf("refresh CirclePostPlacement stream retention: %w", err)
	}
	return nil
}

var _ placementports.OutboxPublisher = (*CirclePostPlacementStreamPublisher)(nil)
