package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	ports "quwoquan_service/services/circle-service/internal/domain/circle/circle_group_membership/ports"
)

const (
	CircleGroupMembershipStream          = "events.circle.group-memberships"
	CircleGroupMembershipStreamRetention = 7 * 24 * time.Hour
)

type CircleGroupMembershipStreamPublisher struct{ redis rtredis.Client }

func NewCircleGroupMembershipStreamPublisher(redis rtredis.Client) *CircleGroupMembershipStreamPublisher {
	return &CircleGroupMembershipStreamPublisher{redis: redis}
}

func (publisher *CircleGroupMembershipStreamPublisher) Publish(ctx context.Context, event ports.OutboxEvent) error {
	if publisher == nil || publisher.redis == nil {
		return fmt.Errorf("CircleGroupMembership stream publisher is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 || event.OccurredAt.IsZero() {
		return fmt.Errorf("CircleGroupMembership event identity is incomplete")
	}
	if !json.Valid(event.Payload) {
		return fmt.Errorf("CircleGroupMembership event payload is not valid JSON")
	}
	if _, err := publisher.redis.XAdd(ctx, CircleGroupMembershipStream, map[string]string{
		"eventId": event.EventID, "eventType": event.EventType, "aggregateType": "CircleGroupMembership",
		"aggregateId": event.AggregateID, "aggregateVersion": strconv.FormatInt(event.AggregateVersion, 10),
		"payload": string(event.Payload), "occurredAt": event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}); err != nil {
		return fmt.Errorf("append CircleGroupMembership stream: %w", err)
	}
	if err := publisher.redis.Expire(ctx, CircleGroupMembershipStream, CircleGroupMembershipStreamRetention); err != nil {
		return fmt.Errorf("refresh CircleGroupMembership stream retention: %w", err)
	}
	return nil
}

var _ ports.OutboxPublisher = (*CircleGroupMembershipStreamPublisher)(nil)
