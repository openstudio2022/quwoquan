package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	membershipports "quwoquan_service/services/circle-service/internal/domain/circle/circle_membership/ports"
)

const (
	CircleMembershipStream          = "events.circle.memberships"
	CircleMembershipStreamRetention = 7 * 24 * time.Hour
)

type CircleMembershipStreamPublisher struct {
	transport durableStreamTransport
}

func NewCircleMembershipStreamPublisher(transport durableStreamTransport) *CircleMembershipStreamPublisher {
	return &CircleMembershipStreamPublisher{transport: transport}
}

func (publisher *CircleMembershipStreamPublisher) Publish(ctx context.Context, event membershipports.OutboxEvent) error {
	if publisher == nil || publisher.transport == nil {
		return fmt.Errorf("CircleMembership stream publisher is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 || event.OccurredAt.IsZero() {
		return fmt.Errorf("CircleMembership event identity is incomplete")
	}
	if !json.Valid(event.Payload) {
		return fmt.Errorf("CircleMembership event payload is not valid JSON")
	}
	if err := appendCircleDurableRecord(ctx, publisher.transport, CircleMembershipStream, map[string]string{
		"eventId": event.EventID, "eventType": event.EventType,
		"aggregateType": "CircleMembership", "aggregateId": event.AggregateID,
		"aggregateVersion": strconv.FormatInt(event.AggregateVersion, 10),
		"payload":          string(event.Payload), "occurredAt": event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}, CircleMembershipStreamRetention); err != nil {
		return fmt.Errorf("append CircleMembership stream: %w", err)
	}
	return nil
}

var _ membershipports.OutboxPublisher = (*CircleMembershipStreamPublisher)(nil)
