// 非破冰 1v1 会话头常驻交集摘要的读面组装契约：GetConversation 对
// direct 且无破冰快照的会话组装 ≤2 条云侧 ContactIntersectionFact；
// 携带破冰快照的会话与群会话为空数组；解析失败降级为空不阻断会话。
//
// spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/conversation-intersection-header/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/conversation-intersection-header/spec.md#gwt-001.t2
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	chathttp "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/http"
	chatapp "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	"quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	usermodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

type stubHeaderIntersectionResolver struct {
	summaries []chatapp.ContactIntersectionSummary
	err       error
}

func (r stubHeaderIntersectionResolver) ListContactIntersections(
	context.Context,
	string,
	string,
	int,
) ([]chatapp.ContactIntersectionSummary, error) {
	return r.summaries, r.err
}

func newIntersectionHeaderHandler(
	t *testing.T,
	resolver chatapp.ContactIntersectionResolver,
	conversation *model.Conversation,
	members ...*model.ConversationMember,
) http.Handler {
	t.Helper()
	store := newCircleGroupChatSyncMemoryStore()
	store.conversations[conversation.ID] = conversation
	for _, member := range members {
		store.members[conversation.ID+":"+member.UserId] = member
	}
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
	memberSvc := chatapp.NewMemberService(
		storage, noopCache{}, syncNoopEventPublisher{}, nil, nil, nil,
		syncNoopGroupAvatarScheduler{},
		chatapp.WithRelationshipGate(chatapp.AllowRelationshipGateForTest()),
		chatapp.WithContactIntersectionResolver(resolver),
	)
	handler := chathttp.NewChatHandler(conversations, nil, memberSvc, nil, nil)
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)
	return mux
}

func getConversationWire(t *testing.T, handler http.Handler, conversationID, personaID string) map[string]any {
	t.Helper()
	request := httptest.NewRequest(
		http.MethodGet,
		"/chat/conversations/"+conversationID,
		nil,
	)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{
			AccountID: personaID, PersonaID: personaID,
		}},
	))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("GET conversation status=%d body=%s", response.Code, response.Body.String())
	}
	var wire map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &wire); err != nil {
		t.Fatal(err)
	}
	return wire
}

func directMember(conversationID, userID string) *model.ConversationMember {
	return &model.ConversationMember{
		ID:             conversationID + ":" + userID,
		ConversationId: conversationID,
		UserId:         userID,
		MemberType:     "user",
		Role:           "member",
	}
}

func TestDirectConversationHeaderCarriesPersistentIntersectionFacts(t *testing.T) {
	conv := &model.Conversation{
		ID: "conv-header-1", Type: "direct", Status: "active",
	}
	resolver := stubHeaderIntersectionResolver{
		summaries: []chatapp.ContactIntersectionSummary{
			{
				IntersectionID: "in-1", SourceRef: "coWishlistedEntity",
				Dimension: "entity", PrimaryText: "你们都想去五彩池观星营地",
			},
			{
				IntersectionID: "in-2", SourceRef: "coExperiencedGathering",
				Dimension: "gathering", PrimaryText: "一起参加过周末观星聚会",
			},
			{
				IntersectionID: "in-3", SourceRef: "coWishlistedEntity",
				Dimension: "entity", PrimaryText: "第三条必须被折叠掉",
			},
		},
	}
	handler := newIntersectionHeaderHandler(
		t, resolver, conv,
		directMember(conv.ID, "persona-viewer"),
		directMember(conv.ID, "persona-peer"),
	)

	wire := getConversationWire(t, handler, conv.ID, "persona-viewer")
	facts, _ := wire["intersectionFacts"].([]any)
	if len(facts) != 2 {
		t.Fatalf("persistent intersection facts must cap at 2, got %d: %#v", len(facts), wire["intersectionFacts"])
	}
	first := facts[0].(map[string]any)
	if first["primaryText"] != "你们都想去五彩池观星营地" ||
		first["kind"] != "coWishlistedEntity" {
		t.Fatalf("fact must carry the cloud primary text verbatim: %#v", first)
	}
}

func TestGreetingOriginConversationKeepsSnapshotAndSkipsPersistentFacts(t *testing.T) {
	conv := &model.Conversation{
		ID: "conv-header-2", Type: "direct", Status: "active",
		OriginIntersectionSnapshot: &usermodel.GreetingIntersectionSnapshot{
			PrimaryText: "破冰依据原文",
		},
	}
	handler := newIntersectionHeaderHandler(
		t,
		stubHeaderIntersectionResolver{
			summaries: []chatapp.ContactIntersectionSummary{{
				IntersectionID: "in-x", SourceRef: "coWishlistedEntity",
				Dimension: "entity", PrimaryText: "不该出现",
			}},
		},
		conv,
		directMember(conv.ID, "persona-viewer"),
		directMember(conv.ID, "persona-peer"),
	)

	wire := getConversationWire(t, handler, conv.ID, "persona-viewer")
	if facts, _ := wire["intersectionFacts"].([]any); len(facts) != 0 {
		t.Fatalf("greeting-origin conversation must keep snapshot only: %#v", facts)
	}
	if wire["originIntersectionSnapshot"] == nil {
		t.Fatal("origin snapshot must stay on the wire")
	}
}

func TestResolverFailureDegradesToEmptyFactsWithoutBlocking(t *testing.T) {
	conv := &model.Conversation{
		ID: "conv-header-3", Type: "direct", Status: "active",
	}
	handler := newIntersectionHeaderHandler(
		t,
		stubHeaderIntersectionResolver{err: errors.New("intersection upstream unavailable")},
		conv,
		directMember(conv.ID, "persona-viewer"),
		directMember(conv.ID, "persona-peer"),
	)

	wire := getConversationWire(t, handler, conv.ID, "persona-viewer")
	if facts, _ := wire["intersectionFacts"].([]any); len(facts) != 0 {
		t.Fatalf("resolver failure must degrade to empty facts: %#v", facts)
	}
}
