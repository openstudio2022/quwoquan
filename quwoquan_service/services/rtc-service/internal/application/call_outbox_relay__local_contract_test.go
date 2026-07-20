package application

import (
	"context"
	"encoding/json"
	"testing"
	"time"
)

func TestCallOutboxRelayPublishesThenMarksDispatched(t *testing.T) {
	payload, err := json.Marshal(callEventBody{
		Type:       "call.ended",
		CallID:     "call-1",
		Recipients: []string{"persona-a", "persona-b"},
	})
	if err != nil {
		t.Fatal(err)
	}
	store := &callOutboxStoreStub{
		pending: []CallOutboxEvent{{
			EventID:     "event-1",
			EventType:   "CallEnded",
			AggregateID: "call-1",
			Payload:     payload,
			OccurredAt:  time.Now().UTC(),
		}},
	}
	publisher := &callPublisherStub{}
	relay := NewCallOutboxRelay(store, publisher)

	count, err := relay.Drain(context.Background(), 10)
	if err != nil {
		t.Fatalf("drain outbox: %v", err)
	}
	if count != 1 {
		t.Fatalf("drain count = %d, want 1", count)
	}
	if len(publisher.recipients) != 2 ||
		publisher.recipients[0] != "persona-a" ||
		publisher.wireType != "call.ended" {
		t.Fatalf(
			"published recipients=%v wire=%s",
			publisher.recipients,
			publisher.wireType,
		)
	}
	if store.marked != "event-1" {
		t.Fatalf("marked event = %q, want event-1", store.marked)
	}
}

func TestCallOutboxRelayDoesNotMarkFailedPublish(t *testing.T) {
	store := &callOutboxStoreStub{
		pending: []CallOutboxEvent{{EventID: "event-failed", Payload: []byte(`{}`)}},
	}
	publisher := &callPublisherStub{fail: true}

	if _, err := NewCallOutboxRelay(store, publisher).Drain(
		context.Background(),
		10,
	); err == nil {
		t.Fatal("expected failed publish")
	}
	if store.marked != "" {
		t.Fatalf("failed publish must not mark outbox, got %q", store.marked)
	}
}

type callOutboxStoreStub struct {
	pending []CallOutboxEvent
	marked  string
}

func (s *callOutboxStoreStub) ReadPendingOutbox(
	context.Context,
	int,
) ([]CallOutboxEvent, error) {
	return s.pending, nil
}

func (s *callOutboxStoreStub) MarkOutboxPublished(
	_ context.Context,
	eventID string,
	_ time.Time,
) error {
	s.marked = eventID
	return nil
}

type callPublisherStub struct {
	recipients []string
	wireType   string
	fail       bool
}

func (p *callPublisherStub) PublishToPersonas(
	_ context.Context,
	personaIDs []string,
	wireType string,
	_ CallOutboxEvent,
) error {
	if p.fail {
		return context.DeadlineExceeded
	}
	p.recipients = append([]string(nil), personaIDs...)
	p.wireType = wireType
	return nil
}
