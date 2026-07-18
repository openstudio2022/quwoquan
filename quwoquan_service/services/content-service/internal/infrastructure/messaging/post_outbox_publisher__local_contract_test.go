package messaging

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
)

type postOutboxEventSpy struct {
	events []runtimemessaging.DomainEvent
}

func (s *postOutboxEventSpy) Publish(
	_ context.Context,
	event runtimemessaging.DomainEvent,
) error {
	s.events = append(s.events, event)
	return nil
}

func TestPostOutboxPublisherPreservesDurableEventIdentity(t *testing.T) {
	t.Parallel()

	payload, err := json.Marshal(map[string]any{"postId": "post-1"})
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	spy := &postOutboxEventSpy{}
	publisher := NewPostOutboxPublisher(spy)

	if err := publisher.Publish(context.Background(), postports.OutboxEvent{
		EventID:       "event-1",
		EventType:     "PostPublished",
		AggregateType: "Post",
		AggregateID:   "post-1",
		Payload:       payload,
		OccurredAt:    time.Date(2026, 7, 13, 10, 0, 0, 0, time.UTC),
	}); err != nil {
		t.Fatalf("Publish() error = %v", err)
	}

	if len(spy.events) != 1 {
		t.Fatalf("published events = %d, want 1", len(spy.events))
	}
	event := spy.events[0]
	if event.EventID != "event-1" || event.AggregateID != "post-1" {
		t.Fatalf("event identity = %#v", event)
	}
}
