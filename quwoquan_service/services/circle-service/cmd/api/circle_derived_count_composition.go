package bootstrap

import (
	"context"

	circleapp "quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	behaviorfactports "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/domain/ports"
	membershipports "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/domain/ports"
	placementports "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/domain/ports"
)

// These composition adapters translate source-owned outbox records into the
// target-owned circle lifecycle input. They contain no business policy.
type circleMembershipCountConsumer struct {
	handler *circleapp.CircleMemberCountProjectionHandler
}

func (consumer circleMembershipCountConsumer) Publish(ctx context.Context, event membershipports.OutboxEvent) error {
	return consumer.handler.Apply(ctx, circleapp.DerivedCountEvent{
		Source: circleapp.DerivedCountSourceMembership, EventID: event.EventID,
		EventType: event.EventType, AggregateID: event.AggregateID,
		AggregateVersion: event.AggregateVersion, Payload: event.Payload,
		OccurredAt: event.OccurredAt,
	})
}

type circlePostCountConsumer struct {
	handler *circleapp.CirclePostCountProjectionHandler
}

func (consumer circlePostCountConsumer) Publish(ctx context.Context, event placementports.OutboxEvent) error {
	return consumer.handler.Apply(ctx, circleapp.DerivedCountEvent{
		Source: circleapp.DerivedCountSourcePostPlacement, EventID: event.EventID,
		EventType: event.EventType, AggregateID: event.AggregateID,
		AggregateVersion: event.AggregateVersion, Payload: event.Payload,
		OccurredAt: event.OccurredAt,
	})
}

type circleWeeklyActiveConsumer struct {
	handler *circleapp.CircleWeeklyActiveProjectionHandler
}

func (consumer circleWeeklyActiveConsumer) Publish(ctx context.Context, event behaviorfactports.OutboxEvent) error {
	return consumer.handler.Apply(ctx, circleapp.DerivedCountEvent{
		Source: circleapp.DerivedCountSourceBehaviorFact, EventID: event.EventID,
		EventType: event.EventType, AggregateID: event.AggregateID,
		Payload: event.Payload, OccurredAt: event.OccurredAt,
	})
}
