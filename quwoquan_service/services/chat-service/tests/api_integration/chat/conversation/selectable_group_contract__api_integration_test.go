// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/group-create-flow/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
// readiness_case: list-group-candidates-api
// readiness_case: list-selectable-group-conversations-api
// readiness_case: list-selectable-group-contact-members-api
package api_integration

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	chathttp "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/http"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/persistence"
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

type unavailableSelectableGroupGate struct{}

func (unavailableSelectableGroupGate) GetCapability(
	context.Context,
	string,
	string,
) (application.RelationshipCapability, error) {
	return application.RelationshipCapability{}, errors.New(
		"relationship capability dependency is unavailable",
	)
}

// socialMutualServer 返回 following+followers，使指定用户成为「contact 候选」。
func socialMutualServer(viewer string, contactIDs ...string) *httptest.Server {
	items := make([]map[string]any, 0, len(contactIDs))
	for _, id := range contactIDs {
		items = append(items, map[string]any{
			"personaId":     id,
			"userHandle":    "handle_" + id,
			"displayName":   "Display_" + id,
			"avatarUrl":     "media/avatar/s/mock/user/" + id + "/avatar.png",
			"followedAt":    "2026-06-06T12:00:00Z",
			"relationState": "mutual",
		})
	}
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/user/personas/" + viewer + "/following",
			"/user/personas/" + viewer + "/followers":
			_ = json.NewEncoder(w).Encode(map[string]any{"items": items, "cursor": ""})
		case "/user/contact-discovery/latest":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"matchedPersonaIds": []string{},
				"status":            "completed",
				"createdAt":         time.Date(2026, 6, 6, 12, 4, 0, 0, time.UTC),
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
		AvatarUrl:      "media/avatar/s/archived-avatar/conversation/" + conversationID + "/mock.png",
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
		UserHandle:     "handle_" + viewer,
		DisplayName:    "Display_" + viewer,
		AvatarUrl:      "media/avatar/s/mock/user/" + viewer + "/avatar.png",
		MemberType:     "user",
		Role:           "owner",
		JoinedAt:       now,
	}
	if _, err := db.Collection("conversation_memberships").InsertOne(ctx, owner); err != nil {
		t.Fatalf("seed owner member %s: %v", conversationID, err)
	}
	for i, id := range memberIDs {
		member := &model.ConversationMember{
			ID:             conversationID + "_" + id,
			ConversationId: conversationID,
			UserId:         id,
			UserHandle:     "handle_" + id,
			DisplayName:    "Display_" + id,
			AvatarUrl:      "media/avatar/s/mock/user/" + id + "/avatar.png",
			MemberType:     "user",
			Role:           "member",
			InvitedBy:      viewer,
			JoinedAt:       now.Add(time.Duration(i+1) * time.Second),
		}
		if _, err := db.Collection("conversation_memberships").InsertOne(ctx, member); err != nil {
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

func bindSelectableGroupToCircle(
	t *testing.T,
	conversationID string,
	circleID string,
) {
	t.Helper()
	result, err := requireMongoDB(t).Collection("conversations").UpdateOne(
		context.Background(),
		bson.M{"_id": conversationID},
		bson.M{"$set": bson.M{"circleId": circleID}},
	)
	if err != nil {
		t.Fatalf("bind selectable group %s to circle: %v", conversationID, err)
	}
	if result.MatchedCount != 1 {
		t.Fatalf("selectable group %s missing while binding circle", conversationID)
	}
}

func newSelectableGroupHandler(t *testing.T, viewer string, mutual map[string]bool, contactIDs ...string) http.Handler {
	return newSelectableGroupHandlerWithRelationshipGate(
		t,
		viewer,
		selectableMutualGate{mutual: mutual},
		contactIDs...,
	)
}

func newSelectableGroupHandlerWithRelationshipGate(
	t *testing.T,
	viewer string,
	relationshipGate application.RelationshipGate,
	contactIDs ...string,
) http.Handler {
	t.Helper()
	socialServer := socialMutualServer(viewer, contactIDs...)
	t.Cleanup(socialServer.Close)

	chatStore := persistence.NewMongoChatStore(mongoDB)
	chatStorage := chatStoragePorts(chatStore)
	convCache := cache.NewConversationCache(redisRouter.Scene("general"))
	profiles := testProfileResolver{}
	memberSvc := application.NewMemberService(
		chatStorage,
		convCache,
		eventPublisherForContractTest(),
		profiles,
		nil,
		nil,
		groupAvatarSchedulerForContractTest(),
		application.WithRelationshipGate(relationshipGate),
		application.WithSocialContactResolver(
			chathttp.NewUserSocialContactResolver(socialServer.URL, socialServer.Client()),
		),
	)
	return chathttp.NewChatHandler(
		application.NewConversationService(chatStorage, convCache, eventPublisherForContractTest(), profiles, application.DenyRelationshipGate(), nil, nil, groupAvatarSchedulerForContractTest()),
		application.NewMessageService(chatStorage, convCache, eventPublisherForContractTest(), application.DenyRelationshipGate(), testMediaAssetDeliveryReader{}),
		memberSvc,
		newTestInboxService(),
		nil,
	).Routes()
}

func getSelectableJSON(t *testing.T, handler http.Handler, path, viewer string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, path, nil)
	req.Header.Set("X-Client-User-Id", viewer)
	req.Header.Set("X-Client-Persona-Id", viewer)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	var payload map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &payload)
	return rec.Code, payload
}

