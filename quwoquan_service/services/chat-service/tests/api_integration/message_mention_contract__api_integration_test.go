package api_integration

import (
	"context"
	"fmt"
	"net/http"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/chat-service/internal/application"
)

func TestMessageMention_CanonicalValueRoundTripsAcrossMessageAndSync(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(
		t,
		`{"type":"group","title":"mention canonical","initialMemberIds":["user_b","user_c"]}`,
	)
	conversationID := conv["id"].(string)
	sent := sendMessage(
		t,
		conversationID,
		`{"type":"text","content":"@Display_user_b 你好","mentions":[" user_b ","","user_b"],"clientMsgId":"mention-canonical-1"}`,
	)
	messageID := sent["messageId"].(string)

	var stored struct {
		Mentions []string `bson:"mentions"`
	}
	if err := requireMongoDB(t).Collection("messages").FindOne(
		context.Background(),
		bson.M{"_id": messageID},
	).Decode(&stored); err != nil {
		t.Fatalf("read stored mention message: %v", err)
	}
	assertStringSlice(t, "stored mentions", stored.Mentions, []string{"user_b"})

	code, listed := doGet(
		t,
		"/chat/conversations/"+conversationID+"/messages?limit=10",
		"user_test_001",
	)
	if code != http.StatusOK {
		t.Fatalf("list messages: status=%d body=%#v", code, listed)
	}
	listItems := listed["items"].([]any)
	assertWireMentions(t, "ListMessages", listItems[0].(map[string]any), []string{"user_b"})

	synced := doPost(
		t,
		"/chat/conversations/"+conversationID+"/sync",
		`{"lastSeq":0,"limit":10}`,
		"user_test_001",
		http.StatusOK,
	)
	syncItems := synced["messages"].([]any)
	assertWireMentions(t, "SyncMessages", syncItems[0].(map[string]any), []string{"user_b"})

	var outbox struct {
		Payload bson.M `bson:"payload"`
	}
	if err := requireMongoDB(t).Collection("messages_outbox").FindOne(
		context.Background(),
		bson.M{"aggregateId": messageID, "eventType": "MessageSent"},
	).Decode(&outbox); err != nil {
		t.Fatalf("read MessageSent outbox: %v", err)
	}
	assertStringSlice(
		t,
		"MessageSent mentions",
		wireStringSlice(outbox.Payload["mentions"]),
		[]string{"user_b"},
	)
}

func TestMessageMention_ServerRejectsInvalidTargetsAndRoleEscalation(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(
		t,
		`{"type":"group","title":"mention authz","initialMemberIds":["user_member","user_admin"]}`,
	)
	conversationID := conv["id"].(string)
	setGroupAdmins(t, conversationID, "user_test_001", `{"adminIds":["user_admin"]}`)

	cases := []struct {
		name    string
		userID  string
		payload string
	}{
		{
			name:    "non member target",
			userID:  "user_test_001",
			payload: `{"type":"text","content":"@外部","mentions":["user_outsider"],"clientMsgId":"mention-outsider"}`,
		},
		{
			name:    "member mention all",
			userID:  "user_member",
			payload: `{"type":"text","content":"@所有人","mentions":["__all__"],"clientMsgId":"mention-all-member"}`,
		},
		{
			name:    "assistant absent",
			userID:  "user_test_001",
			payload: `{"type":"text","content":"@小趣","mentions":["assistant"],"clientMsgId":"mention-assistant-absent"}`,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			failure := doPost(
				t,
				"/chat/conversations/"+conversationID+"/messages",
				tc.payload,
				tc.userID,
				http.StatusBadRequest,
			)
			if failure["code"] != "CHAT.USER.message_invalid" {
				t.Fatalf("expected message_invalid, got %#v", failure)
			}
		})
	}

	sendByUser(
		t,
		conversationID,
		"user_test_001",
		`{"type":"text","content":"@所有人 owner","mentions":["__all__"],"clientMsgId":"mention-all-owner"}`,
	)
	sendByUser(
		t,
		conversationID,
		"user_admin",
		`{"type":"text","content":"@所有人 admin","mentions":["__all__"],"clientMsgId":"mention-all-admin"}`,
	)

	tooMany := make([]string, 0, 51)
	for index := range 51 {
		tooMany = append(tooMany, fmt.Sprintf(`"user_%02d"`, index))
	}
	failure := doPost(
		t,
		"/chat/conversations/"+conversationID+"/messages",
		`{"type":"text","content":"too many","mentions":[`+
			strings.Join(tooMany, ",")+`],"clientMsgId":"mention-too-many"}`,
		"user_test_001",
		http.StatusBadRequest,
	)
	if failure["code"] != "CHAT.USER.message_invalid" {
		t.Fatalf("too many mentions must be message_invalid: %#v", failure)
	}
}

