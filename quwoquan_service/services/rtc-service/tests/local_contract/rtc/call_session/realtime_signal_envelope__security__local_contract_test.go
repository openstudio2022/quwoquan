// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-005
package local_contract

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/adapters/inbound/mq"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
)

func TestRealtimeSignalEnvelopeStripsServerRoutingRecipients(t *testing.T) {
	event := callSignalOutboxFixture(t, "call.answered")

	wire, err := application.MarshalRealtimeSignalEnvelope(
		event,
		"call.answered",
	)
	if err != nil {
		t.Fatalf("MarshalRealtimeSignalEnvelope() error = %v", err)
	}

	var envelope map[string]any
	if err := json.Unmarshal(wire, &envelope); err != nil {
		t.Fatalf("decode realtime signal envelope: %v", err)
	}
	if _, leaked := envelope["recipients"]; leaked {
		t.Fatalf("server routing recipients leaked to client signal: %s", wire)
	}
	if len(envelope) != 4 || envelope["type"] != "call.answered" || envelope["eventId"] != "event-1" {
		t.Fatalf("client signal envelope = %#v", envelope)
	}
	payload, ok := envelope["payload"].(map[string]any)
	if !ok || payload["callId"] != "call-1" || payload["userId"] != "persona-1" {
		t.Fatalf("client signal payload = %#v", envelope["payload"])
	}
	if len(payload) != 2 {
		t.Fatalf("call.answered payload leaked fields outside events.yaml: %#v", payload)
	}
}

func TestRealtimeSignalEnvelopeRejectsWireTypeAndCallIdentityDrift(t *testing.T) {
	event := callSignalOutboxFixture(t, "call.answered")
	if _, err := application.MarshalRealtimeSignalEnvelope(event, "call.ended"); err == nil {
		t.Fatal("wire type drift was accepted")
	}

	event.AggregateID = "call-other"
	if _, err := application.MarshalRealtimeSignalEnvelope(event, "call.answered"); err == nil {
		t.Fatal("call identity drift was accepted")
	}
}

func TestRealtimePublisherEmitsOnlyCanonicalClientSignalEnvelope(t *testing.T) {
	transport := &signalCaptureTransport{}
	publisher := mq.NewRealtimePublisher(transport)

	if err := publisher.PublishToPersonas(
		context.Background(),
		[]string{"persona-1"},
		"call.answered",
		callSignalOutboxFixture(t, "call.answered"),
	); err != nil {
		t.Fatalf("PublishToPersonas() error = %v", err)
	}
	if len(transport.ephemeral) != 1 {
		t.Fatalf("ephemeral messages = %d, want 1", len(transport.ephemeral))
	}
	message := transport.ephemeral[0]
	if message.Channel != "rt:rtc:persona:persona-1" {
		t.Fatalf("ephemeral channel = %q", message.Channel)
	}
	var envelope map[string]any
	if err := json.Unmarshal(message.Payload, &envelope); err != nil {
		t.Fatalf("decode published realtime signal: %v", err)
	}
	if _, leaked := envelope["recipients"]; leaked {
		t.Fatalf("publisher leaked server routing recipients: %s", message.Payload)
	}
	if len(envelope) != 4 || envelope["type"] != "call.answered" || envelope["eventId"] != "event-1" {
		t.Fatalf("published signal envelope = %#v", envelope)
	}
}

func callSignalOutboxFixture(
	t *testing.T,
	wireType string,
) application.CallOutboxEvent {
	t.Helper()
	occurredAt := time.Date(2026, 8, 4, 9, 30, 0, 0, time.UTC)
	payload, err := json.Marshal(map[string]any{
		"type":       wireType,
		"callId":     "call-1",
		"actorId":    "persona-1",
		"recipients": []string{"persona-1", "persona-2"},
		"timestamp":  occurredAt,
		"payload": map[string]any{
			"callId":           "call-1",
			"eventId":          "event-1",
			"callType":         "audio",
			"initiatorId":      "persona-1",
			"maxParticipants":  2,
			"userId":           "persona-1",
			"status":           "connecting",
			"participantCount": 2,
			"createdAt":        occurredAt,
		},
	})
	if err != nil {
		t.Fatalf("marshal signal fixture: %v", err)
	}
	return application.CallOutboxEvent{
		EventID:          "event-1",
		EventType:        "CallAnswered",
		AggregateID:      "call-1",
		AggregateVersion: 2,
		Payload:          payload,
		OccurredAt:       occurredAt,
	}
}

type signalCaptureTransport struct {
	ephemeral []runtimemessaging.EphemeralMessage
	durable   []runtimemessaging.DurableMessage
}

func (t *signalCaptureTransport) PublishEphemeral(
	_ context.Context,
	message runtimemessaging.EphemeralMessage,
) error {
	t.ephemeral = append(t.ephemeral, message)
	return nil
}

func (t *signalCaptureTransport) SubscribeEphemeral(
	context.Context,
	...string,
) (runtimemessaging.EphemeralSubscription, error) {
	panic("SubscribeEphemeral must not be called by RTC publisher")
}

func (t *signalCaptureTransport) AppendDurable(
	_ context.Context,
	message runtimemessaging.DurableMessage,
) (string, error) {
	t.durable = append(t.durable, message)
	return "1-0", nil
}
