// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/spec.md#sit-001
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	sessionorchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
	sessionports "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	sessionmessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/messaging"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/persistence"
	skillconsenttest "quwoquan_service/services/assistant-service/tests/support/skillconsent"
)

type sessionOutboxPublisherStub struct {
	appended  []runtimemessaging.DurableMessage
	appendErr error
	streams   map[string]time.Duration
}

func (publisher *sessionOutboxPublisherStub) AppendDurable(
	_ context.Context,
	message runtimemessaging.DurableMessage,
) (string, error) {
	if publisher.appendErr != nil {
		return "", publisher.appendErr
	}
	publisher.appended = append(publisher.appended, message)
	return "1-0", nil
}

func (publisher *sessionOutboxPublisherStub) SetDurableRetention(
	_ context.Context,
	stream string,
	retention time.Duration,
) error {
	if publisher.streams == nil {
		publisher.streams = map[string]time.Duration{}
	}
	publisher.streams[stream] = retention
	return nil
}

func durableFieldOf(
	message runtimemessaging.DurableMessage,
	name string,
) string {
	for _, field := range message.Fields {
		if field.Name == name {
			return field.Value
		}
	}
	return ""
}

// TestAssistantSessionCreateCommitsDeclaredDomainEventThroughOutbox proves the
// AssistantSession aggregate mutation and its declared AssistantSessionCreated
// event land together, and that a replayed creation never appends a second
// event.
func TestAssistantSessionCreateCommitsDeclaredDomainEventThroughOutbox(t *testing.T) {
	t.Parallel()
	store := persistence.NewMemorySessionStore()
	service := sessionorchestration.NewAssistantService(
		skillconsenttest.NewMemoryStore(),
		nil,
		sessionorchestration.WithSessionStore(store),
	)
	created, err := service.CreateSession(
		context.Background(),
		"user-outbox",
		assistant.CreateSessionInput{ClientRequestID: "request-outbox"},
	)
	if err != nil {
		t.Fatalf("create session: %v", err)
	}
	pending, err := store.ClaimPendingSessionEvents(
		context.Background(),
		"relay-owner",
		time.Minute,
		16,
	)
	if err != nil {
		t.Fatalf("claim pending session events: %v", err)
	}
	if len(pending) != 1 {
		t.Fatalf(
			"AssistantSession creation must commit exactly one domain event: %#v",
			pending,
		)
	}
	event := pending[0]
	if event.EventType != assistant.SessionCreatedEventType ||
		event.SessionID != created.SessionID ||
		event.Payload.SessionID != created.SessionID ||
		!event.OccurredAt.Equal(created.CreatedAt.UTC()) {
		t.Fatalf("committed event drifted from the aggregate: %#v", event)
	}

	replayed, err := service.CreateSession(
		context.Background(),
		"user-outbox",
		assistant.CreateSessionInput{ClientRequestID: "request-outbox"},
	)
	if err != nil {
		t.Fatalf("replay create session: %v", err)
	}
	if replayed.SessionID != created.SessionID {
		t.Fatalf("idempotent replay created another session: %s", replayed.SessionID)
	}
	// The first claim still holds the lease, so a second pending event would be
	// the only thing a fresh owner could observe.
	again, err := store.ClaimPendingSessionEvents(
		context.Background(),
		"relay-owner-2",
		time.Minute,
		16,
	)
	if err != nil {
		t.Fatalf("claim after replay: %v", err)
	}
	if len(again) != 0 {
		t.Fatalf("replayed creation appended a duplicate event: %#v", again)
	}
}