func TestMessageMention_DirectConversationRejectsMentions(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(
		t,
		`{"type":"direct","title":"direct mention","initialMemberIds":["user_peer"]}`,
	)
	failure := doPost(
		t,
		"/chat/conversations/"+conv["id"].(string)+"/messages",
		`{"type":"text","content":"@peer","mentions":["user_peer"],"clientMsgId":"mention-direct"}`,
		"user_test_001",
		http.StatusBadRequest,
	)
	if failure["code"] != "CHAT.USER.message_invalid" {
		t.Fatalf("direct mention must be message_invalid: %#v", failure)
	}
}

func TestMessageMention_UnreadProjectionAndMarkRead(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	inboxService, messageService, projector := newInboxProjectionEnv(t)

	conv := createConversation(
		t,
		`{"type":"group","title":"mention unread","initialMemberIds":["user_target","user_other"]}`,
	)
	conversationID := conv["id"].(string)
	first := sendMessage(
		t,
		conversationID,
		`{"type":"text","content":"@target","mentions":["user_target"],"clientMsgId":"mention-unread-direct"}`,
	)
	second := sendMessage(
		t,
		conversationID,
		`{"type":"text","content":"@所有人","mentions":["__all__"],"clientMsgId":"mention-unread-all"}`,
	)
	drainInboxProjector(t, projector)
	drainInboxProjector(t, projector)

	targetUnread, targetMentions := inboxCounters(
		t,
		inboxService,
		"user_target",
		conversationID,
	)
	if targetUnread != 2 || targetMentions != 2 {
		t.Fatalf(
			"target counters mismatch: unread=%d mentions=%d",
			targetUnread,
			targetMentions,
		)
	}
	otherUnread, otherMentions := inboxCounters(
		t,
		inboxService,
		"user_other",
		conversationID,
	)
	if otherUnread != 2 || otherMentions != 1 {
		t.Fatalf(
			"mention-all counters mismatch: unread=%d mentions=%d",
			otherUnread,
			otherMentions,
		)
	}

	readContext := operation.WithContext(context.Background(), operation.Context{
		OperationID:    "api_integration.mention_mark_as_read",
		IdempotencyKey: "mention-mark-read-key",
		Actor: operation.ActorContext{
			AccountID: "user_target",
			PersonaID: "user_target",
		},
	})
	if err := messageService.MarkAsRead(
		readContext,
		application.MarkAsReadRequest{
			ConversationId: conversationID,
			MessageId:      first["messageId"].(string),
			UserId:         "user_target",
		},
	); err != nil {
		t.Fatalf("mark mention read: %v", err)
	}
	_, targetMentions = inboxCounters(t, inboxService, "user_target", conversationID)
	if targetMentions != 1 {
		t.Fatalf(
			"mentionUnreadCount after partial watermark must retain later mention, got %d",
			targetMentions,
		)
	}

	readLatestContext := operation.WithContext(context.Background(), operation.Context{
		OperationID:    "api_integration.mention_mark_latest_as_read",
		IdempotencyKey: "mention-mark-latest-read-key",
		Actor: operation.ActorContext{
			AccountID: "user_target",
			PersonaID: "user_target",
		},
	})
	if err := messageService.MarkAsRead(
		readLatestContext,
		application.MarkAsReadRequest{
			ConversationId: conversationID,
			MessageId:      second["messageId"].(string),
			UserId:         "user_target",
		},
	); err != nil {
		t.Fatalf("mark latest mention read: %v", err)
	}
	_, targetMentions = inboxCounters(t, inboxService, "user_target", conversationID)
	if targetMentions != 0 {
		t.Fatalf("mentionUnreadCount must reach zero at latest watermark, got %d", targetMentions)
	}
}

