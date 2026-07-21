package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	homepageports "quwoquan_service/services/entity-service/internal/domain/homepage/ports"
	claimports "quwoquan_service/services/entity-service/internal/domain/homepage_claim_request/ports"
	statusports "quwoquan_service/services/entity-service/internal/domain/homepage_status_report/ports"
)

const (
	HomepageLifecycleStream          = "events.entity.homepage_lifecycle"
	HomepageLifecycleStreamRetention = 7 * 24 * time.Hour
)

type lifecycleEvent struct {
	eventID          string
	eventType        string
	aggregateType    string
	aggregateID      string
	aggregateVersion int64
	payload          []byte
	occurredAt       time.Time
}

type lifecycleStream struct {
	transport durableStreamTransport
}

func (stream *lifecycleStream) publish(
	ctx context.Context,
	event lifecycleEvent,
) error {
	if stream == nil || stream.transport == nil {
		return fmt.Errorf("homepage lifecycle stream publisher is not configured")
	}
	if strings.TrimSpace(event.eventID) == "" ||
		strings.TrimSpace(event.eventType) == "" ||
		strings.TrimSpace(event.aggregateID) == "" ||
		event.aggregateVersion <= 0 ||
		event.occurredAt.IsZero() ||
		!json.Valid(event.payload) {
		return fmt.Errorf("homepage lifecycle event is incomplete")
	}
	err := appendEntityDurableRecord(
		ctx,
		stream.transport,
		HomepageLifecycleStream,
		map[string]string{
			"eventId":          event.eventID,
			"eventType":        event.eventType,
			"aggregateType":    event.aggregateType,
			"aggregateId":      event.aggregateID,
			"aggregateVersion": strconv.FormatInt(event.aggregateVersion, 10),
			"payload":          string(event.payload),
			"occurredAt":       event.occurredAt.UTC().Format(time.RFC3339Nano),
		},
		HomepageLifecycleStreamRetention,
	)
	if err != nil {
		return fmt.Errorf("append homepage lifecycle stream: %w", err)
	}
	return nil
}

type HomepageLifecycleStreamPublisher struct{ lifecycleStream }

func NewHomepageLifecycleStreamPublisher(
	transport durableStreamTransport,
) *HomepageLifecycleStreamPublisher {
	return &HomepageLifecycleStreamPublisher{lifecycleStream{transport: transport}}
}

func (publisher *HomepageLifecycleStreamPublisher) Publish(
	ctx context.Context,
	event homepageports.OutboxEvent,
) error {
	return publisher.publish(ctx, lifecycleEvent{
		eventID: event.EventID, eventType: event.EventType,
		aggregateType: "Homepage", aggregateID: event.AggregateID,
		aggregateVersion: event.AggregateVersion,
		payload: event.Payload, occurredAt: event.OccurredAt,
	})
}

type HomepageClaimLifecycleStreamPublisher struct{ lifecycleStream }

func NewHomepageClaimLifecycleStreamPublisher(
	transport durableStreamTransport,
) *HomepageClaimLifecycleStreamPublisher {
	return &HomepageClaimLifecycleStreamPublisher{lifecycleStream{transport: transport}}
}

func (publisher *HomepageClaimLifecycleStreamPublisher) Publish(
	ctx context.Context,
	event claimports.OutboxEvent,
) error {
	return publisher.publish(ctx, lifecycleEvent{
		eventID: event.EventID, eventType: event.EventType,
		aggregateType: "HomepageClaimRequest", aggregateID: event.AggregateID,
		aggregateVersion: event.AggregateVersion,
		payload: event.Payload, occurredAt: event.OccurredAt,
	})
}

type HomepageStatusLifecycleStreamPublisher struct{ lifecycleStream }

func NewHomepageStatusLifecycleStreamPublisher(
	transport durableStreamTransport,
) *HomepageStatusLifecycleStreamPublisher {
	return &HomepageStatusLifecycleStreamPublisher{lifecycleStream{transport: transport}}
}

func (publisher *HomepageStatusLifecycleStreamPublisher) Publish(
	ctx context.Context,
	event statusports.OutboxEvent,
) error {
	return publisher.publish(ctx, lifecycleEvent{
		eventID: event.EventID, eventType: event.EventType,
		aggregateType: "HomepageStatusReport", aggregateID: event.AggregateID,
		aggregateVersion: event.AggregateVersion,
		payload: event.Payload, occurredAt: event.OccurredAt,
	})
}

var (
	_ homepageports.OutboxPublisher = (*HomepageLifecycleStreamPublisher)(nil)
	_ claimports.OutboxPublisher    = (*HomepageClaimLifecycleStreamPublisher)(nil)
	_ statusports.OutboxPublisher   = (*HomepageStatusLifecycleStreamPublisher)(nil)
)
