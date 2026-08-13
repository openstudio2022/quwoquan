// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-002
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-002.t2
// readiness_case: append-rtc-call-log-api
package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	conversationapp "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	conversationpersistence "quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/persistence"
	messageapp "quwoquan_service/services/chat-service/internal/chat/message/application"
	messageports "quwoquan_service/services/chat-service/internal/chat/message/domain/ports"
)

type rtcCallLogAPIBackend struct {
	writer interface {
		AppendRtcCallLog(context.Context, conversationapp.RtcCallEndedFact) error
	}
}

func (backend rtcCallLogAPIBackend) ProjectRtcCallLog(
	ctx context.Context,
	fact messageapp.RtcCallEndedFact,
) error {
	return backend.writer.AppendRtcCallLog(ctx, conversationapp.RtcCallEndedFact{
		EventID: fact.EventID, CallID: fact.CallID, CallType: fact.CallType,
		InitiatorID: fact.InitiatorID, ConversationID: fact.ConversationID,
		EndReason: fact.EndReason, DurationMs: fact.DurationMs,
		StartedAt: fact.StartedAt, EndedAt: fact.EndedAt,
	})
}

func TestRtcCallEndedConsumerCommitsOneMessageAndOutboxInRealMongo(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "chat_message_rtc_call_log_api_integration")
	if err != nil {
		t.Fatalf("start real MongoDB replica set: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := runtime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	store := conversationpersistence.NewMongoChatStore(runtime.Database)
	if err := store.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure Chat message indexes: %v", err)
	}
	conversationID := "conversation-api-1"
	if err := store.CreateConversation(startupCtx, &conversationmodel.Conversation{
		ID: conversationID, Type: "direct", CreatorId: "persona-api-1",
		Status:    conversationmodel.ConversationStatusActive,
		CreatedAt: time.Date(2026, 8, 5, 9, 0, 0, 0, time.UTC),
		UpdatedAt: time.Date(2026, 8, 5, 9, 0, 0, 0, time.UTC),
	}); err != nil {
		t.Fatalf("create target conversation: %v", err)
	}
	service := conversationapp.NewMessageService(
		conversationapp.ChatStoragePorts{Messages: store, MessageProjection: store},
		rtcCallLogAPICache{},
		rtcCallLogAPIPublisher{},
		nil,
		rtcCallLogAPIMediaReader{},
	)
	handler := messageapp.NewRtcCallLogHandler(rtcCallLogAPIBackend{writer: service})
	fact := messageapp.RtcCallEndedFact{
		EventID: "call-ended-api-1", CallID: "call-api-1", CallType: "audio",
		InitiatorID: "persona-api-1", ConversationID: conversationID,
		EndReason: "normal", DurationMs: 42_000,
		EndedAt: time.Date(2026, 8, 5, 9, 30, 0, 0, time.UTC),
	}
	for attempt := 0; attempt < 2; attempt++ {
		if err := handler.AppendRtcCallLog(startupCtx, fact); err != nil {
			t.Fatalf("AppendRtcCallLog() attempt %d error = %v", attempt+1, err)
		}
	}

	var message struct {
		ID              string `bson:"_id"`
		Type            string `bson:"type"`
		ClientMessageID string `bson:"clientMsgId"`
	}
	if err := runtime.Database.Collection("messages").FindOne(
		startupCtx,
		bson.M{"clientMsgId": "rtc:" + fact.EventID},
	).Decode(&message); err != nil {
		t.Fatalf("read committed call-log message: %v", err)
	}
	if message.ID == "" || message.Type != "system_call_log" ||
		message.ClientMessageID != "rtc:"+fact.EventID {
		t.Fatalf("committed call-log message drifted: %+v", message)
	}
	assertRtcCallLogMongoCount(t, runtime, "messages", bson.M{"clientMsgId": "rtc:" + fact.EventID}, 1)
	assertRtcCallLogMongoCount(t, runtime, "messages_outbox", bson.M{"aggregateId": message.ID}, 1)
}

func assertRtcCallLogMongoCount(
	t *testing.T,
	runtime *testinfra.RealMongo,
	collection string,
	filter bson.M,
	want int64,
) {
	t.Helper()
	count, err := runtime.Database.Collection(collection).CountDocuments(t.Context(), filter)
	if err != nil || count != want {
		t.Fatalf("%s count=%d want=%d err=%v", collection, count, want, err)
	}
}

type rtcCallLogAPICache struct{}

func (rtcCallLogAPICache) InvalidateConversation(context.Context, string) error { return nil }

type rtcCallLogAPIPublisher struct{}

func (rtcCallLogAPIPublisher) PublishDomainEvent(context.Context, string, string, string, map[string]any) error {
	return nil
}

func (rtcCallLogAPIPublisher) PublishRecordedDomainEvent(context.Context, string, string, string, string, map[string]any) error {
	return nil
}

type rtcCallLogAPIMediaReader struct{}

func (rtcCallLogAPIMediaReader) ReadOwnedReadyAsset(
	context.Context,
	string,
	string,
) (messageports.MediaAssetDeliverySlice, bool, error) {
	return messageports.MediaAssetDeliverySlice{}, false, nil
}
