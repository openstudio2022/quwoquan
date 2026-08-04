package runtimemessaging

import (
	"bytes"
	"testing"
)

func TestTargetedEphemeralRoutingIsStrippedFromCanonicalEvent(t *testing.T) {
	event := []byte(`{"type":"call.ringing","callId":"call-1","payload":{"callId":"call-1"}}`)
	wire, err := WrapTargetedEphemeralPayload(
		EphemeralRoutingTarget{PersonaID: " persona-1 ", DeviceID: " device-1 "},
		event,
	)
	if err != nil {
		t.Fatalf("WrapTargetedEphemeralPayload() error = %v", err)
	}

	target, unwrapped, targeted, err := UnwrapTargetedEphemeralPayload(wire)
	if err != nil {
		t.Fatalf("UnwrapTargetedEphemeralPayload() error = %v", err)
	}
	if !targeted || target.PersonaID != "persona-1" || target.DeviceID != "device-1" {
		t.Fatalf("routing target = %+v, targeted=%v", target, targeted)
	}
	if !bytes.Equal(unwrapped, event) {
		t.Fatalf("business event changed: got %s want %s", unwrapped, event)
	}
}

func TestTargetedEphemeralEnvelopeRejectsUnknownOrMissingRoutingFields(t *testing.T) {
	invalid := [][]byte{
		[]byte(`{"routing":{"personaId":"persona-1"},"event":{},"deviceId":"leak"}`),
		[]byte(`{"routing":{"deviceId":"device-1"},"event":{}}`),
		[]byte(`{"routing":{"personaId":"persona-1","accountId":"acct-1"},"event":{}}`),
	}
	for _, wire := range invalid {
		if _, _, _, err := UnwrapTargetedEphemeralPayload(wire); err == nil {
			t.Fatalf("invalid targeted envelope accepted: %s", wire)
		}
	}
}