func TestGroupCandidateReadersFailClosedWhenRelationshipGateUnavailable(
	t *testing.T,
) {
	t.Cleanup(func() { cleanAll(t) })

	const (
		viewer                = "viewer_unavailable_gate"
		privateConversationID = "conv_private_unavailable_gate"
		circleConversationID  = "conv_circle_unavailable_gate"
		circleID              = "circle_unavailable_gate"
		contactID             = "friend_unavailable_gate"
	)
	seedSelectableGroup(
		t,
		privateConversationID,
		viewer,
		"关系服务不可用验证群",
		[]string{contactID},
	)
	seedSelectableGroup(
		t,
		circleConversationID,
		viewer,
		"关系服务不可用验证圈群",
		[]string{contactID},
	)
	bindSelectableGroupToCircle(t, circleConversationID, circleID)
	handler := newSelectableGroupHandlerWithRelationshipGate(
		t,
		viewer,
		unavailableSelectableGroupGate{},
		contactID,
	)

	for _, path := range []string{
		"/chat/group-candidates?limit=20",
		"/chat/selectable-group-conversations?source=group&limit=50",
		"/chat/selectable-group-conversations?source=circle&limit=50",
		"/chat/selectable-group-conversations/" + circleConversationID +
			"/contact-members?limit=100",
	} {
		status, payload := getSelectableJSON(t, handler, path, viewer)
		if status != http.StatusInternalServerError {
			t.Fatalf(
				"%s status=%d want=%d payload=%#v",
				path,
				status,
				http.StatusInternalServerError,
				payload,
			)
		}
		if code := errorCodeOf(t, payload); code != "CHAT.SYSTEM.internal_error" {
			t.Fatalf(
				"%s code=%s want=CHAT.SYSTEM.internal_error payload=%#v",
				path,
				code,
				payload,
			)
		}
	}
}

