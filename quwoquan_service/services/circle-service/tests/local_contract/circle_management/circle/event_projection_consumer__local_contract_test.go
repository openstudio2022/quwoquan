// spec_ref: specs/feature-tree/circle-community/spec.md#dom-001
// readiness_case: project-circle-derived-counts-local
package local_contract

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	circleapp "quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	placementapp "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/application"
	placementports "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/domain/ports"
)

type circleProjectionRelayStore struct {
	events     []placementports.OutboxEvent
	checkpoint string
}

func (store *circleProjectionRelayStore) ReadAfter(_ context.Context, checkpoint string, _ int) ([]placementports.OutboxEvent, error) {
	if checkpoint != "" {
		return nil, nil
	}
	return store.events, nil
}

func (store *circleProjectionRelayStore) LoadCheckpoint(context.Context, string) (string, error) {
	return store.checkpoint, nil
}

func (store *circleProjectionRelayStore) SaveCheckpoint(_ context.Context, _ string, checkpoint string) error {
	store.checkpoint = checkpoint
	return nil
}

type circleDerivedCountProjection struct {
	events []circleapp.DerivedCountEvent
}

func (projection *circleDerivedCountProjection) Apply(_ context.Context, event circleapp.DerivedCountEvent) error {
	projection.events = append(projection.events, event)
	return nil
}

type circlePostCountRelayAdapter struct {
	handler *circleapp.CirclePostCountProjectionHandler
}

func (adapter circlePostCountRelayAdapter) Publish(ctx context.Context, event placementports.OutboxEvent) error {
	return adapter.handler.Apply(ctx, circleapp.DerivedCountEvent{
		Source: circleapp.DerivedCountSourcePostPlacement, EventID: event.EventID,
		EventType: event.EventType, AggregateID: event.AggregateID,
		AggregateVersion: event.AggregateVersion, Payload: event.Payload,
		OccurredAt: event.OccurredAt,
	})
}

func TestCircleDerivedCountConsumerAppliesEventBeforeCheckpoint(t *testing.T) {
	store := &circleProjectionRelayStore{events: []placementports.OutboxEvent{{
		EventID: "placement-1:CirclePostPlaced:1", EventType: "CirclePostPlaced",
		AggregateID: "placement-1", AggregateVersion: 1,
		Payload:    json.RawMessage(`{"circleId":"circle-1"}`),
		OccurredAt: time.Date(2026, 8, 5, 8, 0, 0, 0, time.UTC), Checkpoint: "1",
	}}}
	projection := &circleDerivedCountProjection{}
	postHandler := circleapp.NewCirclePostCountProjectionHandler(projection)
	relay := placementapp.NewOutboxRelay(
		store, store, circlePostCountRelayAdapter{handler: postHandler}, "circle-post-count",
	)

	if count, err := relay.Drain(context.Background(), 10); err != nil || count != 1 {
		t.Fatalf("drain count=%d err=%v", count, err)
	}
	if len(projection.events) != 1 || projection.events[0].EventType != "CirclePostPlaced" ||
		projection.events[0].Source != circleapp.DerivedCountSourcePostPlacement {
		t.Fatalf("projection handler state=%+v", projection.events)
	}
	if store.checkpoint != "1" {
		t.Fatalf("projection checkpoint=%q want=1", store.checkpoint)
	}

	memberHandler := circleapp.NewCircleMemberCountProjectionHandler(projection)
	if err := memberHandler.Apply(t.Context(), circleapp.DerivedCountEvent{
		Source: circleapp.DerivedCountSourceMembership, EventID: "membership-1",
		EventType: "CircleMembershipJoined", AggregateID: "membership-1",
		AggregateVersion: 1, Payload: json.RawMessage(`{"circleId":"circle-1"}`),
	}); err != nil {
		t.Fatalf("member-count handler: %v", err)
	}
	weeklyHandler := circleapp.NewCircleWeeklyActiveProjectionHandler(projection)
	if err := weeklyHandler.Apply(t.Context(), circleapp.DerivedCountEvent{
		Source: circleapp.DerivedCountSourceBehaviorFact, EventID: "behavior-1",
		EventType: "CircleBehaviorFactAppended", AggregateID: "behavior-1",
		Payload: json.RawMessage(`{"circleId":"circle-1"}`),
	}); err != nil {
		t.Fatalf("weekly-active handler: %v", err)
	}
	if len(projection.events) != 3 {
		t.Fatalf("all three target-owned handlers must execute, events=%+v", projection.events)
	}
}
