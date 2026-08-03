package messaging

import (
	"context"
	"fmt"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	domaineventing "quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/eventing"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/ports"
	infraeventing "quwoquan_service/services/travel-service/internal/travel/trip_plan/infrastructure/eventing"
)

const (
	TripPlanEventStream = domaineventing.TripPlanStream
)

type durableTransport interface {
	AppendDurable(context.Context, runtimemessaging.DurableMessage) (string, error)
	SetDurableRetention(context.Context, string, time.Duration) error
}

type StreamPublisher struct {
	delegate *infraeventing.StreamPublisher
}

func NewStreamPublisher(transport durableTransport) (*StreamPublisher, error) {
	if transport == nil {
		return nil, fmt.Errorf("TripPlan stream publisher requires durable transport")
	}
	delegate, err := infraeventing.NewStreamPublisher(transport)
	if err != nil {
		return nil, err
	}
	return &StreamPublisher{delegate: delegate}, nil
}

func (publisher *StreamPublisher) Publish(ctx context.Context, event ports.OutboxEvent) error {
	if publisher == nil || publisher.delegate == nil {
		return fmt.Errorf("TripPlan stream publisher is unavailable")
	}
	return publisher.delegate.Publish(ctx, domaineventing.Event{
		Source: "TripPlan", EventID: event.EventID, EventType: event.EventType,
		AggregateID: event.AggregateID, AggregateVersion: event.AggregateVersion,
		Payload: event.Payload, OccurredAt: event.OccurredAt,
	})
}

var _ ports.EventPublisher = (*StreamPublisher)(nil)
