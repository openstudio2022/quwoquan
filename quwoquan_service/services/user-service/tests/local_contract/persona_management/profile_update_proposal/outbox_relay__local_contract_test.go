// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/spec.md#sit-001
package local_contract

import (
	"context"
	"errors"
	"slices"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	proposalapp "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/application"
	proposalevent "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/event"
	proposalports "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/ports"
	proposalmessaging "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/infrastructure/messaging"
)

type profileProposalRecordedTransport struct {
	durable []runtimemessaging.DurableMessage
}

func (*profileProposalRecordedTransport) PublishEphemeral(
	context.Context,
	runtimemessaging.EphemeralMessage,
) error {
	return nil
}

func (*profileProposalRecordedTransport) SubscribeEphemeral(
	context.Context,
	...string,
) (runtimemessaging.EphemeralSubscription, error) {
	return nil, nil
}

func (transport *profileProposalRecordedTransport) AppendDurable(
	_ context.Context,
	message runtimemessaging.DurableMessage,
) (string, error) {
	transport.durable = append(transport.durable, message)
	return "1-0", nil
}

func TestProfileUpdateProposalPublisherUsesCanonicalStreamAndRawOutboxPayload(
	t *testing.T,
) {
	t.Parallel()
	now := time.Date(2026, time.July, 26, 12, 30, 0, 0, time.UTC)
	payload := []byte(
		`{"id":"proposal-1","personaId":"persona-1","status":"pending","version":1}`,
	)
	transport := &profileProposalRecordedTransport{}
	publisher := proposalmessaging.NewEventPublisher(transport)
	if err := publisher.PublishProfileUpdateProposal(
		context.Background(),
		proposalports.OutboxEvent{
			EventID:          "proposal-event-1",
			AggregateID:      "proposal-1",
			AggregateVersion: 1,
			EventType:        proposalevent.ProfileUpdateProposalCreated,
			PayloadJSON:      payload,
			OccurredAt:       now,
		},
	); err != nil {
		t.Fatalf("publish ProfileUpdateProposal event: %v", err)
	}
	if len(transport.durable) != 1 {
		t.Fatalf("durable messages=%d, want 1", len(transport.durable))
	}
	message := transport.durable[0]
	if message.Stream != proposalmessaging.EventStream {
		t.Fatalf(
			"stream=%q, want %q",
			message.Stream,
			proposalmessaging.EventStream,
		)
	}
	fields := durableFieldMap(t, message.Fields)
	want := map[string]string{
		"eventId":         "proposal-event-1",
		"eventName":       proposalevent.ProfileUpdateProposalCreated,
		"proposalId":      "proposal-1",
		"proposalVersion": "1",
		"payload":         string(payload),
		"occurredAt":      now.Format(time.RFC3339Nano),
	}
	if len(fields) != len(want) {
		t.Fatalf("durable fields=%#v, want %#v", fields, want)
	}
	for name, value := range want {
		if fields[name] != value {
			t.Fatalf("field %s=%q, want %q", name, fields[name], value)
		}
	}
}

