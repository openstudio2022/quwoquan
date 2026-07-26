package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	learningmessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/messaging"
	learningpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/persistence"
)

type relayStoreStub struct {
	events   []learningpersistence.PendingOutboxEvent
	marked   []string
	released []string
}

func (store *relayStoreStub) ClaimPendingOutbox(
	context.Context,
	string,
	time.Duration,
	int,
) ([]learningpersistence.PendingOutboxEvent, error) {
	return store.events, nil
}

func (store *relayStoreStub) MarkOutboxPublished(
	_ context.Context,
	eventID string,
	_ string,
	publishedRef string,
	_ time.Time,
) error {
	store.marked = append(store.marked, eventID+":"+publishedRef)
	return nil
}

func (store *relayStoreStub) ReleaseOutboxClaim(
	_ context.Context,
	eventID string,
	_ string,
) error {
	store.released = append(store.released, eventID)
	return nil
}

type durablePublisherStub struct {
	messages     []runtimemessaging.DurableMessage
	retained     []time.Duration
	err          error
	retentionErr error
}

func (publisher *durablePublisherStub) AppendDurable(
	_ context.Context,
	message runtimemessaging.DurableMessage,
) (string, error) {
	if publisher.err != nil {
		return "", publisher.err
	}
	publisher.messages = append(publisher.messages, message)
	return "stream-1", nil
}

func (publisher *durablePublisherStub) SetDurableRetention(
	_ context.Context,
	stream string,
	retention time.Duration,
) error {
	if stream != learningmessaging.LearningFactStream {
		return errors.New("unexpected learning fact stream")
	}
	if publisher.retentionErr != nil {
		return publisher.retentionErr
	}
	publisher.retained = append(publisher.retained, retention)
	return nil
}

func TestOutboxRelayMarksOnlyConfirmedPublish(t *testing.T) {
	t.Parallel()
	store := &relayStoreStub{events: []learningpersistence.PendingOutboxEvent{{
		ID:             "feedback:1",
		EventType:      "AssistantLearningFactAppended",
		AppendSequence: 9,
		Payload: learningmodel.RedactedPayload{
			EventID:         "feedback",
			EventVersion:    1,
			AppendSequence:  9,
			FactType:        learningmodel.FactTypeUserFeedback,
			UserID:          "account-1",
			PersonaID:       "persona-1",
			AssistantTurnID: "turn-1",
		},
		OccurredAt: time.Date(2026, 7, 26, 1, 2, 3, 0, time.UTC),
	}}}
	publisher := &durablePublisherStub{}
	relay, err := learningmessaging.NewOutboxRelay(store, publisher, time.Second, 32, nil)
	if err != nil {
		t.Fatalf("NewOutboxRelay() error = %v", err)
	}
	published, err := relay.FlushOnce(context.Background())
	if err != nil {
		t.Fatalf("FlushOnce() error = %v", err)
	}
	if published != 1 || len(publisher.messages) != 1 {
		t.Fatalf("published/messages = %d/%d, want 1/1", published, len(publisher.messages))
	}
	if len(store.marked) != 1 || store.marked[0] != "feedback:1:stream-1" {
		t.Fatalf("marked = %v", store.marked)
	}
	if publisher.messages[0].Stream != learningmessaging.LearningFactStream {
		t.Fatalf("stream = %q", publisher.messages[0].Stream)
	}
	if len(publisher.retained) != 1 ||
		publisher.retained[0] != learningmessaging.LearningFactStreamRetention {
		t.Fatalf("retention = %v", publisher.retained)
	}
	fields := make(map[string]string, len(publisher.messages[0].Fields))
	for _, field := range publisher.messages[0].Fields {
		fields[field.Name] = field.Value
	}
	if fields["eventType"] != "AssistantLearningFactAppended" ||
		fields["aggregateType"] != "AssistantLearningFact" ||
		fields["aggregateId"] != "feedback" ||
		fields["aggregateVersion"] != "1" {
		t.Fatalf("canonical event fields = %#v", fields)
	}
}

func TestOutboxRelayRetainsPendingEventWhenPublishFails(t *testing.T) {
	t.Parallel()
	store := &relayStoreStub{events: []learningpersistence.PendingOutboxEvent{{
		ID:             "feedback:1",
		EventType:      "AssistantLearningFactAppended",
		AppendSequence: 9,
	}}}
	publisher := &durablePublisherStub{err: errors.New("transport unavailable")}
	relay, err := learningmessaging.NewOutboxRelay(store, publisher, time.Second, 32, nil)
	if err != nil {
		t.Fatalf("NewOutboxRelay() error = %v", err)
	}
	published, err := relay.FlushOnce(context.Background())
	if err == nil {
		t.Fatal("FlushOnce() error = nil, want transport failure")
	}
	if published != 0 || len(store.marked) != 0 {
		t.Fatalf("published/marked = %d/%d, want 0/0", published, len(store.marked))
	}
	if len(store.released) != 1 || store.released[0] != "feedback:1" {
		t.Fatalf("released = %v, want failed claim released", store.released)
	}
}

func TestOutboxRelayRetainsPendingEventWhenRetentionFails(t *testing.T) {
	t.Parallel()
	store := &relayStoreStub{events: []learningpersistence.PendingOutboxEvent{{
		ID:             "feedback:1",
		EventType:      "AssistantLearningFactAppended",
		AppendSequence: 9,
	}}}
	publisher := &durablePublisherStub{
		retentionErr: errors.New("retention unavailable"),
	}
	relay, err := learningmessaging.NewOutboxRelay(store, publisher, time.Second, 32, nil)
	if err != nil {
		t.Fatalf("NewOutboxRelay() error = %v", err)
	}
	published, err := relay.FlushOnce(context.Background())
	if err == nil {
		t.Fatal("FlushOnce() error = nil, want retention failure")
	}
	if published != 0 || len(store.marked) != 0 {
		t.Fatalf("published/marked = %d/%d, want 0/0", published, len(store.marked))
	}
	if len(store.released) != 1 || store.released[0] != "feedback:1" {
		t.Fatalf("released = %v, want claim released", store.released)
	}
}

func TestOutboxRelayHealthFollowsObservedScans(t *testing.T) {
	t.Parallel()
	relay, err := learningmessaging.NewOutboxRelay(
		&relayStoreStub{},
		&durablePublisherStub{},
		time.Second,
		32,
		nil,
	)
	if err != nil {
		t.Fatalf("NewOutboxRelay() error = %v", err)
	}
	if err := relay.Healthy(context.Background(), time.Second); err == nil {
		t.Fatal("relay must remain unready before its first scan")
	}
	relay.FlushAndObserve(context.Background())
	if err := relay.Healthy(context.Background(), time.Second); err != nil {
		t.Fatalf("relay health after successful scan: %v", err)
	}
}
