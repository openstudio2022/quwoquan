package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	membershipports "quwoquan_service/services/circle-service/internal/domain/circle/circle_membership/ports"
)

const (
	CircleMembershipStream          = "events.circle.memberships"
	CircleMembershipStreamRetention = 7 * 24 * time.Hour
)

type CircleMembershipStreamPublisher struct {
	redis rtredis.Client
}

func NewCircleMembershipStreamPublisher(redis rtredis.Client) *CircleMembershipStreamPublisher {
	return &CircleMembershipStreamPublisher{redis: redis}
}

func (publisher *CircleMembershipStreamPublisher) Publish(ctx context.Context, event membershipports.OutboxEvent) error {
	if publisher == nil || publisher.redis == nil {
		return fmt.Errorf("CircleMembership stream publisher is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 || event.OccurredAt.IsZero() {
		return fmt.Errorf("CircleMembership event identity is incomplete")
	}
	if !json.Valid(event.Payload) {
		return fmt.Errorf("CircleMembership event payload is not valid JSON")
	}
	if _, err := publisher.redis.XAdd(ctx, CircleMembershipStream, map[string]string{
		"eventId": event.EventID, "eventType": event.EventType,
		"aggregateType": "CircleMembership", "aggregateId": event.AggregateID,
		"aggregateVersion": strconv.FormatInt(event.AggregateVersion, 10),
		"payload":          string(event.Payload), "occurredAt": event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}); err != nil {
		return fmt.Errorf("append CircleMembership stream: %w", err)
	}
	if err := publisher.redis.Expire(ctx, CircleMembershipStream, CircleMembershipStreamRetention); err != nil {
		return fmt.Errorf("refresh CircleMembership stream retention: %w", err)
	}
	return nil
}

var _ membershipports.OutboxPublisher = (*CircleMembershipStreamPublisher)(nil)