func TestMessageMention_LateAndReplayedProjectionDoesNotReopenReadWatermark(
	t *testing.T,
) {
	t.Cleanup(func() { cleanAll(t) })
	inboxService, messageService, projector := newInboxProjectionEnv(t)

	conv := createConversation(
		t,
		`{"type":"group","title":"mention projection race","initialMemberIds":["user_target"]}`,
	)
	conversationID := conv["id"].(string)
	sendMessage(
		t,
		conversationID,
		`{"type":"text","content":"@target","mentions":["user_target"],"clientMsgId":"mention-race-direct"}`,
	)
	latest := sendMessage(
		t,
		conversationID,
		`{"type":"text","content":"@所有人","mentions":["__all__"],"clientMsgId":"mention-race-all"}`,
	)

	readContext := operation.WithContext(context.Background(), operation.Context{
		OperationID:    "api_integration.mention_mark_before_projection",
		IdempotencyKey: "mention-mark-before-projection-key",
		Actor: operation.ActorContext{
			AccountID: "user_target",
			PersonaID: "user_target",
		},
	})
	if err := messageService.MarkAsRead(
		readContext,
		application.MarkAsReadRequest{
			ConversationId: conversationID,
			MessageId:      latest["messageId"].(string),
			UserId:         "user_target",
		},
	); err != nil {
		t.Fatalf("mark latest before projection: %v", err)
	}

	drainInboxProjector(t, projector)
	unread, mentions := inboxCounters(
		t,
		inboxService,
		"user_target",
		conversationID,
	)
	if unread != 0 || mentions != 0 {
		t.Fatalf(
			"late projection reopened read watermark: unread=%d mentions=%d",
			unread,
			mentions,
		)
	}

	if _, err := requireMongoDB(t).Collection("chat_projection_checkpoints").
		UpdateOne(
			context.Background(),
			bson.M{"_id": "chat-inbox-projection-message"},
			bson.M{"$set": bson.M{"checkpoint": ""}},
		); err != nil {
		t.Fatalf("rewind inbox checkpoint: %v", err)
	}
	drainInboxProjector(t, projector)
	unread, mentions = inboxCounters(
		t,
		inboxService,
		"user_target",
		conversationID,
	)
	if unread != 0 || mentions != 0 {
		t.Fatalf(
			"replayed projection duplicated counters: unread=%d mentions=%d",
			unread,
			mentions,
		)
	}
}

func TestListMembers_SearchIsServerSideLiteralAndMemberScoped(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(
		t,
		`{"type":"group","title":"member search","initialMemberIds":["search_alpha","search_beta"]}`,
	)
	conversationID := conv["id"].(string)

	code, result := doGet(
		t,
		"/chat/conversations/"+conversationID+"/members?query=search_alpha&limit=50&sort=display_name_asc",
		"search_beta",
	)
	if code != http.StatusOK {
		t.Fatalf("member search: status=%d body=%#v", code, result)
	}
	items := result["items"].([]any)
	if len(items) != 1 || items[0].(map[string]any)["userId"] != "search_alpha" {
		t.Fatalf("unexpected member search result: %#v", items)
	}

	code, result = doGet(
		t,
		"/chat/conversations/"+conversationID+"/members?query=%5B&limit=50",
		"search_beta",
	)
	if code != http.StatusOK {
		t.Fatalf("literal search must not treat query as regex: status=%d body=%#v", code, result)
	}
	if items = result["items"].([]any); len(items) != 0 {
		t.Fatalf("literal bracket query should have no matches: %#v", items)
	}

	code, result = doGet(
		t,
		"/chat/conversations/"+conversationID+"/members?query=search&limit=50",
		"user_outsider",
	)
	if code != http.StatusNotFound {
		t.Fatalf("non-member roster search must fail closed: status=%d body=%#v", code, result)
	}
}

func inboxCounters(
	t *testing.T,
	inboxService *application.InboxService,
	userID string,
	conversationID string,
) (int, int) {
	t.Helper()
	items, err := inboxService.ListInbox(
		context.Background(),
		application.ListInboxRequest{UserId: userID, Limit: 50},
	)
	if err != nil {
		t.Fatalf("ListInbox counters: %v", err)
	}
	for _, item := range items {
		if item.Conversation.ID == conversationID {
			return item.UserState.UnreadCount, item.UserState.MentionUnreadCount
		}
	}
	t.Fatalf("conversation %s not found for %s", conversationID, userID)
	return 0, 0
}

func sendByUser(
	t *testing.T,
	conversationID string,
	userID string,
	payload string,
) map[string]any {
	t.Helper()
	return doPost(
		t,
		"/chat/conversations/"+conversationID+"/messages",
		payload,
		userID,
		http.StatusCreated,
	)
}

func assertWireMentions(
	t *testing.T,
	source string,
	item map[string]any,
	want []string,
) {
	t.Helper()
	assertStringSlice(t, source+" mentions", wireStringSlice(item["mentions"]), want)
}

func wireStringSlice(raw any) []string {
	values := make([]string, 0)
	switch items := raw.(type) {
	case []any:
		for _, item := range items {
			if value, ok := item.(string); ok {
				values = append(values, value)
			}
		}
	case bson.A:
		for _, item := range items {
			if value, ok := item.(string); ok {
				values = append(values, value)
			}
		}
	case []string:
		values = append(values, items...)
	}
	return values
}

func assertStringSlice(t *testing.T, label string, got, want []string) {
	t.Helper()
	if len(got) != len(want) {
		t.Fatalf("%s length=%d want=%d values=%#v", label, len(got), len(want), got)
	}
	for index := range want {
		if got[index] != want[index] {
			t.Fatalf("%s[%d]=%q want=%q", label, index, got[index], want[index])
		}
	}
}
