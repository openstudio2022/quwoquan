package api_integration

import (
	"context"
	"testing"

	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/chat-service/internal/application"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

// newInboxProjectionEnv 装配投影驱动的 inbox 链路：MessageSent 经 Message
// outbox 由 InboxProjector 消费推进未读；已读回落由 MarkAsRead 命令在
// ConversationUserState 聚合内原子完成。
func newInboxProjectionEnv(t *testing.T) (
	*application.InboxService,
	*application.MessageService,
	*application.InboxProjector,
) {
	t.Helper()
	chatStore := persistence.NewMongoChatStore(mongoDB)
	chatStorage := chatStoragePorts(chatStore)
	checkpoints := persistence.NewMongoProjectionCheckpointStore(mongoDB)
	inboxSvc := application.NewInboxService(chatStorage)
	msgSvc := application.NewMessageService(
		chatStorage,
		noopConversationCache{},
		eventPublisherForContractTest(),
		application.AllowRelationshipGateForTest(),
		testMediaAssetDeliveryReader{},
	)
	projector := application.NewInboxProjector(chatStore, checkpoints, chatStore, chatStore)
	return inboxSvc, msgSvc, projector
}

type noopConversationCache struct{}

func (noopConversationCache) InvalidateConversation(context.Context, string) error {
	return nil
}

func drainInboxProjector(t *testing.T, projector *application.InboxProjector) {
	t.Helper()
	for range 10 {
		count, err := projector.Drain(context.Background(), 100)
		if err != nil {
			t.Fatalf("drain inbox projector: %v", err)
		}
		if count == 0 {
			return
		}
	}
}

func inboxUnread(t *testing.T, inboxSvc *application.InboxService, userId, convId string) (int, int64, bool) {
	t.Helper()
	items, err := inboxSvc.ListInbox(context.Background(), application.ListInboxRequest{
		UserId: userId, Limit: 50,
	})
	if err != nil {
		t.Fatalf("ListInbox: %v", err)
	}
	for _, item := range items {
		if item.Conversation.ID == convId {
			return item.UserState.UnreadCount, item.UserState.ReadSeq, true
		}
	}
	return 0, 0, false
}

func TestInbox_MessageSentEventAdvancesUnreadViaProjection(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	inboxSvc, _, projector := newInboxProjectionEnv(t)

	conv := createConversation(t, `{"type":"group","title":"inbox unread test","initialMemberIds":["user_inbox_reader_001"]}`)
	convId := conv["id"].(string)

	sendMessage(t, convId, `{"type":"text","content":"unread probe","clientMsgId":"inbox-unread-1"}`)
	drainInboxProjector(t, projector)

	unread, _, found := inboxUnread(t, inboxSvc, "user_inbox_reader_001", convId)
	if !found {
		t.Fatal("conversation not found in receiver inbox after projection")
	}
	if unread != 1 {
		t.Fatalf("expected receiver unreadCount=1, got %d", unread)
	}

	senderUnread, _, senderFound := inboxUnread(t, inboxSvc, "user_test_001", convId)
	if !senderFound {
		t.Fatal("conversation not found in sender inbox")
	}
	if senderUnread != 0 {
		t.Fatalf("sender unread must stay 0, got %d", senderUnread)
	}
}

func TestInbox_MultipleMessagesAccumulateViaProjection(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	inboxSvc, _, projector := newInboxProjectionEnv(t)

	conv := createConversation(t, `{"type":"group","title":"inbox multi unread","initialMemberIds":["user_inbox_multi_001"]}`)
	convId := conv["id"].(string)

	for i := range 5 {
		sendMessage(t, convId, `{"type":"text","content":"m","clientMsgId":"inbox-multi-`+string(rune('a'+i))+`"}`)
	}
	drainInboxProjector(t, projector)

	unread, _, found := inboxUnread(t, inboxSvc, "user_inbox_multi_001", convId)
	if !found {
		t.Fatal("conversation not found in inbox")
	}
	if unread != 5 {
		t.Fatalf("expected unreadCount=5, got %d", unread)
	}
}

func TestInbox_ProjectionDrainIsReplayableFromCheckpoint(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	inboxSvc, _, projector := newInboxProjectionEnv(t)

	conv := createConversation(t, `{"type":"group","title":"inbox replay","initialMemberIds":["user_inbox_replay_001"]}`)
	convId := conv["id"].(string)

	sendMessage(t, convId, `{"type":"text","content":"first","clientMsgId":"inbox-replay-1"}`)
	drainInboxProjector(t, projector)
	// 再次 drain 不得重复推进（checkpoint 幂等）。
	drainInboxProjector(t, projector)

	unread, _, _ := inboxUnread(t, inboxSvc, "user_inbox_replay_001", convId)
	if unread != 1 {
		t.Fatalf("checkpoint replay must not double count: got %d", unread)
	}
}

func TestInbox_MarkAsReadCommandResetsUnreadAndAdvancesWatermark(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	inboxSvc, msgSvc, projector := newInboxProjectionEnv(t)
	readerId := "user_inbox_markread_001"

	conv := createConversation(t, `{"type":"group","title":"inbox mark read","initialMemberIds":["`+readerId+`"]}`)
	convId := conv["id"].(string)

	var lastMessageId string
	for _, clientMsgId := range []string{"read-a", "read-b", "read-c"} {
		message := sendMessage(t, convId, `{"type":"text","content":"m","clientMsgId":"`+clientMsgId+`"}`)
		lastMessageId = message["messageId"].(string)
	}
	drainInboxProjector(t, projector)

	readCtx := operation.WithContext(context.Background(), operation.Context{
		OperationID:    "api_integration.mark_as_read",
		IdempotencyKey: "inbox-markread-key-1",
		Actor:          operation.ActorContext{AccountID: readerId, PersonaID: readerId},
	})
	if err := msgSvc.MarkAsRead(readCtx, application.MarkAsReadRequest{
		ConversationId: convId,
		MessageId:      lastMessageId,
		UserId:         readerId,
	}); err != nil {
		t.Fatalf("MarkAsRead: %v", err)
	}

	unread, readSeq, found := inboxUnread(t, inboxSvc, readerId, convId)
	if !found {
		t.Fatal("conversation not found in inbox after MarkAsRead")
	}
	if unread != 0 {
		t.Fatalf("expected unreadCount=0 after MarkAsRead, got %d", unread)
	}
	if readSeq < 3 {
		t.Fatalf("expected readSeq >= 3, got %d", readSeq)
	}
}

func TestInbox_MarkAsReadStaleWatermarkIsNoop(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	inboxSvc, msgSvc, projector := newInboxProjectionEnv(t)
	readerId := "user_inbox_seqadv_001"

	conv := createConversation(t, `{"type":"group","title":"inbox seq advance","initialMemberIds":["`+readerId+`"]}`)
	convId := conv["id"].(string)

	first := sendMessage(t, convId, `{"type":"text","content":"first","clientMsgId":"seq-first"}`)
	second := sendMessage(t, convId, `{"type":"text","content":"second","clientMsgId":"seq-second"}`)
	drainInboxProjector(t, projector)

	newerCtx := operation.WithContext(context.Background(), operation.Context{
		OperationID:    "api_integration.mark_as_read",
		IdempotencyKey: "seqadv-key-newer",
		Actor:          operation.ActorContext{AccountID: readerId, PersonaID: readerId},
	})
	if err := msgSvc.MarkAsRead(newerCtx, application.MarkAsReadRequest{
		ConversationId: convId,
		MessageId:      second["messageId"].(string),
		UserId:         readerId,
	}); err != nil {
		t.Fatalf("MarkAsRead newer: %v", err)
	}

	// 旧水位重放：no-op，不回退 readSeq，也不产生新事件。
	staleCtx := operation.WithContext(context.Background(), operation.Context{
		OperationID:    "api_integration.mark_as_read",
		IdempotencyKey: "seqadv-key-stale",
		Actor:          operation.ActorContext{AccountID: readerId, PersonaID: readerId},
	})
	if err := msgSvc.MarkAsRead(staleCtx, application.MarkAsReadRequest{
		ConversationId: convId,
		MessageId:      first["messageId"].(string),
		UserId:         readerId,
	}); err != nil {
		t.Fatalf("MarkAsRead stale: %v", err)
	}

	_, readSeq, _ := inboxUnread(t, inboxSvc, readerId, convId)
	if readSeq != 2 {
		t.Fatalf("readSeq should not regress: expected 2, got %d", readSeq)
	}
}

func TestInbox_EmptyInbox(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	inboxSvc, _, _ := newInboxProjectionEnv(t)

	items, err := inboxSvc.ListInbox(context.Background(), application.ListInboxRequest{
		UserId: "user_no_conversations", Limit: 20,
	})
	if err != nil {
		t.Fatalf("ListInbox: %v", err)
	}
	if len(items) != 0 {
		t.Fatalf("expected 0 items for empty inbox, got %d", len(items))
	}
}
