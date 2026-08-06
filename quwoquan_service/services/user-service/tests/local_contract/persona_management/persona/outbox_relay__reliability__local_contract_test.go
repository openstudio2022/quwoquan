// spec_ref: specs/feature-tree/user-profile/persona-management/persona/spec.md
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	personaapp "quwoquan_service/services/user-service/internal/persona_management/persona/application/persona"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
	personamessaging "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/messaging"
)

type personaOutboxFixture struct {
	event     personaports.PersonaOutboxEvent
	marked    int
	retried   int
	nextRetry time.Time
}

func (fixture *personaOutboxFixture) ClaimPendingOutbox(context.Context, time.Time, time.Duration) (personaports.PersonaOutboxEvent, bool, error) {
	if fixture.marked > 0 {
		return personaports.PersonaOutboxEvent{}, false, nil
	}
	fixture.event.AttemptCount++
	fixture.event.ClaimUntil = time.Now().UTC().Add(30 * time.Second)
	return fixture.event, true, nil
}

func (fixture *personaOutboxFixture) MarkPublished(_ context.Context, _ string, claimUntil time.Time, _ time.Time) error {
	if !claimUntil.Equal(fixture.event.ClaimUntil) {
		return personaports.ErrPersonaOutboxCheckpointLost
	}
	fixture.marked++
	return nil
}

func (fixture *personaOutboxFixture) SchedulePublicationRetry(_ context.Context, _ string, claimUntil time.Time, next time.Time, digest string) error {
	if digest == "" {
		return errors.New("missing failure digest")
	}
	if !claimUntil.Equal(fixture.event.ClaimUntil) {
		return personaports.ErrPersonaOutboxCheckpointLost
	}
	fixture.retried++
	fixture.nextRetry = next
	return nil
}

type personaTransportFixture struct {
	fail      bool
	message   runtimemessaging.DurableMessage
	retention time.Duration
}

func (fixture *personaTransportFixture) AppendDurable(_ context.Context, message runtimemessaging.DurableMessage) (string, error) {
	if fixture.fail {
		return "", errors.New("transport unavailable")
	}
	fixture.message = message
	return "1-0", nil
}

func (fixture *personaTransportFixture) SetDurableRetention(_ context.Context, _ string, retention time.Duration) error {
	fixture.retention = retention
	return nil
}

func TestPersonaOutboxRelayRetriesWithoutPrematureAcknowledgement(t *testing.T) {
	now := time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC)
	outbox := &personaOutboxFixture{event: personaports.PersonaOutboxEvent{
		EventID: "persona-event-1", EventType: personaports.PersonaCreatedEvent,
		OwnerID: "user-1", AggregateID: "persona-1", AggregateVersion: 1,
		PayloadJSON: []byte(`{"userId":"user-1","personaId":"persona-1"}`),
		OccurredAt:  now,
	}}
	transport := &personaTransportFixture{fail: true}
	publisher, err := personamessaging.NewEventPublisher(transport)
	if err != nil {
		t.Fatalf("NewEventPublisher() error = %v", err)
	}
	relay, err := personaapp.NewOutboxRelay(outbox, publisher)
	if err != nil {
		t.Fatalf("NewOutboxRelay() error = %v", err)
	}

	if count, err := relay.Drain(context.Background(), 1); err == nil || count != 0 {
		t.Fatalf("failed Drain() = (%d, %v), want (0, error)", count, err)
	}
	if outbox.marked != 0 || outbox.retried != 1 || outbox.nextRetry.IsZero() {
		t.Fatalf("failed publish state: marked=%d retried=%d nextRetry=%s", outbox.marked, outbox.retried, outbox.nextRetry)
	}

	transport.fail = false
	if count, err := relay.Drain(context.Background(), 1); err != nil || count != 1 {
		t.Fatalf("recovered Drain() = (%d, %v), want (1, nil)", count, err)
	}
	fields := runtimemessaging.DurableFieldMap(transport.message.Fields)
	if outbox.marked != 1 || transport.message.Stream != personamessaging.PersonaEventStream ||
		fields["eventId"] != outbox.event.EventID || fields["personaVersion"] != "1" ||
		transport.retention != personamessaging.PersonaEventStreamRetention {
		t.Fatalf("Persona delivery mismatch: marked=%d stream=%q fields=%v retention=%s", outbox.marked, transport.message.Stream, fields, transport.retention)
	}
}

func TestPersonaPublisherMapsAllContractEventsToExactCanonicalIdentity(t *testing.T) {
	tests := []struct {
		sourceType, canonicalType string
	}{
		{personaports.PersonaCreatedEvent, personaports.PersonaCreatedEvent},
		{personaports.PersonaUpdatedEvent, personaports.PersonaUpdatedEvent},
		{personaports.PersonaRetiredEvent, personaports.PersonaRetiredEvent},
		{personaports.PersonaActivatedEvent, personaports.PersonaActivatedEvent},
	}
	for _, test := range tests {
		t.Run(test.sourceType, func(t *testing.T) {
			transport := &personaTransportFixture{}
			publisher, err := personamessaging.NewEventPublisher(transport)
			if err != nil {
				t.Fatalf("NewEventPublisher() error = %v", err)
			}
			err = publisher.PublishPersona(context.Background(), personaports.PersonaOutboxEvent{
				EventID: "event-1", OwnerID: "user-1", AggregateID: "persona-1",
				AggregateVersion: 3, EventType: test.sourceType,
				PayloadJSON: []byte(`{"proposalId":"extra","personaId":"wrong"}`),
				OccurredAt:  time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC),
			})
			if err != nil {
				t.Fatalf("PublishPersona() error = %v", err)
			}
			fields := runtimemessaging.DurableFieldMap(transport.message.Fields)
			if fields["eventName"] != test.canonicalType {
				t.Fatalf("eventName = %q, want %q", fields["eventName"], test.canonicalType)
			}
			var payload map[string]string
			if err := json.Unmarshal([]byte(fields["payload"]), &payload); err != nil {
				t.Fatalf("decode canonical Persona payload: %v", err)
			}
			if len(payload) != 2 || payload["userId"] != "user-1" || payload["personaId"] != "persona-1" {
				t.Fatalf("Persona payload = %#v", payload)
			}
		})
	}
}
