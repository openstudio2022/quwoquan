package application

import (
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/domain/event"
)

// signalWireType maps a domain event constant (event.go) to its client WS wire
// type as declared by `client_ws_type` in services/rtc-service/contracts/rtc/call_session/events.yaml.
//
// events.yaml is the single source of truth for the wire protocol. Go codegen
// currently emits these constants only for the Dart client; this thin map keeps
// the rtc-service WS push aligned with the client decoder (parseRtcWsPayload),
// which switches on values like "call.ringing". Keep this table in lockstep with
// events.yaml `client_ws_type`; the ws_event_wire_type_contract_test asserts it.
var signalWireTypeByDomainEvent = map[string]string{
	event.CallInitiated:      "call.initiated",
	event.CallRinging:        "call.ringing",
	event.CallAnswered:       "call.answered",
	event.CallConnected:      "call.connected",
	event.CallEnded:          "call.ended",
	event.ParticipantJoined:  "participant.joined",
	event.ParticipantLeft:    "participant.left",
	event.ScreenShareStarted: "screen_share.started",
	event.ScreenShareStopped: "screen_share.stopped",
}

// signalWireType returns the client wire type for a domain event, falling back
// to the domain constant when no mapping exists (defensive; unknown types are
// surfaced as RtcWsUnknownPayload on the client rather than crashing).
func signalWireType(domainEvent string) string {
	if wire, ok := signalWireTypeByDomainEvent[domainEvent]; ok {
		return wire
	}
	return domainEvent
}
