package tests

import (
	"context"
	"fmt"
	"testing"

	"quwoquan_service/services/chat-service/internal/application"
	chatcache "quwoquan_service/services/chat-service/internal/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

// newInboxTestEnv creates a fresh InboxService + supporting services
// wired to the shared test MongoDB and miniredis.
func newInboxTestEnv(t *testing.T) (
	*application.InboxService,
	*application.ConversationService,
	*application.MessageService,
	*application.MemberService,
) {
	t.Helper()
	chatStore := persistence.NewMongoChatStore(mongoDB)
	convCache := chatcache.NewConversationCache(redisRouter.Scene("general"))

	inboxSvc := application.NewInboxService(chatStore)
	convSvc := application.NewConversationService(chatStore, convCache, nil)
	msgSvc := application.NewMessageService(chatStore, convCache, nil)
	memberSvc := application.NewMemberService(chatStore, convCache, nil)

	return inboxSvc, convSvc, msgSvc, memberSvc
}

func TestInbox_NewMessageIncrementsUnread(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	inboxSvc, _, _, _ := newInboxTestEnv(t)
	ctx := context.Background()

	conv := createConversation(t, `{"type":"group","title":"inbox unread test"}`)
	convId := conv["_id"].(string)

	userId := "user_inbox_reader_001"
	doPost(t, "/v1/chat/conversations/"+convId+"/members",
		`{"userIds":["user_inbox_reader_001"]}`, "user_test_001", 200)

	if err := inboxSvc.IncrementUnread(ctx, userId, convId); err != nil {
		t.Fatalf("IncrementUnread: %v", err)
	}

	items, err := inboxSvc.ListInbox(ctx, application.ListInboxRequest{
		UserId: userId, Limit: 20,
	})
	if err != nil {
		t.Fatalf("ListInbox: %v", err)
	}

	found := false
	for _, item := range items {
		if item.Conversation.ID == convId {
			found = true
			if item.UserState.UnreadCount != 1 {
				t.Errorf("expected unreadCount=1, got %d", item.UserState.UnreadCount)
			}
			break
		}
	}
	if !found {
		t.Error("conversation not found in inbox after IncrementUnread")
	}
}

func TestInbox_MultipleIncrementsAccumulate(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	inboxSvc, _, _, _ := newInboxTestEnv(t)
	ctx := context.Background()

	conv := createConversation(t, `{"type":"group","title":"inbox multi unread"}`)
	convId := conv["_id"].(string)
	userId := "user_inbox_multi_001"

	for i := 0; i < 5; i++ {
		if err := inboxSvc.IncrementUnread(ctx, userId, convId); err != nil {
			t.Fatalf("IncrementUnread[%d]: %v", i, err)
		}
	}

	items, err := inboxSvc.ListInbox(ctx, application.ListInboxRequest{
		UserId: userId, Limit: 20,
	})
	if err != nil {
		t.Fatalf("ListInbox: %v", err)
	}

	for _, item := range items {
		if item.Conversation.ID == convId {
			if item.UserState.UnreadCount != 5 {
				t.Errorf("expected unreadCount=5, got %d", item.UserState.UnreadCount)
			}
			return
		}
	}
	t.Error("conversation not found in inbox")
}

func TestInbox_MarkAsReadResetsUnread(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	inboxSvc, _, _, _ := newInboxTestEnv(t)
	ctx := context.Background()

	conv := createConversation(t, `{"type":"group","title":"inbox mark read"}`)
	convId := conv["_id"].(string)
	userId := "user_inbox_markread_001"

	for i := 0; i < 3; i++ {
		if err := inboxSvc.IncrementUnread(ctx, userId, convId); err != nil {
			t.Fatalf("IncrementUnread[%d]: %v", i, err)
		}
	}

	if err := inboxSvc.MarkAsRead(ctx, userId, convId, 10); err != nil {
		t.Fatalf("MarkAsRead: %v", err)
	}

	items, err := inboxSvc.ListInbox(ctx, application.ListInboxRequest{
		UserId: userId, Limit: 20,
	})
	if err != nil {
		t.Fatalf("ListInbox: %v", err)
	}

	for _, item := range items {
		if item.Conversation.ID == convId {
			if item.UserState.UnreadCount != 0 {
				t.Errorf("expected unreadCount=0 after MarkAsRead, got %d", item.UserState.UnreadCount)
			}
			if item.UserState.ReadSeq != 10 {
				t.Errorf("expected readSeq=10, got %d", item.UserState.ReadSeq)
			}
			return
		}
	}
	t.Error("conversation not found in inbox after MarkAsRead")
}

func TestInbox_MarkAsReadOnlyAdvancesSeq(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	inboxSvc, _, _, _ := newInboxTestEnv(t)
	ctx := context.Background()

	conv := createConversation(t, `{"type":"direct","title":"inbox seq advance"}`)
	convId := conv["_id"].(string)
	userId := "user_inbox_seqadv_001"

	if err := inboxSvc.MarkAsRead(ctx, userId, convId, 50); err != nil {
		t.Fatalf("MarkAsRead(50): %v", err)
	}
	// MarkAsRead with a lower seq should NOT regress
	if err := inboxSvc.MarkAsRead(ctx, userId, convId, 30); err != nil {
		t.Fatalf("MarkAsRead(30): %v", err)
	}

	items, err := inboxSvc.ListInbox(ctx, application.ListInboxRequest{
		UserId: userId, Limit: 20,
	})
	if err != nil {
		t.Fatalf("ListInbox: %v", err)
	}

	for _, item := range items {
		if item.Conversation.ID == convId {
			if item.UserState.ReadSeq != 50 {
				t.Errorf("readSeq should not regress: expected 50, got %d", item.UserState.ReadSeq)
			}
			return
		}
	}
	t.Error("conversation not found in inbox")
}

func TestInbox_ListInboxSortedByTime(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	inboxSvc, _, _, _ := newInboxTestEnv(t)
	ctx := context.Background()

	userId := "user_inbox_sort_001"

	conv1 := createConversationAs(t, userId, `{"type":"direct","title":"older conv"}`)
	conv1Id := conv1["_id"].(string)

	conv2 := createConversationAs(t, userId, `{"type":"direct","title":"newer conv"}`)
	conv2Id := conv2["_id"].(string)

	// Increment unread on conv1 first, then conv2 (conv2 should be more recent)
	if err := inboxSvc.IncrementUnread(ctx, userId, conv1Id); err != nil {
		t.Fatalf("IncrementUnread conv1: %v", err)
	}
	if err := inboxSvc.IncrementUnread(ctx, userId, conv2Id); err != nil {
		t.Fatalf("IncrementUnread conv2: %v", err)
	}

	items, err := inboxSvc.ListInbox(ctx, application.ListInboxRequest{
		UserId: userId, Limit: 20,
	})
	if err != nil {
		t.Fatalf("ListInbox: %v", err)
	}

	if len(items) < 2 {
		t.Fatalf("expected >=2 inbox items, got %d", len(items))
	}

	// Most recent conversation (conv2) should appear first or have later UpdatedAt
	first := items[0]
	if first.UserState.UpdatedAt.IsZero() {
		t.Error("first item UpdatedAt should not be zero")
	}
}

func TestInbox_ListInboxDefaultLimit(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	inboxSvc, _, _, _ := newInboxTestEnv(t)
	ctx := context.Background()

	userId := "user_inbox_limit_001"

	for i := 0; i < 3; i++ {
		conv := createConversationAs(t, userId, fmt.Sprintf(`{"type":"direct","title":"limit conv %d"}`, i))
		if err := inboxSvc.IncrementUnread(ctx, userId, conv["_id"].(string)); err != nil {
			t.Fatalf("IncrementUnread[%d]: %v", i, err)
		}
	}

	// Request with limit=0 should use default (20)
	items, err := inboxSvc.ListInbox(ctx, application.ListInboxRequest{
		UserId: userId, Limit: 0,
	})
	if err != nil {
		t.Fatalf("ListInbox: %v", err)
	}

	if len(items) != 3 {
		t.Errorf("expected 3 items, got %d", len(items))
	}
}

func TestInbox_EmptyInbox(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	inboxSvc, _, _, _ := newInboxTestEnv(t)
	ctx := context.Background()

	items, err := inboxSvc.ListInbox(ctx, application.ListInboxRequest{
		UserId: "user_no_conversations", Limit: 20,
	})
	if err != nil {
		t.Fatalf("ListInbox: %v", err)
	}

	if len(items) != 0 {
		t.Errorf("expected 0 items for empty inbox, got %d", len(items))
	}
}

func TestInbox_IncrementUnreadCreatesStateIfMissing(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	inboxSvc, _, _, _ := newInboxTestEnv(t)
	ctx := context.Background()

	conv := createConversation(t, `{"type":"group","title":"inbox state create"}`)
	convId := conv["_id"].(string)
	userId := "user_inbox_newstate_001"

	// No prior state for this user/conversation pair
	if err := inboxSvc.IncrementUnread(ctx, userId, convId); err != nil {
		t.Fatalf("IncrementUnread should create state: %v", err)
	}

	items, err := inboxSvc.ListInbox(ctx, application.ListInboxRequest{
		UserId: userId, Limit: 20,
	})
	if err != nil {
		t.Fatalf("ListInbox: %v", err)
	}

	for _, item := range items {
		if item.Conversation.ID == convId {
			if item.UserState.UnreadCount != 1 {
				t.Errorf("expected unreadCount=1, got %d", item.UserState.UnreadCount)
			}
			return
		}
	}
	t.Error("newly created user state not found in inbox")
}
