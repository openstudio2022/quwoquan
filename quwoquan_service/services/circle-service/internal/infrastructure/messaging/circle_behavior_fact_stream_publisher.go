package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	behaviorfactports "quwoquan_service/services/circle-service/internal/domain/circle/circle_behavior_fact/ports"
)

const (
	CircleBehaviorFactStream          = "events.circle.behavior_facts"
	CircleBehaviorFactStreamRetention = 7 * 24 * time.Hour
)

type CircleBehaviorFactStreamPublisher struct{ redis rtredis.Client }

func NewCircleBehaviorFactStreamPublisher(redis rtredis.Client) *CircleBehaviorFactStreamPublisher {
	return &CircleBehaviorFactStreamPublisher{redis: redis}
}

func (publisher *CircleBehaviorFactStreamPublisher) Publish(ctx context.Context, event behaviorfactports.OutboxEvent) error {
	if publisher == nil || publisher.redis == nil || strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.AggregateID) == "" || event.OccurredAt.IsZero() || !json.Valid(event.Payload) {
		return fmt.Errorf("CircleBehaviorFact stream event is invalid")
	}
	if _, err := publisher.redis.XAdd(ctx, CircleBehaviorFactStream, map[string]string{
		"eventId": event.EventID, "eventType": event.EventType,
		"aggregateType": "CircleBehaviorFact", "aggregateId": event.AggregateID,
		"payload": string(event.Payload), "occurredAt": event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}); err != nil {
		return fmt.Errorf("append CircleBehaviorFact stream: %w", err)
	}
	if err := publisher.redis.Expire(ctx, CircleBehaviorFactStream, CircleBehaviorFactStreamRetention); err != nil {
		return fmt.Errorf("refresh CircleBehaviorFact stream retention: %w", err)
	}
	return nil
}

var _ behaviorfactports.OutboxPublisher = (*CircleBehaviorFactStreamPublisher)(nil)
