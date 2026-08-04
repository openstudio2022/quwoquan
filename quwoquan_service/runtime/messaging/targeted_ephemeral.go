package runtimemessaging

import (
	"bytes"
	"encoding/json"
	"errors"
	"strings"
)

// EphemeralRoutingTarget is transport-only delivery metadata. It is consumed
// by the trusted gateway subscription and must never be forwarded as part of a
// first-party business event.
type EphemeralRoutingTarget struct {
	PersonaID string `json:"personaId"`
	DeviceID  string `json:"deviceId,omitempty"`
}

type targetedEphemeralEnvelope struct {
	Routing EphemeralRoutingTarget `json:"routing"`
	Event   json.RawMessage        `json:"event"`
}

// WrapTargetedEphemeralPayload binds a canonical business event to one trusted
// persona/device route without adding routing fields to the business wire.
func WrapTargetedEphemeralPayload(
	target EphemeralRoutingTarget,
	event []byte,
) ([]byte, error) {
	target.PersonaID = strings.TrimSpace(target.PersonaID)
	target.DeviceID = strings.TrimSpace(target.DeviceID)
	if target.PersonaID == "" {
		return nil, errors.New("targeted ephemeral personaId is required")
	}
	if !isJSONObject(event) {
		return nil, errors.New("targeted ephemeral event must be a JSON object")
	}
	return json.Marshal(targetedEphemeralEnvelope{
		Routing: target,
		Event:   append(json.RawMessage(nil), event...),
	})
}

// UnwrapTargetedEphemeralPayload removes trusted routing metadata before a
// payload crosses the realtime client boundary. Bare business events return
// targeted=false and are left byte-for-byte unchanged.
func UnwrapTargetedEphemeralPayload(
	payload []byte,
) (
	target EphemeralRoutingTarget,
	event []byte,
	targeted bool,
	err error,
) {
	var top map[string]json.RawMessage
	if err := json.Unmarshal(payload, &top); err != nil {
		return target, nil, false, errors.New("ephemeral payload must be valid JSON")
	}
	if _, exists := top["routing"]; !exists {
		return target, append([]byte(nil), payload...), false, nil
	}
	if len(top) != 2 || top["event"] == nil {
		return target, nil, true, errors.New("targeted ephemeral envelope fields are invalid")
	}
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.DisallowUnknownFields()
	var envelope targetedEphemeralEnvelope
	if err := decoder.Decode(&envelope); err != nil {
		return target, nil, true, errors.New("decode targeted ephemeral envelope")
	}
	envelope.Routing.PersonaID = strings.TrimSpace(envelope.Routing.PersonaID)
	envelope.Routing.DeviceID = strings.TrimSpace(envelope.Routing.DeviceID)
	if envelope.Routing.PersonaID == "" {
		return target, nil, true, errors.New("targeted ephemeral personaId is required")
	}
	if !isJSONObject(envelope.Event) {
		return target, nil, true, errors.New("targeted ephemeral event must be a JSON object")
	}
	return envelope.Routing,
		append([]byte(nil), envelope.Event...),
		true,
		nil
}

func isJSONObject(payload []byte) bool {
	var object map[string]json.RawMessage
	return json.Unmarshal(payload, &object) == nil && object != nil
}
