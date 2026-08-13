package streaming

import (
	"encoding/json"
	"testing"
	"time"

	"quwoquan_service/runtime/failures"
)

func TestEnvelopeRoundTrip(t *testing.T) {
	envelope, err := NewEnvelope("assistant.partial", 7, map[string]string{"text": "hello"})
	if err != nil {
		t.Fatalf("NewEnvelope() error = %v", err)
	}
	envelope.ID = "evt_1"
	envelope.StreamID = "turn-stream-1"
	envelope.ResumeToken = NewResumeToken(envelope.StreamID, envelope.Seq)

	payload, err := json.Marshal(envelope)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}
	var decoded Envelope
	if err := json.Unmarshal(payload, &decoded); err != nil {
		t.Fatalf("Unmarshal() error = %v", err)
	}
	var data map[string]string
	if err := decoded.DecodeData(&data); err != nil {
		t.Fatalf("DecodeData() error = %v", err)
	}
	if data["text"] != "hello" {
		t.Fatalf("decoded data = %#v", data)
	}
	streamID, seq, err := ParseResumeToken(decoded.ResumeToken)
	if err != nil {
		t.Fatalf("ParseResumeToken() error = %v", err)
	}
	if streamID != "turn-stream-1" || seq != 7 {
		t.Fatalf("resume token = (%q, %d)", streamID, seq)
	}
}

func TestEnvelopeSSEEventUsesResumeToken(t *testing.T) {
	envelope, err := NewEnvelope("assistant.final", 2, map[string]bool{"done": true})
	if err != nil {
		t.Fatalf("NewEnvelope() error = %v", err)
	}
	envelope.ID = "event-id"
	envelope.ResumeToken = "resume-token"

	event := envelope.SSEEvent()
	if event.ID != "resume-token" {
		t.Fatalf("SSEEvent ID = %q", event.ID)
	}
	if event.Event != "assistant.final" {
		t.Fatalf("SSEEvent Event = %q", event.Event)
	}
}

func TestEnvelopeNormalizesRuntimeFailureAndCreatedAt(t *testing.T) {
	createdAt := time.Date(2026, 4, 29, 2, 0, 0, 0, time.FixedZone("CST", 8*60*60))
	failure := failures.Failure{}
	envelope := Envelope{
		StreamID:       "turn_1",
		Event:          "assistant.failure",
		Seq:            7,
		RuntimeFailure: &failure,
		CreatedAt:      createdAt,
	}.Normalized()

	if envelope.ResumeToken == "" {
		t.Fatal("ResumeToken is empty")
	}
	if envelope.CreatedAt.Location() != time.UTC {
		t.Fatalf("CreatedAt location = %s, want UTC", envelope.CreatedAt.Location())
	}
	if envelope.RuntimeFailure == nil || envelope.RuntimeFailure.Code == "" {
		t.Fatalf("RuntimeFailure was not normalized: %#v", envelope.RuntimeFailure)
	}
}

func TestEnvelopeSupportsTopicAndEventType(t *testing.T) {
	createdAt := time.Date(2026, 4, 29, 2, 0, 0, 0, time.UTC)
	envelope := Envelope{
		EventID:   "evt_1",
		Topic:     "user:user_1",
		Seq:       7,
		EventType: "app_message.created",
		Payload:   map[string]any{"messageId": "msg_1"},
		CreatedAt: createdAt,
	}
	event := envelope.SSEEvent()
	if event.ID != "evt_1" {
		t.Fatalf("ID = %q, want evt_1", event.ID)
	}
	if event.Event != "app_message.created" {
		t.Fatalf("Event = %q", event.Event)
	}
}

func TestFakeTransportListAfterSeq(t *testing.T) {
	transport := NewFakeTransport()
	transport.Publish("user:user_1", Envelope{EventID: "evt_1", Seq: 1, EventType: "created"})
	transport.Publish("user:user_1", Envelope{EventID: "evt_2", Seq: 2, EventType: "read"})
	got := transport.List("user:user_1", 1)
	if len(got) != 1 {
		t.Fatalf("len = %d, want 1", len(got))
	}
	if got[0].EventID != "evt_2" {
		t.Fatalf("EventID = %q, want evt_2", got[0].EventID)
	}
}

func TestInvalidResumeToken(t *testing.T) {
	if _, _, err := ParseResumeToken("not base64"); err == nil {
		t.Fatal("ParseResumeToken() error = nil")
	}
}
