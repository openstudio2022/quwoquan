package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	groupports "quwoquan_service/services/circle-service/internal/domain/circle/circle_group/ports"
)

const (
	CircleGroupStream          = "events.circle.groups"
	CircleGroupStreamRetention = 7 * 24 * time.Hour
)

type CircleGroupStreamPublisher struct {
	redis rtredis.Client
}

func NewCircleGroupStreamPublisher(redis rtredis.Client) *CircleGroupStreamPublisher {
	return &CircleGroupStreamPublisher{redis: redis}
}

func (publisher *CircleGroupStreamPublisher) Publish(ctx context.Context, event groupports.OutboxEvent) error {
	if publisher == nil || publisher.redis == nil {
		return fmt.Errorf("CircleGroup stream publisher is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 || event.OccurredAt.IsZero() {
		return fmt.Errorf("CircleGroup event identity is incomplete")
	}
	if !json.Valid(event.Payload) {
		return fmt.Errorf("CircleGroup event payload is not valid JSON")
	}
	if _, err := publisher.redis.XAdd(ctx, CircleGroupStream, map[string]string{
		"eventId": event.EventID, "eventType": event.EventType,
		"aggregateType": "CircleGroup", "aggregateId": event.AggregateID,
		"aggregateVersion": strconv.FormatInt(event.AggregateVersion, 10),
		"payload":          string(event.Payload), "occurredAt": event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}); err != nil {
		return fmt.Errorf("append CircleGroup stream: %w", err)
	}
	if err := publisher.redis.Expire(ctx, CircleGroupStream, CircleGroupStreamRetention); err != nil {
		return fmt.Errorf("refresh CircleGroup stream retention: %w", err)
	}
	return nil
}

var _ groupports.OutboxPublisher = (*CircleGroupStreamPublisher)(nil)