func TestProfileUpdateProposalRelayRetainsFailureAndReplaysAfterRestart(
	t *testing.T,
) {
	t.Parallel()
	now := time.Date(2026, time.July, 26, 13, 0, 0, 0, time.UTC)
	events := []proposalports.OutboxEvent{
		{
			EventID:          "event-1",
			AggregateID:      "proposal-1",
			AggregateVersion: 1,
			EventType:        proposalevent.ProfileUpdateProposalCreated,
			PayloadJSON:      []byte(`{"id":"proposal-1","version":1}`),
			OccurredAt:       now,
		},
		{
			EventID:          "event-2",
			AggregateID:      "proposal-1",
			AggregateVersion: 2,
			EventType:        proposalevent.ProfileUpdateProposalConfirmed,
			PayloadJSON:      []byte(`{"id":"proposal-1","version":2}`),
			OccurredAt:       now.Add(time.Second),
		},
	}
	outbox := newProfileProposalMemoryOutbox(events)
	publisher := &profileProposalRecordingPublisher{failOnce: true}
	firstRelay, err := proposalapp.NewOutboxRelay(outbox, publisher)
	if err != nil {
		t.Fatalf("new first relay: %v", err)
	}
	if published, err := firstRelay.Drain(context.Background(), 100); err == nil ||
		published != 0 {
		t.Fatalf("first drain=(%d, %v), want retained publish failure", published, err)
	}
	if len(outbox.published) != 0 ||
		!slices.Equal(outbox.released, []string{"event-1", "event-2"}) {
		t.Fatalf(
			"failure advanced checkpoint: published=%v released=%v",
			outbox.published,
			outbox.released,
		)
	}
	if err := firstRelay.Healthy(context.Background(), time.Second); err == nil {
		t.Fatal("failed relay must be unready")
	}

	restartedRelay, err := proposalapp.NewOutboxRelay(outbox, publisher)
	if err != nil {
		t.Fatalf("new restarted relay: %v", err)
	}
	published, err := restartedRelay.Drain(context.Background(), 100)
	if err != nil || published != 2 {
		t.Fatalf("restart drain=(%d, %v), want both events", published, err)
	}
	if !slices.Equal(outbox.published, []string{"event-1", "event-2"}) {
		t.Fatalf("published checkpoints=%v", outbox.published)
	}
	if !slices.Equal(publisher.eventIDs, []string{"event-1", "event-1", "event-2"}) {
		t.Fatalf(
			"replay identities=%v, want stable duplicate eventId",
			publisher.eventIDs,
		)
	}
	if err := restartedRelay.Healthy(context.Background(), time.Second); err != nil {
		t.Fatalf("restarted relay readiness: %v", err)
	}
}

type profileProposalMemoryOutbox struct {
	events    []proposalports.OutboxEvent
	claims    map[string]string
	published []string
	released  []string
}

func newProfileProposalMemoryOutbox(
	events []proposalports.OutboxEvent,
) *profileProposalMemoryOutbox {
	return &profileProposalMemoryOutbox{
		events: events,
		claims: map[string]string{},
	}
}

func (outbox *profileProposalMemoryOutbox) ClaimPendingOutbox(
	_ context.Context,
	ownerID string,
	_ time.Duration,
	limit int,
) ([]proposalports.OutboxEvent, error) {
	result := make([]proposalports.OutboxEvent, 0, min(limit, len(outbox.events)))
	for _, event := range outbox.events {
		if slices.Contains(outbox.published, event.EventID) ||
			outbox.claims[event.EventID] != "" {
			continue
		}
		outbox.claims[event.EventID] = ownerID
		result = append(result, event)
		if len(result) == limit {
			break
		}
	}
	return result, nil
}

func (outbox *profileProposalMemoryOutbox) MarkOutboxPublished(
	_ context.Context,
	eventID string,
	ownerID string,
) error {
	if outbox.claims[eventID] != ownerID {
		return proposalports.ErrOutboxClaimLost
	}
	delete(outbox.claims, eventID)
	outbox.published = append(outbox.published, eventID)
	return nil
}

func (outbox *profileProposalMemoryOutbox) ReleaseOutboxClaim(
	_ context.Context,
	eventID string,
	ownerID string,
) error {
	if outbox.claims[eventID] == ownerID {
		delete(outbox.claims, eventID)
		outbox.released = append(outbox.released, eventID)
	}
	return nil
}

type profileProposalRecordingPublisher struct {
	eventIDs []string
	failOnce bool
}

func (publisher *profileProposalRecordingPublisher) PublishProfileUpdateProposal(
	_ context.Context,
	event proposalports.OutboxEvent,
) error {
	publisher.eventIDs = append(publisher.eventIDs, event.EventID)
	if publisher.failOnce {
		publisher.failOnce = false
		return errors.New("simulated publish acknowledgement loss")
	}
	return nil
}

func durableFieldMap(
	t *testing.T,
	fields []runtimemessaging.DurableField,
) map[string]string {
	t.Helper()
	result := make(map[string]string, len(fields))
	for _, field := range fields {
		if _, exists := result[field.Name]; exists {
			t.Fatalf("duplicate durable field %q", field.Name)
		}
		result[field.Name] = field.Value
	}
	return result
}
