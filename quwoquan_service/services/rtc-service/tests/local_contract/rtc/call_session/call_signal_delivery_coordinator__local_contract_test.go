// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-005
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-005.t5
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-005.t4
// readiness_case: deliver-realtime-call-signals-local
package local_contract

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
)

type signalDeliveryStore struct {
	events     []application.CallOutboxEvent
	checkpoint string
}

func (store *signalDeliveryStore) ReadPendingOutbox(
	context.Context,
	int,
) ([]application.CallOutboxEvent, error) {
	if store.checkpoint != "" {
		return nil, nil
	}
	return append([]application.CallOutboxEvent(nil), store.events...), nil
}

func (store *signalDeliveryStore) MarkOutboxPublished(
	_ context.Context,
	eventID string,
	publishedAt time.Time,
) error {
	if !publishedAt.IsZero() {
		store.checkpoint = eventID
	}
	return nil
}

type signalDeliveryPublisher struct {
	eventID    string
	wireType   string
	recipients []string
}

func (publisher *signalDeliveryPublisher) PublishToPersonas(
	_ context.Context,
	recipients []string,
	wireType string,
	event application.CallOutboxEvent,
) error {
	publisher.eventID = event.EventID
	publisher.wireType = wireType
	publisher.recipients = append([]string(nil), recipients...)
	return nil
}

func TestCallSignalDeliveryCoordinatorPublishesBeforeCheckpointing(t *testing.T) {
	payload, err := json.Marshal(map[string]any{
		"type":       "call.initiated",
		"callId":     "call-1",
		"recipients": []string{"persona-1", "persona-2"},
		"payload":    map[string]any{"callId": "call-1"},
	})
	if err != nil {
		t.Fatal(err)
	}
	store := &signalDeliveryStore{events: []application.CallOutboxEvent{{
		EventID: "event-1", EventType: "CallInitiated", AggregateID: "call-1",
		AggregateVersion: 1, Payload: payload, OccurredAt: time.Now().UTC(),
	}}}
	publisher := &signalDeliveryPublisher{}
	coordinator := application.NewCallSignalDeliveryRelay(store, publisher)

	processed, err := coordinator.Deliver(t.Context(), 10)
	if err != nil || processed != 1 {
		t.Fatalf("Deliver() processed=%d err=%v", processed, err)
	}
	if publisher.eventID != "event-1" || publisher.wireType != "call.initiated" ||
		len(publisher.recipients) != 2 || store.checkpoint != "event-1" {
		t.Fatalf(
			"delivery event=%q wire=%q recipients=%v checkpoint=%q",
			publisher.eventID,
			publisher.wireType,
			publisher.recipients,
			store.checkpoint,
		)
	}
	processed, err = coordinator.Deliver(t.Context(), 10)
	if err != nil || processed != 0 {
		t.Fatalf("checkpoint replay processed=%d err=%v", processed, err)
	}
}
