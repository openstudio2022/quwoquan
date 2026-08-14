// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-002
// readiness_case: append-rtc-call-log-local
package local_contract

import (
	"context"
	"testing"
	"time"

	messageevent "quwoquan_service/services/chat-service/generated/chat/message/contract/event"
	conversationapp "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	messageapp "quwoquan_service/services/chat-service/internal/chat/message/application"
	messagemodel "quwoquan_service/services/chat-service/internal/chat/message/domain/model"
	messageports "quwoquan_service/services/chat-service/internal/chat/message/domain/ports"
)

type rtcCallLogTargetBackend struct {
	writer interface {
		AppendRtcCallLog(context.Context, conversationapp.RtcCallEndedFact) error
	}
}

func (backend rtcCallLogTargetBackend) ProjectRtcCallLog(
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

func TestRtcCallEndedConsumerAppendsOneTypedCallLogAndOutbox(t *testing.T) {
	messages := &rtcCallLogStore{}
	projection := &rtcCallLogProjection{}
	cache := &rtcCallLogCache{}
	service := conversationapp.NewMessageService(
		conversationapp.ChatStoragePorts{
			Messages: messages, MessageProjection: projection,
		},
		cache,
		rtcCallLogPublisher{},
		nil,
		rtcCallLogMediaReader{},
	)

	handler := messageapp.NewRtcCallLogHandler(rtcCallLogTargetBackend{writer: service})
	fact := messageapp.RtcCallEndedFact{
		EventID: "call-ended-event-1", CallID: "call-1", CallType: "video",
		InitiatorID: "persona-1", ConversationID: "conversation-1",
		EndReason: "normal", DurationMs: 65_000,
		EndedAt: time.Date(2026, 8, 5, 9, 0, 0, 0, time.UTC),
	}
	if err := handler.AppendRtcCallLog(t.Context(), fact); err != nil {
		t.Fatalf("AppendRtcCallLog() error = %v", err)
	}
	if messages.persisted != 1 {
		t.Fatalf("persisted messages = %d, want 1", messages.persisted)
	}
	message := messages.last.Message
	if message.Type != "system_call_log" || message.ClientMessageID != "rtc:"+fact.EventID ||
		message.Card == nil || message.Card.Kind != "rtc_call_log" {
		t.Fatalf("typed call-log message drifted: %+v", message)
	}
	if len(messages.last.Events) != 1 ||
		messages.last.Events[0].EventType != messageevent.MessageSent {
		t.Fatalf("call-log outbox drifted: %+v", messages.last.Events)
	}
	if projection.message.ID != message.ID || cache.conversationID != fact.ConversationID {
		t.Fatalf("projection=%+v cacheConversation=%q", projection.message, cache.conversationID)
	}

	if err := handler.AppendRtcCallLog(t.Context(), fact); err != nil {
		t.Fatalf("replay AppendRtcCallLog() error = %v", err)
	}
	if messages.attempts != 2 || messages.persisted != 1 || messages.last.Message.ID != message.ID {
		t.Fatalf(
			"stable event projection drifted: attempts=%d persisted=%d first=%q replay=%q",
			messages.attempts, messages.persisted, message.ID, messages.last.Message.ID,
		)
	}
}

type rtcCallLogStore struct {
	last      conversationapp.MessageCommit
	attempts  int
	persisted int
}

func (*rtcCallLogStore) ListMediaMessages(
	context.Context,
	string,
	string,
	int,
	int64,
) ([]messagemodel.Message, error) {
	return nil, nil
}

func (store *rtcCallLogStore) CommitMessage(
	_ context.Context,
	commit conversationapp.MessageCommit,
) (conversationapp.MessageCommitResult, error) {
	store.attempts++
	if store.persisted > 0 && store.last.Message.ID == commit.Message.ID {
		return conversationapp.MessageCommitResult{
			Message: store.last.Message, Events: store.last.Events, Replayed: true,
		}, nil
	}
	store.last = commit
	store.persisted++
	return conversationapp.MessageCommitResult{
		Message: commit.Message, Events: commit.Events,
	}, nil
}

func (*rtcCallLogStore) FindMessageByID(context.Context, string) (*messagemodel.Message, error) {
	return nil, messagemodel.ErrMessageNotFound
}

func (*rtcCallLogStore) ListMessages(context.Context, string, int, int64, int64) ([]messagemodel.Message, error) {
	return nil, nil
}

func (*rtcCallLogStore) CountUnreadMessages(context.Context, string, string, int64, int64) (conversationapp.UnreadMessageCounts, error) {
	return conversationapp.UnreadMessageCounts{}, nil
}

func (*rtcCallLogStore) SetMessageRecalled(context.Context, string) error { return nil }

func (*rtcCallLogStore) AppendMessageOutboxEvent(
	context.Context,
	messageports.OutboxEvent,
	string,
	int64,
) error {
	return nil
}

type rtcCallLogProjection struct{ message messagemodel.Message }

func (projection *rtcCallLogProjection) ProjectCommittedMessage(
	_ context.Context,
	message messagemodel.Message,
) error {
	projection.message = message
	return nil
}

type rtcCallLogCache struct{ conversationID string }

func (cache *rtcCallLogCache) InvalidateConversation(
	_ context.Context,
	conversationID string,
) error {
	cache.conversationID = conversationID
	return nil
}

type rtcCallLogPublisher struct{}

func (rtcCallLogPublisher) PublishDomainEvent(context.Context, string, string, string, map[string]any) error {
	return nil
}

func (rtcCallLogPublisher) PublishRecordedDomainEvent(context.Context, string, string, string, string, map[string]any) error {
	return nil
}

type rtcCallLogMediaReader struct{}

func (rtcCallLogMediaReader) ReadOwnedReadyAsset(
	context.Context,
	string,
	string,
) (messageports.MediaAssetDeliverySlice, bool, error) {
	return messageports.MediaAssetDeliverySlice{}, false, nil
}
