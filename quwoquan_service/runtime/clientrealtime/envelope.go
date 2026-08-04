package clientrealtime

import (
	"encoding/json"
	"errors"
	"strings"
	"time"
)

// ClientRealtimeEventEnvelope is the one first-party business wire shared by
// WebSocket and LongPoll. Routing coordinates stay in transport-only wrappers;
// payload fields remain owned by the catalog event's object-local contract.
//
// This package is intentionally redis/recommendation/messaging-free so producers
// in those packages can share one wire ABI without import cycles.
type ClientRealtimeEventEnvelope struct {
	Type       string          `json:"type"`
	EventID    string          `json:"eventId,omitempty"`
	OccurredAt string          `json:"occurredAt"`
	Payload    json.RawMessage `json:"payload"`
}

// MarshalClientRealtimeEventEnvelope rejects incomplete/non-object payloads so
// a producer cannot create an opaque alternate client decoder path.
func MarshalClientRealtimeEventEnvelope(
	wireType string,
	eventID string,
	occurredAt time.Time,
	payload any,
) ([]byte, error) {
	wireType = strings.TrimSpace(wireType)
	eventID = strings.TrimSpace(eventID)
	if wireType == "" {
		return nil, errors.New("client realtime event type is required")
	}
	if occurredAt.IsZero() {
		return nil, errors.New("client realtime occurredAt is required")
	}
	encodedPayload, err := json.Marshal(payload)
	if err != nil || !isJSONObject(encodedPayload) {
		return nil, errors.New("client realtime payload must be a JSON object")
	}
	return json.Marshal(ClientRealtimeEventEnvelope{
		Type:       wireType,
		EventID:    eventID,
		OccurredAt: occurredAt.UTC().Format(time.RFC3339Nano),
		Payload:    encodedPayload,
	})
}

func isJSONObject(payload []byte) bool {
	trimmed := strings.TrimSpace(string(payload))
	return strings.HasPrefix(trimmed, "{") && strings.HasSuffix(trimmed, "}")
}
