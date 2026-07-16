package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	fileports "quwoquan_service/services/circle-service/internal/domain/circle/circle_file/ports"
)

const (
	CircleFileStream          = "events.circle.files"
	CircleFileStreamRetention = 7 * 24 * time.Hour
)

type CircleFileStreamPublisher struct {
	redis rtredis.Client
}

func NewCircleFileStreamPublisher(redis rtredis.Client) *CircleFileStreamPublisher {
	return &CircleFileStreamPublisher{redis: redis}
}

func (publisher *CircleFileStreamPublisher) Publish(ctx context.Context, event fileports.OutboxEvent) error {
	if publisher == nil || publisher.redis == nil {
		return fmt.Errorf("CircleFile stream publisher is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 || event.OccurredAt.IsZero() {
		return fmt.Errorf("CircleFile event identity is incomplete")
	}
	if !json.Valid(event.Payload) {
		return fmt.Errorf("CircleFile event payload is not valid JSON")
	}
	if _, err := publisher.redis.XAdd(ctx, CircleFileStream, map[string]string{
		"eventId": event.EventID, "eventType": event.EventType,
		"aggregateType": "CircleFile", "aggregateId": event.AggregateID,
		"aggregateVersion": strconv.FormatInt(event.AggregateVersion, 10),
		"payload":          string(event.Payload), "occurredAt": event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}); err != nil {
		return fmt.Errorf("append CircleFile stream: %w", err)
	}
	if err := publisher.redis.Expire(ctx, CircleFileStream, CircleFileStreamRetention); err != nil {
		return fmt.Errorf("refresh CircleFile stream retention: %w", err)
	}
	return nil
}

var _ fileports.OutboxPublisher = (*CircleFileStreamPublisher)(nil)
