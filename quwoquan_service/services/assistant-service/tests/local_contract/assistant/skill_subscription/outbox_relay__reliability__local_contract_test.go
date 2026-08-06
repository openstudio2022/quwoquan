// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001
package skill_subscription

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	subscriptionapp "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
	subscriptionmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
	subscriptionports "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/ports"
	subscriptionmessaging "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/infrastructure/messaging"
)

type subscriptionOutboxFixture struct {
	event      subscriptionports.OutboxEvent
	available  bool
	marked     int
	retried    int
	claimOwner string
}

func (fixture *subscriptionOutboxFixture) ClaimPendingOutbox(
	_ context.Context, owner string, _ time.Time, _ time.Duration,
) (subscriptionports.OutboxEvent, bool, error) {
	fixture.claimOwner = owner
	return fixture.event, fixture.available, nil
}

func (fixture *subscriptionOutboxFixture) MarkOutboxPublished(
	_ context.Context, _ string, owner string, _ time.Time,
) error {
	if owner != fixture.claimOwner {
		return subscriptionports.ErrOutboxClaimLost
	}
	fixture.marked++
	fixture.available = false
	return nil
}

func (fixture *subscriptionOutboxFixture) ScheduleOutboxRetry(
	_ context.Context, _ string, owner string, _ time.Time, _ time.Time, _ string,
) error {
	if owner != fixture.claimOwner {
		return subscriptionports.ErrOutboxClaimLost
	}
	fixture.retried++
	fixture.available = false
	return nil
}

type subscriptionTransportFixture struct {
	fail      bool
	message   runtimemessaging.DurableMessage
	retention time.Duration
}

func (fixture *subscriptionTransportFixture) AppendDurable(
	_ context.Context, message runtimemessaging.DurableMessage,
) (string, error) {
	if fixture.fail {
		return "", errors.New("transport unavailable")
	}
	fixture.message = message
	return "1-0", nil
}

func (fixture *subscriptionTransportFixture) SetDurableRetention(
	_ context.Context, _ string, retention time.Duration,
) error {
	fixture.retention = retention
	return nil
}

func TestSubscriptionRelayPublishesRedactedLifecycleEvent(t *testing.T) {
	now := time.Date(2026, 8, 5, 13, 0, 0, 0, time.UTC)
	event := subscriptionports.OutboxEvent{
		EventID: "subscription-1:1:created", EventType: subscriptionmodel.EventCreated,
		AggregateID: "subscription-1", AggregateVersion: 1,
		Payload:    []byte(`{"subscriptionId":"subscription-1"}`),
		OccurredAt: now, AttemptCount: 1,
	}
	outbox := &subscriptionOutboxFixture{event: event, available: true}
	transport := &subscriptionTransportFixture{fail: true}
	publisher, err := subscriptionmessaging.NewEventPublisher(transport)
	if err != nil {
		t.Fatal(err)
	}
	relay, err := subscriptionapp.NewOutboxRelay(outbox, publisher)
	if err != nil {
		t.Fatal(err)
	}
	if count, err := relay.Drain(t.Context(), 1); err == nil || count != 0 {
		t.Fatalf("failed Drain() = (%d, %v), want (0, error)", count, err)
	}
	if outbox.marked != 0 || outbox.retried != 1 {
		t.Fatalf("failed delivery marked/retried = %d/%d, want 0/1", outbox.marked, outbox.retried)
	}
	outbox.available = true
	transport.fail = false
	if count, err := relay.Drain(t.Context(), 1); err != nil || count != 1 {
		t.Fatalf("recovered Drain() = (%d, %v), want (1, nil)", count, err)
	}
	fields := runtimemessaging.DurableFieldMap(transport.message.Fields)
	if outbox.marked != 1 || transport.message.Stream != subscriptionmessaging.SkillSubscriptionEventStream ||
		fields["eventName"] != subscriptionmodel.EventCreated || transport.retention <= 0 {
		t.Fatalf("subscription delivery mismatch: marked=%d stream=%q fields=%v retention=%s",
			outbox.marked, transport.message.Stream, fields, transport.retention)
	}
	if strings.Contains(fields["payload"], "destination") || strings.Contains(fields["payload"], "trigger") {
		t.Fatalf("subscription private delivery details leaked: %q", fields["payload"])
	}
}

func TestSubscriptionRelayRejectsNonCanonicalPayloads(t *testing.T) {
	now := time.Date(2026, 8, 5, 15, 0, 0, 0, time.UTC)
	tests := map[string]string{
		"extra key":     `{"subscriptionId":"subscription-1","destination":"private"}`,
		"null identity": `{"subscriptionId":null}`,
		"duplicate key": `{"subscriptionId":"subscription-1","subscriptionId":"subscription-2"}`,
	}
	for name, payload := range tests {
		t.Run(name, func(t *testing.T) {
			outbox := &subscriptionOutboxFixture{available: true, event: subscriptionports.OutboxEvent{
				EventID: "subscription-1:1", EventType: subscriptionmodel.EventCreated,
				AggregateID: "subscription-1", AggregateVersion: 1,
				Payload: []byte(payload), OccurredAt: now, AttemptCount: 1,
			}}
			transport := &subscriptionTransportFixture{}
			publisher, err := subscriptionmessaging.NewEventPublisher(transport)
			if err != nil {
				t.Fatal(err)
			}
			relay, err := subscriptionapp.NewOutboxRelay(outbox, publisher)
			if err != nil {
				t.Fatal(err)
			}
			if count, err := relay.Drain(t.Context(), 1); err == nil || count != 0 {
				t.Fatalf("Drain()=(%d,%v), want fail-closed", count, err)
			}
			if outbox.retried != 1 || outbox.marked != 0 || transport.message.Stream != "" {
				t.Fatalf("invalid payload escaped relay: outbox=%+v message=%+v", outbox, transport.message)
			}
		})
	}
}