// TestAssistantSessionOutboxRelayPublishesDeclaredEventStream drives the relay
// over the same store that committed the aggregate and asserts the declared
// event_store channel, aggregate coordinates and payload_fields.
func TestAssistantSessionOutboxRelayPublishesDeclaredEventStream(t *testing.T) {
	t.Parallel()
	store := persistence.NewMemorySessionStore()
	service := sessionorchestration.NewAssistantService(
		skillconsenttest.NewMemoryStore(),
		nil,
		sessionorchestration.WithSessionStore(store),
	)
	created, err := service.CreateSession(
		context.Background(),
		"user-relay",
		assistant.CreateSessionInput{ClientRequestID: "request-relay"},
	)
	if err != nil {
		t.Fatalf("create session: %v", err)
	}
	publisher := &sessionOutboxPublisherStub{}
	relay, err := sessionmessaging.NewSessionOutboxRelay(
		store,
		publisher,
		time.Second,
		16,
		nil,
	)
	if err != nil {
		t.Fatalf("build session outbox relay: %v", err)
	}
	published, err := relay.FlushOnce(context.Background())
	if err != nil || published != 1 {
		t.Fatalf("flush session outbox: published=%d err=%v", published, err)
	}
	if len(publisher.appended) != 1 {
		t.Fatalf("relay published %#v", publisher.appended)
	}
	message := publisher.appended[0]
	if message.Stream != sessionmessaging.SessionEventStream ||
		durableFieldOf(message, "eventType") != assistant.SessionCreatedEventType ||
		durableFieldOf(message, "aggregateType") != "AssistantSession" ||
		durableFieldOf(message, "aggregateId") != created.SessionID ||
		durableFieldOf(message, "payload") !=
			`{"sessionId":"`+created.SessionID+`"}` {
		t.Fatalf("published event drifted from contracts: %#v", message)
	}
	if publisher.streams[sessionmessaging.SessionEventStream] !=
		sessionmessaging.SessionEventStreamRetention {
		t.Fatalf("declared retention was not applied: %#v", publisher.streams)
	}
	repeated, err := relay.FlushOnce(context.Background())
	if err != nil || repeated != 0 {
		t.Fatalf("published event must not be republished: %d %v", repeated, err)
	}
}

// TestAssistantSessionOutboxRetainsEventWhenPublishFails proves the relay never
// drops a committed aggregate fact when durable transport rejects it.
func TestAssistantSessionOutboxRetainsEventWhenPublishFails(t *testing.T) {
	t.Parallel()
	store := persistence.NewMemorySessionStore()
	service := sessionorchestration.NewAssistantService(
		skillconsenttest.NewMemoryStore(),
		nil,
		sessionorchestration.WithSessionStore(store),
	)
	if _, err := service.CreateSession(
		context.Background(),
		"user-retain",
		assistant.CreateSessionInput{ClientRequestID: "request-retain"},
	); err != nil {
		t.Fatalf("create session: %v", err)
	}
	publisher := &sessionOutboxPublisherStub{
		appendErr: errors.New("durable transport unavailable"),
	}
	relay, err := sessionmessaging.NewSessionOutboxRelay(
		store,
		publisher,
		time.Second,
		16,
		nil,
	)
	if err != nil {
		t.Fatalf("build session outbox relay: %v", err)
	}
	if published, flushErr := relay.FlushOnce(context.Background()); published != 0 ||
		flushErr == nil {
		t.Fatalf("failed publish must surface: published=%d err=%v", published, flushErr)
	}
	pending, err := store.ClaimPendingSessionEvents(
		context.Background(),
		"relay-owner-after-failure",
		time.Minute,
		16,
	)
	if err != nil {
		t.Fatalf("reclaim after failure: %v", err)
	}
	if len(pending) != 1 {
		t.Fatalf("event was lost after publish failure: %#v", pending)
	}
	if err := relay.Healthy(context.Background(), time.Second); err == nil {
		t.Fatal("relay reported healthy after a failed scan")
	}
}

var (
	_ sessionports.SessionOutboxStore        = (*persistence.MemorySessionStore)(nil)
	_ sessionmessaging.SessionEventPublisher = (*sessionOutboxPublisherStub)(nil)
)
