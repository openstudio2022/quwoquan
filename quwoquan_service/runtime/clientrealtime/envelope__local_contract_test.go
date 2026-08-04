package clientrealtime

import (
	"encoding/json"
	"testing"
	"time"
)

func TestMarshalClientRealtimeEventEnvelopeProducesSingleStrictShape(t *testing.T) {
	occurredAt := time.Date(2026, 8, 4, 12, 30, 0, 0, time.FixedZone("CST", 8*60*60))
	body, err := MarshalClientRealtimeEventEnvelope(
		"MessageSent", "evt-1", occurredAt, map[string]any{"messageId": "msg-1"},
	)
	if err != nil {
		t.Fatal(err)
	}
	var wire map[string]json.RawMessage
	if err := json.Unmarshal(body, &wire); err != nil {
		t.Fatal(err)
	}
	if len(wire) != 4 || wire["type"] == nil || wire["eventId"] == nil || wire["occurredAt"] == nil || wire["payload"] == nil {
		t.Fatalf("unexpected realtime envelope fields: %s", body)
	}
	if string(wire["occurredAt"]) != `"2026-08-04T04:30:00Z"` {
		t.Fatalf("occurredAt=%s", wire["occurredAt"])
	}
}

func TestMarshalClientRealtimeEventEnvelopeRejectsOpaquePayload(t *testing.T) {
	if _, err := MarshalClientRealtimeEventEnvelope("sync_hint", "", time.Now(), []string{"opaque"}); err == nil {
		t.Fatal("expected non-object payload rejection")
	}
}
