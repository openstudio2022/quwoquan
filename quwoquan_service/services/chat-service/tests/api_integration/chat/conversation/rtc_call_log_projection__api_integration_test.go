package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

func TestRtcCallEndedProjectsOneSystemCallLogMessage(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	conversation := createConversation(
		t,
		`{"type":"direct","title":"rtc call log","initialMemberIds":["user_test_002"]}`,
	)
	conversationID := conversation["id"].(string)
	fact := application.RtcCallEndedFact{
		EventID:        "rtc-event-integration-1",
		CallID:         "rtc-call-integration-1",
		CallType:       "audio",
		InitiatorID:    "user_test_001",
		ConversationID: conversationID,
		EndReason:      "normal",
		DurationMs:     65000,
		StartedAt:      time.Date(2026, 7, 19, 1, 0, 0, 0, time.UTC),
		EndedAt:        time.Date(2026, 7, 19, 1, 1, 5, 0, time.UTC),
	}
	if err := testMessageService.AppendRtcCallLog(
		context.Background(),
		fact,
	); err != nil {
		t.Fatalf("append rtc call log: %v", err)
	}
	// Redis Stream 至少一次投递重放同一 EventID 时，Message receipt 保证单条。
	if err := testMessageService.AppendRtcCallLog(
		context.Background(),
		fact,
	); err != nil {
		t.Fatalf("replay rtc call log: %v", err)
	}

	messageCount, err := mongoDB.Collection("messages").CountDocuments(
		context.Background(),
		bson.M{"clientMsgId": "rtc:rtc-event-integration-1"},
	)
	if err != nil {
		t.Fatal(err)
	}
	if messageCount != 1 {
		t.Fatalf("system call log count = %d, want 1", messageCount)
	}
	var message struct {
		Type string `bson:"type"`
		Card struct {
			Kind string `bson:"kind"`
		} `bson:"card"`
	}
	if err := mongoDB.Collection("messages").FindOne(
		context.Background(),
		bson.M{"clientMsgId": "rtc:rtc-event-integration-1"},
	).Decode(&message); err != nil {
		t.Fatal(err)
	}
	if message.Type != "system_call_log" || message.Card.Kind != "rtc_call_log" {
		t.Fatalf("unexpected persisted message: %#v", message)
	}
}
