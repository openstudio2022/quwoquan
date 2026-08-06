// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/shared-surface-skill-placement/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	placementapp "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/application"
	placementmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/model"
	placementports "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/ports"
	placementmessaging "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/infrastructure/messaging"
)

type placementOutboxFixture struct {
	event      placementports.OutboxEvent
	available  bool
	marked     int
	retried    int
	claimOwner string
}

func (fixture *placementOutboxFixture) ClaimPendingOutbox(
	_ context.Context, owner string, _ time.Time, _ time.Duration,
) (placementports.OutboxEvent, bool, error) {
	fixture.claimOwner = owner
	return fixture.event, fixture.available, nil
}

func (fixture *placementOutboxFixture) MarkOutboxPublished(
	_ context.Context, _ string, owner string, _ time.Time,
) error {
	if owner != fixture.claimOwner {
		return placementports.ErrOutboxClaimLost
	}
	fixture.marked++
	fixture.available = false
	return nil
}

func (fixture *placementOutboxFixture) ScheduleOutboxRetry(
	_ context.Context, _ string, owner string, _ time.Time, _ string,
) error {
	if owner != fixture.claimOwner {
		return placementports.ErrOutboxClaimLost
	}
	fixture.retried++
	fixture.available = false
	return nil
}

type placementTransportFixture struct {
	fail      bool
	message   runtimemessaging.DurableMessage
	retention time.Duration
}

func (fixture *placementTransportFixture) AppendDurable(
	_ context.Context, message runtimemessaging.DurableMessage,
) (string, error) {
	if fixture.fail {
		return "", errors.New("transport unavailable")
	}
	fixture.message = message
	return "1-0", nil
}

func (fixture *placementTransportFixture) SetDurableRetention(
	_ context.Context, _ string, retention time.Duration,
) error {
	fixture.retention = retention
	return nil
}

func TestPlacementRelayCheckpointsOnlyAfterDurableHandoff(t *testing.T) {
	now := time.Date(2026, 8, 5, 11, 0, 0, 0, time.UTC)
	event := placementports.OutboxEvent{
		EventID: "placement-1:1", EventType: placementmodel.EventChanged,
		AggregateID: "placement-1", AggregateVersion: 1,
		Payload:    []byte(`{"id":"placement-1","surfaceKind":"circle","surfaceId":"circle-1","policy":"allow_list","disabledSkillIds":[],"status":"active","revision":1,"updatedAt":"2026-08-05T11:00:00Z"}`),
		OccurredAt: now, AttemptCount: 1,
	}
	outbox := &placementOutboxFixture{event: event, available: true}
	transport := &placementTransportFixture{fail: true}
	publisher, err := placementmessaging.NewEventPublisher(transport)
	if err != nil {
		t.Fatalf("NewEventPublisher() error = %v", err)
	}
	relay, err := placementapp.NewOutboxRelay(outbox, publisher)
	if err != nil {
		t.Fatalf("NewOutboxRelay() error = %v", err)
	}
	if count, err := relay.Drain(context.Background(), 1); err == nil || count != 0 {
		t.Fatalf("failed Drain() = (%d, %v), want (0, error)", count, err)
	}
	if outbox.marked != 0 || outbox.retried != 1 {
		t.Fatalf("failed delivery marked=%d retried=%d", outbox.marked, outbox.retried)
	}
	if err := relay.Healthy(context.Background(), time.Minute); err == nil {
		t.Fatal("Healthy() succeeded while durable handoff is failed")
	}
	outbox.available = true
	transport.fail = false
	if count, err := relay.Drain(context.Background(), 1); err != nil || count != 1 {
		t.Fatalf("recovered Drain() = (%d, %v), want (1, nil)", count, err)
	}
	fields := runtimemessaging.DurableFieldMap(transport.message.Fields)
	if outbox.marked != 1 || transport.message.Stream != placementmessaging.SkillSurfacePlacementEventStream ||
		fields["aggregateId"] != event.AggregateID || fields["payload"] == "" || transport.retention <= 0 {
		t.Fatalf("placement delivery mismatch: marked=%d stream=%q fields=%v retention=%s", outbox.marked, transport.message.Stream, fields, transport.retention)
	}
	if err := relay.Healthy(context.Background(), time.Minute); err != nil {
		t.Fatalf("Healthy() after recovery error = %v", err)
	}
}
