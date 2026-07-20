package mq

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

	fact, err := decodeRtcCallEndedFact(map[string]string{
		"eventId":     "event-1",
		"payloadJson": string(payload),
	})
	if err != nil {
		t.Fatalf("decode CallEnded: %v", err)
	}
	if fact.EventID != "event-1" ||
		fact.CallID != "call-1" ||
		fact.ConversationID != "conversation-1" ||
		fact.DurationMs != 3210 ||
		fact.EndReason != "normal" {
		t.Fatalf("unexpected fact: %#v", fact)
	}
}

func TestDecodeRtcCallEndedFactRejectsMissingIdentity(t *testing.T) {
	if _, err := decodeRtcCallEndedFact(map[string]string{
		"payloadJson": `{"callId":"","payload":{}}`,
	}); err == nil {
		t.Fatal("expected missing eventId/callId rejection")
	}
}
