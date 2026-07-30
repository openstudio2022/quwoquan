// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-006
package local_contract

import (
	"encoding/json"
	"testing"

	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
)

func TestCallEventPayloadKeepsRoutingRecipientsOffTheWire(t *testing.T) {
	payload := application.CallEventPayload{
		CallID:    "call-1",
		Status:    "ringing",
		CreatedAt: "2026-07-29T12:00:00Z",
		InviteeIDs: []string{
			"persona-2",
			"persona-3",
		},
	}

	encoded, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal CallEventPayload: %v", err)
	}

	var wire map[string]any
	if err := json.Unmarshal(encoded, &wire); err != nil {
		t.Fatalf("decode CallEventPayload wire: %v", err)
	}
	if _, leaked := wire["inviteeIds"]; leaked {
		t.Fatalf("routing-only inviteeIds leaked into event payload: %s", encoded)
	}
	if wire["createdAt"] != payload.CreatedAt {
		t.Fatalf("createdAt = %v, want %q", wire["createdAt"], payload.CreatedAt)
	}
}
