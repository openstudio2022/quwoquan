package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	chathttp "quwoquan_service/services/chat-service/internal/adapters/http"
	"quwoquan_service/services/chat-service/internal/application"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
	"quwoquan_service/services/chat-service/internal/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

// selectableMutualGate 按 targetID 集合判定 mutual，用于「从群聊中选择联系人」交集测试。
type selectableMutualGate struct {
	mutual map[string]bool
}

func (g selectableMutualGate) GetCapability(
	_ context.Context,
	_ string,
	targetID string,
) (application.RelationshipCapability, error) {
	if g.mutual[targetID] {
		return application.RelationshipCapability{
			IsMutual:                    true,
			CanCreateDirectConversation: true,
			CanSendMessage:              true,
		}, nil
	}
	return application.RelationshipCapability{}, nil
}

// socialMutualServer 返回 following+followers，使指定用户成为「contact 候选」。
func socialMutualServer(viewer string, contactIDs ...string) *httptest.Server {
	items := make([]map[string]any, 0, len(contactIDs))
	for _, id := range contactIDs {
		items = append(items, map[string]any{
			"subAccountId":  id,
			"displayName":   "Display_" + id,
			"avatarUrl":     "media/avatar/s/mock/user/" + id + "/v1/avatar.png",
			"followedAt":    "2026-06-06T12:00:00Z",
			"relationState": "mutual",
		})
	}
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/v1/user/sub-accounts/" + viewer + "/following",
			"/v1/user/sub-accounts/" + viewer + "/followers":
			_ = json.NewEncoder(w).Encode(map[string]any{"items": items, "cursor": ""})
		case "/v1/user/contact-discovery/latest":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"matchedSubAccountIds": []string{},
				"status":               "completed",
				"createdAt":            time.Date(2026, 6, 6, 12, 4, 0, 0, time.UTC),
			})
		default:
			writeTestUserNotFound(w, r, "unexpected "+r.Method+" "+r.URL.Path)
		}
	}))
}

func seedSelectableGroup(
	t *testing.T,
	conversationID string,
	viewer string,
	title string,
	memberIDs []string,
) {
	t.Helper()
	db := requireMongoDB(t)
	ctx := context.Background()
	now := time.Now().UTC()
	conversation := &model.Conversation{
		ID:             conversationID,
		Type:           "group",
		Title:          title,
		AvatarUrl:      "media/avatar/s/archived-avatar/conversation/" + conversationID + "/v1/mock.png",
		CreatorId:      viewer,
		MemberCount:    len(memberIDs) + 1,
		MaxGroupSize:   500,
		ReceiptEnabled: true,
		Status:         "active",
		CreatedAt:      now,
		UpdatedAt:      now,
	}
	if _, err := db.Collection("conversations").InsertOne(ctx, conversation); err != nil {
		t.Fatalf("seed conversation %s: %v", conversationID, err)
	}
	owner := &model.ConversationMember{
		ID:             conversationID + "_owner",
		ConversationId: conversationID,
		UserId:         viewer,
		DisplayName:    "Display_" + viewer,
		AvatarUrl:      "media/avatar/s/mock/user/" + viewer + "/v1/avatar.png",
		MemberType:     "user",
		Role:           "owner",
		JoinedAt:       now,
	}
	if _, err := db.Collection("conversation_members").InsertOne(ctx, owner); err != nil {
		t.Fatalf("seed owner member %s: %v", conversationID, err)
	}
	for i, id := range memberIDs {
		member := &model.ConversationMember{
			ID:             conversationID + "_" + id,
			ConversationId: conversationID,
			UserId:         id,
			DisplayName:    "Display_" + id,
			AvatarUrl:      "media/avatar/s/mock/user/" + id + "/v1/avatar.png",
			MemberType:     "user",
			Role:           "member",
			InvitedBy:      viewer,
			JoinedAt:       now.Add(time.Duration(i+1) * time.Second),
		}
		if _, err := db.Collection("conversation_members").InsertOne(ctx, member); err != nil {
			t.Fatalf("seed member %s in %s: %v", id, conversationID, err)
		}
	}
	state := &model.ConversationUserState{
		ID:             conversationID + "_state_" + viewer,
		UserId:         viewer,
		ConversationId: conversationID,
	}
	if _, err := db.Collection("conversation_user_states").InsertOne(ctx, state); err != nil {
		t.Fatalf("seed user state %s: %v", conversationID, err)
	}
}

