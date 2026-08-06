// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
// readiness_case: list-conversations-local
// readiness_case: list-conversation-timestamps-local
// readiness_case: create-conversation-local
// readiness_case: batch-get-conversations-local
// readiness_case: get-conversation-local
// readiness_case: update-conversation-title-local
// readiness_case: update-announcement-local
// readiness_case: update-group-governance-settings-local
// readiness_case: dissolve-conversation-local
// readiness_case: list-message-home-local
// readiness_case: list-contacts-local
// readiness_case: list-contact-home-local
// readiness_case: get-group-home-local
// readiness_case: list-group-candidates-local
// readiness_case: list-selectable-group-conversations-local
// readiness_case: list-selectable-group-contact-members-local
package local_contract

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sort"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	chathttp "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/http"
	chatapp "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	chatmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

func (store *circleGroupChatSyncMemoryStore) FindConversationsByIDs(_ context.Context, ids []string) ([]chatmodel.Conversation, error) {
	items := make([]chatmodel.Conversation, 0, len(ids))
	for _, id := range ids {
		if item := store.conversations[id]; item != nil {
			items = append(items, *item)
		}
	}
	return items, nil
}

func (*circleGroupChatSyncMemoryStore) ListGroupConversationsNeedingAvatar(context.Context, int) ([]chatmodel.Conversation, error) {
	return nil, nil
}

func (store *circleGroupChatSyncMemoryStore) UpdateMemberAvatarSnapshot(_ context.Context, conversationID, userID, avatarURL, avatarAssetID string, avatarVersion int64) error {
	member, err := store.FindMember(context.Background(), conversationID, userID)
	if err != nil {
		return err
	}
	member.AvatarUrl, member.AvatarAssetId, member.AvatarVersion = avatarURL, avatarAssetID, avatarVersion
	store.members[store.memberKey(conversationID, userID)] = member
	return nil
}

func (store *circleGroupChatSyncMemoryStore) FindAssistantMember(_ context.Context, conversationID string) (*chatmodel.ConversationMember, error) {
	for _, member := range store.members {
		if member.ConversationId == conversationID && member.MemberType == "assistant" {
			copy := *member
			return &copy, nil
		}
	}
	return nil, chatmodel.ErrMemberNotFound
}

func (store *circleGroupChatSyncMemoryStore) ListSharedConversationIDs(_ context.Context, memberA, memberB string) ([]string, error) {
	result := []string{}
	for id := range store.conversations {
		if store.members[store.memberKey(id, memberA)] != nil && store.members[store.memberKey(id, memberB)] != nil {
			result = append(result, id)
		}
	}
	sort.Strings(result)
	return result, nil
}

func (store *circleGroupChatSyncMemoryStore) ListUserStatePage(_ context.Context, userID string, limit int, _ string) (chatmodel.ConversationUserStatePage, error) {
	items, _ := store.ListUserStates(context.Background(), userID, limit, "")
	return chatmodel.ConversationUserStatePage{Items: items}, nil
}

func (store *circleGroupChatSyncMemoryStore) ListUserStates(_ context.Context, userID string, limit int, _ string) ([]chatmodel.ConversationUserState, error) {
	items := []chatmodel.ConversationUserState{}
	for _, state := range store.states {
		if state.UserId == userID {
			items = append(items, *state)
		}
	}
	sort.Slice(items, func(i, j int) bool { return items[i].ConversationId < items[j].ConversationId })
	if limit > 0 && len(items) > limit {
		items = items[:limit]
	}
	return items, nil
}

func (store *circleGroupChatSyncMemoryStore) ListUserStatesByConversationID(ctx context.Context, userID string, limit int, after string) ([]chatmodel.ConversationUserState, error) {
	items, _ := store.ListUserStates(ctx, userID, 0, "")
	filtered := items[:0]
	for _, item := range items {
		if item.ConversationId > after {
			filtered = append(filtered, item)
		}
	}
	if limit > 0 && len(filtered) > limit {
		filtered = filtered[:limit]
	}
	return filtered, nil
}

func (*circleGroupChatSyncMemoryStore) AdvanceInboxUnread(context.Context, string, string, int64, int, int, time.Time) error {
	return nil
}

type operationReadinessInbox struct {
	store *circleGroupChatSyncMemoryStore
}

func (reader operationReadinessInbox) ListInboxPage(ctx context.Context, request chatapp.ListInboxRequest) (chatapp.InboxPage, error) {
	states, _ := reader.store.ListUserStates(ctx, request.UserId, request.Limit, request.Cursor)
	items := make([]chatapp.InboxItem, 0, len(states))
	for _, state := range states {
		conversation, err := reader.store.FindConversationByID(ctx, state.ConversationId)
		if err == nil {
			items = append(items, chatapp.InboxItem{Conversation: *conversation, UserState: state})
		}
	}
	return chatapp.InboxPage{Items: items}, nil
}

type operationReadinessSocial struct{}

