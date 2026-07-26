package local_contract

import (
	"encoding/json"
	"testing"
)

func TestDecodeRtcCallEndedFactPreservesCallLogFields(t *testing.T) {
	payload, err := json.Marshal(map[string]any{
		"type":    "call.ended",
		"callId":  "call-1",
		"actorId": "persona-1",
		"payload": map[string]any{
			"callType":       "audio",
			"initiatorId":    "persona-1",
			"conversationId": "conversation-1",
			"endReason":      "normal",
			"durationMs":     3210,
			"startedAt":      "2026-07-19T00:00:00Z",
			"endedAt":        "2026-07-19T00:00:03.210Z",
		},
	})
	if err != nil {
		t.Fatal(err)
	}

	var decoded struct {
		CallID  string `json:"callId"`
		Payload struct {
			ConversationID string `json:"conversationId"`
			DurationMs     int64  `json:"durationMs"`
			EndReason      string `json:"endReason"`
		} `json:"payload"`
	}
	err = json.Unmarshal(payload, &decoded)
	if err != nil {
		t.Fatalf("decode CallEnded: %v", err)
	}
	if decoded.CallID != "call-1" ||
		decoded.Payload.ConversationID != "conversation-1" ||
		decoded.Payload.DurationMs != 3210 ||
		decoded.Payload.EndReason != "normal" {
		t.Fatalf("unexpected RTC event payload: %#v", decoded)
	}
}

func TestRtcCallEndedEventRequiresIdentity(t *testing.T) {
	var decoded struct {
		CallID string `json:"callId"`
	}
	if err := json.Unmarshal([]byte(`{"callId":"","payload":{}}`), &decoded); err != nil {
		t.Fatalf("decode RTC event: %v", err)
	}
	if decoded.CallID != "" {
		t.Fatalf("expected missing call identity, got %q", decoded.CallID)
	}
}
