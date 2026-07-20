package application

import (
	"context"
	"testing"
	"time"

	messageevent "quwoquan_service/services/chat-service/internal/domain/chat/message/event"
	messagemodel "quwoquan_service/services/chat-service/internal/domain/chat/message/model"
)

func TestAppendRtcCallLogCreatesTypedSystemMessage(t *testing.T) {
	messages := &rtcCallLogMessageStoreStub{}
	projection := &rtcCallLogProjectionStub{}
	cache := &rtcCallLogCacheStub{}
	service := &MessageService{
		messages:   messages,
		projection: projection,
		cache:      cache,
	}

	err := service.AppendRtcCallLog(context.Background(), RtcCallEndedFact{
		EventID:        "rtc-event-1",
		CallID:         "call-1",
		CallType:       "video",
		InitiatorID:    "persona-1",
		ConversationID: "conversation-1",
		EndReason:      "normal",
		DurationMs:     65000,
		EndedAt:        time.Date(2026, 7, 19, 1, 2, 3, 0, time.UTC),
	})
	if err != nil {
		t.Fatalf("append rtc call log: %v", err)
	}

	message := messages.commit.Message
	if message.Type != "system_call_log" ||
		message.ClientMessageID != "rtc:rtc-event-1" ||
		message.Card == nil ||
		message.Card.Kind != "rtc_call_log" {
		t.Fatalf("unexpected message: %#v", message)
	}
	if len(messages.commit.Events) != 1 ||
		messages.commit.Events[0].EventType != messageevent.MessageSent {
		t.Fatalf("unexpected outbox: %#v", messages.commit.Events)
	}
	if projection.message.ID != message.ID ||
		cache.conversationID != "conversation-1" {
		t.Fatalf(
			"projection=%#v cache=%q",
			projection.message,
			cache.conversationID,
		)
	}
}

func TestAppendRtcCallLogWithoutConversationIsNoop(t *testing.T) {
	messages := &rtcCallLogMessageStoreStub{}
	service := &MessageService{messages: messages}
	if err := service.AppendRtcCallLog(context.Background(), RtcCallEndedFact{
		EventID: "rtc-event-no-conversation",
		CallID:  "call-2",
	}); err != nil {
		t.Fatalf("append no-conversation call log: %v", err)
	}
	if messages.commit.Message.ID != "" {
		t.Fatalf("unexpected message commit: %#v", messages.commit)
	}
}

type rtcCallLogMessageStoreStub struct {
	commit MessageCommit
}

func (s *rtcCallLogMessageStoreStub) CommitMessage(
	_ context.Context,
	commit MessageCommit,
) (MessageCommitResult, error) {
	s.commit = commit
	return MessageCommitResult{Message: commit.Message, Events: commit.Events}, nil
}

func (*rtcCallLogMessageStoreStub) FindMessageByID(
	context.Context,
	string,
) (*messagemodel.Message, error) {
	return nil, messagemodel.ErrMessageNotFound
}

func (*rtcCallLogMessageStoreStub) ListMessages(
	context.Context,
	string,
	int,
	int64,
	int64,
) ([]messagemodel.Message, error) {
	return nil, nil
}

func (*rtcCallLogMessageStoreStub) CountUnreadMessages(
	context.Context,
	string,
	string,
	int64,
	int64,
) (UnreadMessageCounts, error) {
	return UnreadMessageCounts{}, nil
}

func (*rtcCallLogMessageStoreStub) SetMessageRecalled(
	context.Context,
	string,
) error {
	return nil
}

func (*rtcCallLogMessageStoreStub) AppendMessageOutboxEvent(
	context.Context,
	MessageOutboxEvent,
	string,
	int64,
) error {
	return nil
}

type rtcCallLogProjectionStub struct {
	message messagemodel.Message
}

func (s *rtcCallLogProjectionStub) ProjectCommittedMessage(
	_ context.Context,
	message messagemodel.Message,
) error {
	s.message = message
	return nil
}

type rtcCallLogCacheStub struct {
	conversationID string
}

func (s *rtcCallLogCacheStub) InvalidateConversation(
	_ context.Context,
	conversationID string,
) error {
	s.conversationID = conversationID
	return nil
}