func (operationReadinessSocial) ListContacts(context.Context, string, int) ([]chatapp.SocialContactSeed, error) {
	return []chatapp.SocialContactSeed{{UserID: "persona-friend", DisplayName: "Friend", RelationState: "mutual", Source: "follow"}}, nil
}
func (operationReadinessSocial) ListContactPage(context.Context, string, int, string) (chatapp.SocialContactPage, error) {
	return chatapp.SocialContactPage{Items: []chatapp.SocialContactSeed{{UserID: "persona-friend", DisplayName: "Friend", RelationState: "mutual", Source: "follow"}}}, nil
}

type operationReadinessCircles struct{}

func (operationReadinessCircles) ListCircles(context.Context, string, int) ([]chatapp.ContactHomeCircleHit, error) {
	return []chatapp.ContactHomeCircleHit{{CircleID: "circle-1", DisplayName: "Circle"}}, nil
}

type operationReadinessAnnouncement struct{}

func (operationReadinessAnnouncement) SendAnnouncementSystemMessage(context.Context, string, string, string, string) error {
	return nil
}

func TestConversationProductionRoutesExecuteAllPublicApplicationFacets(t *testing.T) {
	store := newCircleGroupChatSyncMemoryStore()
	commands := newMemoryAggregateCommandStore()
	storage := chatapp.ChatStoragePorts{
		Transactions: passthroughTransactionRunner{}, Conversations: store,
		GatheringConversations: store, Members: store, RosterProjection: store,
		UserStates: store, ConversationCommands: commands,
		MembershipCommands: commands, UserStateCommands: commands,
	}
	conversations := chatapp.NewConversationService(
		storage, noopCache{}, syncNoopEventPublisher{}, nil,
		chatapp.AllowRelationshipGateForTest(), nil, nil, syncNoopGroupAvatarScheduler{},
	)
	conversations.SetAnnouncementMessageSender(operationReadinessAnnouncement{})
	members := chatapp.NewMemberService(
		storage, noopCache{}, syncNoopEventPublisher{}, nil, nil, nil,
		syncNoopGroupAvatarScheduler{},
		chatapp.WithRelationshipGate(chatapp.AllowRelationshipGateForTest()),
		chatapp.WithSocialContactResolver(operationReadinessSocial{}),
		chatapp.WithCircleListResolver(operationReadinessCircles{}),
	)
	inbox := chatapp.NewInboxService(operationReadinessInbox{store: store})
	handler := chathttp.NewChatHandler(conversations, nil, members, inbox, nil)
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)
	sequence := 0
	call := func(method, path, body string, want int) map[string]any {
		t.Helper()
		sequence++
		request := httptest.NewRequest(method, path, strings.NewReader(body))
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{Actor: operation.ActorContext{AccountID: "account-owner", PersonaID: "persona-owner"}}))
		request = request.WithContext(operation.WithContext(request.Context(), operation.Context{IdempotencyKey: "conversation-readiness-" + time.Now().Add(time.Duration(sequence)*time.Nanosecond).Format("150405.000000000"), Actor: operation.ActorContext{AccountID: "account-owner", PersonaID: "persona-owner"}}))
		response := httptest.NewRecorder()
		mux.ServeHTTP(response, request)
		if response.Code != want {
			t.Fatalf("%s %s status=%d want=%d body=%s", method, path, response.Code, want, response.Body.String())
		}
		return map[string]any{"body": response.Body.String()}
	}
	created := call(http.MethodPost, "/chat/conversations", `{"type":"group","title":"Readiness","initialMemberIds":["persona-friend"]}`, http.StatusCreated)
	_ = created
	var conversationID string
	for id := range store.conversations {
		conversationID = id
		break
	}
	if conversationID == "" {
		t.Fatal("CreateConversation did not persist the aggregate")
	}
	call(http.MethodGet, "/chat/conversations?limit=20", "", http.StatusOK)
	call(http.MethodGet, "/chat/conversations/timestamps", "", http.StatusOK)
	call(http.MethodPost, "/chat/conversations/batch", `{"ids":["`+conversationID+`"]}`, http.StatusOK)
	call(http.MethodGet, "/chat/conversations/"+conversationID, "", http.StatusOK)
	call(http.MethodPatch, "/chat/conversations/"+conversationID, `{"title":"Renamed"}`, http.StatusOK)
	call(http.MethodPatch, "/chat/conversations/"+conversationID+"/announcement", `{"announcement":"Meet at noon"}`, http.StatusOK)
	call(http.MethodPatch, "/chat/conversations/"+conversationID+"/governance", `{"nameEditableByAdminOnly":true}`, http.StatusOK)
	call(http.MethodGet, "/chat/message-home", "", http.StatusOK)
	call(http.MethodGet, "/chat/contacts", "", http.StatusOK)
	call(http.MethodGet, "/chat/contact-home", "", http.StatusOK)
	call(http.MethodGet, "/chat/groups/"+conversationID+"/home", "", http.StatusOK)
	call(http.MethodGet, "/chat/group-candidates?conversationId="+conversationID, "", http.StatusOK)
	call(http.MethodGet, "/chat/selectable-group-conversations", "", http.StatusOK)
	call(http.MethodGet, "/chat/selectable-group-conversations/"+conversationID+"/contact-members", "", http.StatusOK)
	call(http.MethodDelete, "/chat/conversations/"+conversationID, "", http.StatusOK)
}