// TestListSelectableGroupConversations_ReturnsGroupsWithFriendCount 验证图四群列表：
// 只返回含互关联系人的群，并给出准确的 friendMemberCount。
func TestListSelectableGroupConversations_ReturnsGroupsWithFriendCount(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	const viewer = "viewer_sg"
	mutual := map[string]bool{"friend_a": true, "friend_b": true}
	// 含 2 个互关好友 + 1 个非联系人成员 stranger_x。
	seedSelectableGroup(t, "conv_sg_with_friends", viewer, "周末登山群", []string{"friend_a", "friend_b", "stranger_x"})
	seedSelectableGroup(t, "conv_sg_circle", viewer, "摄影圈交流群", []string{"friend_a"})
	bindSelectableGroupToCircle(t, "conv_sg_circle", "circle_photo")
	// 无任何互关联系人成员，只有 stranger。
	seedSelectableGroup(t, "conv_sg_no_friends", viewer, "陌生人群", []string{"stranger_y"})

	handler := newSelectableGroupHandler(t, viewer, mutual, "friend_a", "friend_b")
	code, payload := getSelectableJSON(t, handler, "/chat/selectable-group-conversations?limit=50", viewer)
	if code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %#v", code, payload)
	}
	items, ok := payload["items"].([]any)
	if !ok {
		t.Fatalf("response missing items: %#v", payload)
	}
	if len(items) != 2 {
		t.Fatalf("expected exactly 2 groups with mutual friends, got %d: %#v", len(items), items)
	}
	rowsByID := map[string]map[string]any{}
	for _, item := range items {
		row := item.(map[string]any)
		rowsByID[row["conversationId"].(string)] = row
	}
	row := rowsByID["conv_sg_with_friends"]
	if got := int(row["friendMemberCount"].(float64)); got != 2 {
		t.Fatalf("expected friendMemberCount 2 (stranger excluded), got %d", got)
	}
	if got := rowsByID["conv_sg_circle"]["circleId"]; got != "circle_photo" {
		t.Fatalf("circle-bound row circleId=%v want=circle_photo", got)
	}

	code, payload = getSelectableJSON(
		t,
		handler,
		"/chat/selectable-group-conversations?source=group&limit=50",
		viewer,
	)
	if code != http.StatusOK {
		t.Fatalf("group source expected 200, got %d: %#v", code, payload)
	}
	items = payload["items"].([]any)
	if len(items) != 1 || items[0].(map[string]any)["conversationId"] != "conv_sg_with_friends" {
		t.Fatalf("group source leaked circle-bound rows: %#v", items)
	}

	code, payload = getSelectableJSON(
		t,
		handler,
		"/chat/selectable-group-conversations?source=circle&limit=50",
		viewer,
	)
	if code != http.StatusOK {
		t.Fatalf("circle source expected 200, got %d: %#v", code, payload)
	}
	items = payload["items"].([]any)
	if len(items) != 1 || items[0].(map[string]any)["conversationId"] != "conv_sg_circle" {
		t.Fatalf("circle source did not isolate circle-bound rows: %#v", items)
	}

	code, payload = getSelectableJSON(
		t,
		handler,
		"/chat/selectable-group-conversations?source=unsupported&limit=50",
		viewer,
	)
	if code != http.StatusBadRequest {
		t.Fatalf("invalid source expected 400, got %d: %#v", code, payload)
	}
	if payload["code"] != "CHAT.USER.invalid_argument" {
		t.Fatalf("invalid source must return structured invalid_argument: %#v", payload)
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
		"/chat/selectable-group-conversations/conv_sg_with_friends/contact-members?limit=100",
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
		if row["userHandle"] != "handle_"+row["userId"].(string) {
			t.Fatalf("expected canonical userHandle for selectable member, got %#v", row)
		}
		if _, ok := row["contactId"]; ok {
			t.Fatalf("selectable member must not expose retired contactId alias: %#v", row)
		}
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

func TestListSelectableGroupSources_KeysetPagination(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	const viewer = "viewer_selectable_page"
	mutual := make(map[string]bool, 51)
	contacts := make([]string, 0, 51)
	for index := 0; index < 51; index++ {
		id := fmt.Sprintf("friend_selectable_%03d", index)
		mutual[id] = true
		contacts = append(contacts, id)
		seedSelectableGroup(
			t,
			fmt.Sprintf("conversation_selectable_%03d", index),
			viewer,
			fmt.Sprintf("分页群 %03d", index),
			[]string{id},
		)
	}

	handler := newSelectableGroupHandler(t, viewer, mutual, contacts...)
	code, firstPage := getSelectableJSON(
		t,
		handler,
		"/chat/selectable-group-conversations?limit=50",
		viewer,
	)
	if code != http.StatusOK {
		t.Fatalf("first page expected 200, got %d: %#v", code, firstPage)
	}
	firstItems := firstPage["items"].([]any)
	if len(firstItems) != 50 {
		t.Fatalf("first page expected 50 items, got %d: %#v", len(firstItems), firstItems)
	}
	nextCursor, ok := firstPage["nextCursor"].(string)
	if !ok || nextCursor == "" {
		t.Fatalf("full first page must return nextCursor: %#v", firstPage)
	}

	code, secondPage := getSelectableJSON(
		t,
		handler,
		"/chat/selectable-group-conversations?limit=50&cursor="+nextCursor,
		viewer,
	)
	if code != http.StatusOK {
		t.Fatalf("second page expected 200, got %d: %#v", code, secondPage)
	}
	secondItems := secondPage["items"].([]any)
	if len(secondItems) != 1 {
		t.Fatalf("second page expected 1 remaining item, got %d: %#v", len(secondItems), secondItems)
	}
	if _, exists := secondPage["nextCursor"]; exists {
		t.Fatalf("terminal page must not advertise another cursor: %#v", secondPage)
	}
	seen := make(map[string]struct{}, 51)
	for _, raw := range append(firstItems, secondItems...) {
		id := raw.(map[string]any)["conversationId"].(string)
		if _, duplicate := seen[id]; duplicate {
			t.Fatalf("keyset pagination duplicated conversation %q", id)
		}
		seen[id] = struct{}{}
	}
	if len(seen) != 51 {
		t.Fatalf("keyset pagination omitted selectable groups: got=%d want=51", len(seen))
	}
}

func TestListSelectableGroupContactMembers_KeysetPaginationAndMembership(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	const viewer = "viewer_selectable_members_page"
	mutual := make(map[string]bool, 102)
	contacts := make([]string, 0, 102)
	for index := 0; index < 102; index++ {
		id := fmt.Sprintf("friend_member_%03d", index)
		mutual[id] = true
		contacts = append(contacts, id)
	}
	seedSelectableGroup(
		t,
		"conversation_member_pages",
		viewer,
		"可分页群成员",
		contacts,
	)
	handler := newSelectableGroupHandler(t, viewer, mutual, contacts...)

	code, firstPage := getSelectableJSON(
		t,
		handler,
		"/chat/selectable-group-conversations/conversation_member_pages/contact-members?limit=100",
		viewer,
	)
	if code != http.StatusOK {
		t.Fatalf("first member page expected 200, got %d: %#v", code, firstPage)
	}
	firstItems := firstPage["items"].([]any)
	if len(firstItems) != 100 {
		t.Fatalf("first member page expected 100 items, got %d", len(firstItems))
	}
	nextCursor, ok := firstPage["nextCursor"].(string)
	if !ok || nextCursor == "" {
		t.Fatalf("full member page must return nextCursor: %#v", firstPage)
	}

	code, secondPage := getSelectableJSON(
		t,
		handler,
		"/chat/selectable-group-conversations/conversation_member_pages/contact-members?limit=100&cursor="+nextCursor,
		viewer,
	)
	if code != http.StatusOK {
		t.Fatalf("second member page expected 200, got %d: %#v", code, secondPage)
	}
	secondItems := secondPage["items"].([]any)
	if len(secondItems) != 2 {
		t.Fatalf("second member page expected 2 remaining items, got %d", len(secondItems))
	}
	seen := make(map[string]struct{}, 102)
	for _, raw := range append(firstItems, secondItems...) {
		id := raw.(map[string]any)["userId"].(string)
		if _, duplicate := seen[id]; duplicate {
			t.Fatalf("keyset pagination duplicated member %q", id)
		}
		seen[id] = struct{}{}
	}
	if len(seen) != 102 {
		t.Fatalf("keyset pagination omitted mutual group members: got=%d want=102", len(seen))
	}

	code, payload := getSelectableJSON(
		t,
		handler,
		"/chat/selectable-group-conversations/conversation_member_pages/contact-members?limit=100",
		"not_a_member",
	)
	if code != http.StatusNotFound || payload["code"] != "CHAT.USER.conversation_not_found" {
		t.Fatalf("non-member must not enumerate group roster: code=%d payload=%#v", code, payload)
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
		"/chat/selectable-group-conversations/conv_missing/contact-members",
		viewer,
	)
	if code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d: %#v", code, payload)
	}
	if payload["code"] != "CHAT.USER.conversation_not_found" {
		t.Fatalf("expected CHAT.USER.conversation_not_found, got %#v", payload)
	}
}
