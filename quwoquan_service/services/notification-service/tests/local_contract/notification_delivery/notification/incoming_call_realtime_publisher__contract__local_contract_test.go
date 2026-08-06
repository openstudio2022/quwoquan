// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-005
package local_contract

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	notificationrealtime "quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/realtime"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
)

func TestIncomingCallPublisherUsesCanonicalRTCEnvelopeAndTransportOnlyDeviceRoute(t *testing.T) {
	transport := &incomingCallRealtimeCapture{}
	publisher, err := notificationrealtime.NewIncomingCallPublisher(transport)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 8, 4, 10, 0, 0, 0, time.UTC)
	deliveryKey := canonicalFixtureDigest("call-1", "persona-1")
	job := notification.IncomingCallDeliveryJob{
		EventID:         "event-ring",
		CallID:          "call-1",
		TargetPersonaID: "persona-1",
		DeviceID:        "device-1",
		DeliveryKey:     deliveryKey,
		CallType:        "audio",
		CallerName:      "来电用户",
		CallerAvatarURL: "https://cdn.example/avatar.jpg",
		SourceLabel:     "私信通话",
		TrustRelation:   "known",
		ExpiresAt:       now.Add(30 * time.Second),
		CreatedAt:       now,
	}
	if err := publisher.DispatchIncomingCall(context.Background(), job); err != nil {
		t.Fatalf("DispatchIncomingCall() error = %v", err)
	}
	if len(transport.ephemeral) != 1 {
		t.Fatalf("ephemeral messages = %d, want 1", len(transport.ephemeral))
	}
	target, event, targeted, err := runtimemessaging.UnwrapTargetedEphemeralPayload(
		transport.ephemeral[0].Payload,
	)
	if err != nil {
		t.Fatalf("unwrap targeted signal: %v", err)
	}
	if !targeted || target.PersonaID != "persona-1" || target.DeviceID != "device-1" {
		t.Fatalf("routing target = %+v, targeted=%v", target, targeted)
	}
	var envelope map[string]any
	if err := json.Unmarshal(event, &envelope); err != nil {
		t.Fatalf("decode RTC client envelope: %v", err)
	}
	if len(envelope) != 4 || envelope["type"] != "call.ringing" || envelope["eventId"] != "event-ring" {
		t.Fatalf("RTC signal envelope = %#v", envelope)
	}
	if envelope["deviceId"] != nil || envelope["routing"] != nil {
		t.Fatalf("routing metadata leaked to client event: %s", event)
	}
	payload, ok := envelope["payload"].(map[string]any)
	if !ok || payload["targetPersonaId"] != "persona-1" || payload["deliveryKey"] != deliveryKey {
		t.Fatalf("ringing payload = %#v", envelope["payload"])
	}
}

func TestIncomingCallCancellationUsesExistingCanonicalRTCWireType(t *testing.T) {
	transport := &incomingCallRealtimeCapture{}
	publisher, err := notificationrealtime.NewIncomingCallPublisher(transport)
	if err != nil {
		t.Fatal(err)
	}
	event := notification.IncomingCallCancellationEvent{
		EventID:    "event-answer",
		EventType:  "CallAnswered",
		CallID:     "call-1",
		ActorID:    "persona-1",
		OccurredAt: time.Date(2026, 8, 4, 10, 0, 1, 0, time.UTC),
	}
	if err := publisher.DispatchCancellation(context.Background(), "persona-1", event); err != nil {
		t.Fatalf("DispatchCancellation() error = %v", err)
	}
	var envelope map[string]any
	if err := json.Unmarshal(transport.ephemeral[0].Payload, &envelope); err != nil {
		t.Fatalf("decode cancellation signal: %v", err)
	}
	if len(envelope) != 4 || envelope["type"] != "call.answered" || envelope["eventId"] != "event-answer" {
		t.Fatalf("cancellation signal = %#v", envelope)
	}
	payload, ok := envelope["payload"].(map[string]any)
	if !ok || payload["callId"] != "call-1" || payload["userId"] != "persona-1" {
		t.Fatalf("cancellation payload = %#v", envelope["payload"])
	}
}

type incomingCallRealtimeCapture struct {
	ephemeral []runtimemessaging.EphemeralMessage
}

func (t *incomingCallRealtimeCapture) PublishEphemeral(
	_ context.Context,
	message runtimemessaging.EphemeralMessage,
) error {
	t.ephemeral = append(t.ephemeral, message)
	return nil
}

func (*incomingCallRealtimeCapture) SubscribeEphemeral(
	context.Context,
	...string,
) (runtimemessaging.EphemeralSubscription, error) {
	panic("SubscribeEphemeral must not be called by incoming call publisher")
}

func (*incomingCallRealtimeCapture) AppendDurable(
	context.Context,
	runtimemessaging.DurableMessage,
) (string, error) {
	panic("AppendDurable must not be called by incoming call publisher")
}
