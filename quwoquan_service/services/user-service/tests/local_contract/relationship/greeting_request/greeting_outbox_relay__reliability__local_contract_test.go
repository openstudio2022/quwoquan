// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/greeting-request-inbox-and-upgrade/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	greetingapp "quwoquan_service/services/user-service/internal/relationship/greeting_request/application"
	greetingports "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/ports"
)

type greetingOutboxFixture struct {
	event     greetingports.GreetingOutboxEvent
	marked    int
	retried   int
	nextRetry time.Time
}

func (fixture *greetingOutboxFixture) ClaimPendingOutbox(context.Context, string, time.Duration, int) ([]greetingports.GreetingOutboxEvent, error) {
	if fixture.marked > 0 {
		return nil, nil
	}
	return []greetingports.GreetingOutboxEvent{fixture.event}, nil
}

func (fixture *greetingOutboxFixture) MarkOutboxPublished(context.Context, string, string) error {
	fixture.marked++
	return nil
}

func (fixture *greetingOutboxFixture) ScheduleOutboxRetry(
	_ context.Context,
	_ string,
	_ string,
	lease time.Duration,
	nextAttemptAt time.Time,
) error {
	if lease <= 0 || !nextAttemptAt.After(time.Now().UTC()) {
		return errors.New("retry schedule is not durable backoff")
	}
	fixture.retried++
	fixture.nextRetry = nextAttemptAt
	return nil
}

type greetingUserEventsFixture struct {
	publishes int
	userID    string
	payload   map[string]any
}

func (fixture *greetingUserEventsFixture) PublishUserEvent(
	_ context.Context,
	_ string,
	userID string,
	_ string,
	payload map[string]any,
) error {
	fixture.publishes++
	fixture.userID = userID
	fixture.payload = payload
	return nil
}

type greetingStreamFixture struct {
	fail      bool
	publishes int
	event     greetingapp.GreetingStreamEvent
}

func (fixture *greetingStreamFixture) PublishGreetingEvent(_ context.Context, event greetingapp.GreetingStreamEvent) error {
	fixture.publishes++
	if fixture.fail {
		return errors.New("durable stream unavailable")
	}
	fixture.event = event
	return nil
}

func TestGreetingOutboxRelayAcknowledgesOnlyAfterAllPublicationChannelsSucceed(t *testing.T) {
	now := time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC)
	outbox := &greetingOutboxFixture{event: greetingports.GreetingOutboxEvent{
		EventID: "greeting-1:1", AggregateID: "greeting-1", EventName: "GreetingRequestSent",
		Payload: map[string]any{
			"id":                 "greeting-1",
			"requesterPersonaId": "persona-a", "targetPersonaId": "persona-b",
			"recipientAccountId": "account-b",
			"source":             "profile", "expireAt": "2026-09-04T12:00:00Z",
			"targetAllowsStrangerGreeting": true,
		},
		OccurredAt: now,
	}}
	userEvents := &greetingUserEventsFixture{}
	stream := &greetingStreamFixture{fail: true}
	relay := greetingapp.NewGreetingOutboxRelay(outbox, userEvents, stream)

	if count, err := relay.Drain(context.Background(), 1); err == nil || count != 0 {
		t.Fatalf("failed Drain() = (%d, %v), want (0, error)", count, err)
	}
	if outbox.marked != 0 || outbox.retried != 1 || outbox.nextRetry.IsZero() {
		t.Fatalf("failed publication state: marked=%d retried=%d nextRetry=%s", outbox.marked, outbox.retried, outbox.nextRetry)
	}

	stream.fail = false
	if count, err := relay.Drain(context.Background(), 1); err != nil || count != 1 {
		t.Fatalf("recovered Drain() = (%d, %v), want (1, nil)", count, err)
	}
	if outbox.marked != 1 || stream.event.EventID != outbox.event.EventID ||
		stream.event.GreetingID != outbox.event.AggregateID ||
		stream.event.RecipientAccountID != "account-b" ||
		userEvents.publishes != 2 || userEvents.userID != "account-b" ||
		userEvents.payload["recipientAccountId"] != "account-b" {
		t.Fatalf("greeting delivery mismatch: marked=%d event=%+v realtimePublishes=%d", outbox.marked, stream.event, userEvents.publishes)
	}
}