func newSelectableGroupHandler(t *testing.T, viewer string, mutual map[string]bool, contactIDs ...string) http.Handler {
	t.Helper()
	socialServer := socialMutualServer(viewer, contactIDs...)
	t.Cleanup(socialServer.Close)

	chatStore := persistence.NewMongoChatStore(mongoDB)
	convCache := cache.NewConversationCache(redisRouter.Scene("general"))
	profiles := testProfileResolver{}
	memberSvc := application.NewMemberService(
		chatStore,
		convCache,
		nil,
		profiles,
		nil,
		nil,
		nil,
		application.WithRelationshipGate(selectableMutualGate{mutual: mutual}),
		application.WithSocialContactResolver(
			chathttp.NewUserSocialContactResolver(socialServer.URL, socialServer.Client()),
		),
	)
	return chathttp.NewChatHandler(
		application.NewConversationService(chatStore, convCache, nil, profiles, application.DenyRelationshipGate(), nil, nil, nil),
		application.NewMessageService(chatStore, convCache, nil, application.DenyRelationshipGate()),
		memberSvc,
		application.NewInboxService(chatStore),
		nil,
	).Routes()
}

func getSelectableJSON(t *testing.T, handler http.Handler, path, viewer string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, path, nil)
	req.Header.Set("X-Client-User-Id", viewer)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	var payload map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &payload)
	return rec.Code, payload
}

// TestListSelectableGroupConversations_ReturnsGroupsWithFriendCount 验证图四群列表：
// 只返回含互关联系人的群，并给出准确的 friendMemberCount。
func TestListSelectableGroupConversations_ReturnsGroupsWithFriendCount(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	const viewer = "viewer_sg"
	mutual := map[string]bool{"friend_a": true, "friend_b": true}
	// 含 2 个互关好友 + 1 个非联系人成员 stranger_x。
	seedSelectableGroup(t, "conv_sg_with_friends", viewer, "周末登山群", []string{"friend_a", "friend_b", "stranger_x"})
	// 无任何互关联系人成员，只有 stranger。
	seedSelectableGroup(t, "conv_sg_no_friends", viewer, "陌生人群", []string{"stranger_y"})

	handler := newSelectableGroupHandler(t, viewer, mutual, "friend_a", "friend_b")
	code, payload := getSelectableJSON(t, handler, "/v1/chat/selectable-group-conversations?limit=50", viewer)
	if code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %#v", code, payload)
	}
	items, ok := payload["items"].([]any)
	if !ok {
		t.Fatalf("response missing items: %#v", payload)
	}
	if len(items) != 1 {
		t.Fatalf("expected exactly 1 group with mutual friends, got %d: %#v", len(items), items)
	}
	row := items[0].(map[string]any)
	if row["conversationId"] != "conv_sg_with_friends" {
		t.Fatalf("expected conv_sg_with_friends, got %v", row["conversationId"])
	}
	if got := int(row["friendMemberCount"].(float64)); got != 2 {
		t.Fatalf("expected friendMemberCount 2 (stranger excluded), got %d", got)
	}
}

// TestListSelectableGroupContactMembers_IntersectsMutualMembers 验证图五成员列表：
// 只返回群成员 ∩ 互关联系人，排除当前用户与非联系人成员。
func TestListSelectableGroupContactMembers_IntersectsMutualMembers(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	const viewer = "viewer_sg"
	mutual := map[string]bool{"friend_a": true, "friend_b": true}
	seedSelectableGroup(t, "conv_sg_with_friends", viewer, "周末登山群", []string{"friend_a", "friend_b", "stranger_x"})

	handler := newSelectableGroupHandler(t, viewer, mutual, "friend_a", "friend_b")
	code, payload := getSelectableJSON(
		t,
		handler,
		"/v1/chat/selectable-group-conversations/conv_sg_with_friends/contact-members?limit=100",
		viewer,
	)
	if code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %#v", code, payload)
	}
	items, ok := payload["items"].([]any)
	if !ok {
		t.Fatalf("response missing items: %#v", payload)
	}
	if len(items) != 2 {
		t.Fatalf("expected 2 mutual members (viewer + stranger excluded), got %d: %#v", len(items), items)
	}
	got := map[string]bool{}
	for _, raw := range items {
		row := raw.(map[string]any)
		got[row["userId"].(string)] = true
		if row["relationState"] != "mutual" {
			t.Fatalf("expected relationState mutual, got %v", row["relationState"])
		}
	}
	if !got["friend_a"] || !got["friend_b"] {
		t.Fatalf("expected friend_a and friend_b, got %#v", got)
	}
	if got[viewer] || got["stranger_x"] {
		t.Fatalf("viewer/stranger must be excluded, got %#v", got)
	}
}

// TestListSelectableGroupContactMembers_NotFoundReturnsStructuredError 验证不存在的群返回
// 结构化 CHAT.USER.conversation_not_found（HTTP 404）。
func TestListSelectableGroupContactMembers_NotFoundReturnsStructuredError(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	const viewer = "viewer_sg"
	handler := newSelectableGroupHandler(t, viewer, map[string]bool{}, "friend_a")
	code, payload := getSelectableJSON(
		t,
		handler,
		"/v1/chat/selectable-group-conversations/conv_missing/contact-members",
		viewer,
	)
	if code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d: %#v", code, payload)
	}
	if payload["code"] != "CHAT.USER.conversation_not_found" {
		t.Fatalf("expected CHAT.USER.conversation_not_found, got %#v", payload)
	}
}
