package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	ports "quwoquan_service/services/circle-service/internal/domain/circle/circle_group_membership/ports"
)

const (
	CircleGroupMembershipStream          = "events.circle.group-memberships"
	CircleGroupMembershipStreamRetention = 7 * 24 * time.Hour
)

type CircleGroupMembershipStreamPublisher struct{ transport durableStreamTransport }

func NewCircleGroupMembershipStreamPublisher(transport durableStreamTransport) *CircleGroupMembershipStreamPublisher {
	return &CircleGroupMembershipStreamPublisher{transport: transport}
}

func (publisher *CircleGroupMembershipStreamPublisher) Publish(ctx context.Context, event ports.OutboxEvent) error {
	if publisher == nil || publisher.transport == nil {
		return fmt.Errorf("CircleGroupMembership stream publisher is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 || event.OccurredAt.IsZero() {
		return fmt.Errorf("CircleGroupMembership event identity is incomplete")
	}
	if !json.Valid(event.Payload) {
		return fmt.Errorf("CircleGroupMembership event payload is not valid JSON")
	}
	if err := appendCircleDurableRecord(ctx, publisher.transport, CircleGroupMembershipStream, map[string]string{
		"eventId": event.EventID, "eventType": event.EventType, "aggregateType": "CircleGroupMembership",
		"aggregateId": event.AggregateID, "aggregateVersion": strconv.FormatInt(event.AggregateVersion, 10),
		"payload": string(event.Payload), "occurredAt": event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}, CircleGroupMembershipStreamRetention); err != nil {
		return fmt.Errorf("append CircleGroupMembership stream: %w", err)
	}
	return nil
}

var _ ports.OutboxPublisher = (*CircleGroupMembershipStreamPublisher)(nil)
