// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/conversation-entry-matrix/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-002.t2
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-002.t4
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
	rterr "quwoquan_service/runtime/errors"
	chathttp "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/http"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	chatcache "quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/persistence"
)

func newGateTestMessageService(t *testing.T, gate application.RelationshipGate) (*application.ConversationService, *application.MessageService) {
	t.Helper()
	store := persistence.NewMongoChatStore(requireMongoDB(t))
	storage := chatStoragePorts(store)
	cache := chatcache.NewConversationCache(redisRouter.Scene("general"))
	convSvc := application.NewConversationService(
		storage,
		cache,
		eventPublisherForContractTest(),
		testProfileResolver{},
		application.AllowRelationshipGateForTest(),
		nil,
		nil,
		groupAvatarSchedulerForContractTest(),
	)
	msgSvc := application.NewMessageService(storage, cache, eventPublisherForContractTest(), gate, testMediaAssetDeliveryReader{})
	return convSvc, msgSvc
}

func TestSendMessage_Direct_RequiresRelationshipGate(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	convSvc, msgSvc := newGateTestMessageService(t, relationshipGateForContractTest(
		t,
		application.RelationshipCapability{},
		nil,
	))

	conv, err := convSvc.CreateOrReuseDirect(
		context.Background(), "sender_gate", "peer_gate",
		application.DirectConversationPromotion{})
	if err != nil {
		t.Fatalf("create conversation: %v", err)
	}

	_, err = msgSvc.SendMessage(context.Background(), application.SendMessageRequest{
		ConversationId: conv.ID,
		SenderId:       "sender_gate",
		Type:           "text",
		Content:        "hello",
		ClientMsgId:    "client_gate_1",
	})
	if err == nil {
		t.Fatal("expected send message gate error")
	}
	appErr, ok := err.(*rterr.AppError)
	if !ok {
		t.Fatalf("expected AppError, got %T (%v)", err, err)
	}
	if got := appErr.Code.String(); got != "CHAT.USER.not_mutual" {
		t.Fatalf("code = %q, want CHAT.USER.not_mutual", got)
	}
}

func TestSendMessage_Direct_AllowsFormalConversation(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	convSvc, msgSvc := newGateTestMessageService(t, relationshipGateForContractTest(
		t,
		application.RelationshipCapability{
			CanSendMessage:        true,
			HasFormalConversation: true,
		},
		nil,
	))

	conv, err := convSvc.CreateOrReuseDirect(
		context.Background(), "sender_ok", "peer_ok",
		application.DirectConversationPromotion{})
	if err != nil {
		t.Fatalf("create conversation: %v", err)
	}

	resp, err := msgSvc.SendMessage(context.Background(), application.SendMessageRequest{
		ConversationId: conv.ID,
		SenderId:       "sender_ok",
		Type:           "text",
		Content:        "hello",
		ClientMsgId:    "client_ok_1",
	})
	if err != nil {
		t.Fatalf("send message: %v", err)
	}
	if resp == nil || resp.MessageId == "" {
		t.Fatal("expected message id")
	}
}

func TestExistingDirectConversationRemainsReadableWhenRelationshipBecomesBlocked(
	t *testing.T,
) {
	for _, testCase := range []struct {
		name        string
		isBlocked   bool
		isBlockedBy bool
	}{
		{name: "sender_blocks_peer", isBlocked: true},
		{name: "peer_blocks_sender", isBlockedBy: true},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			t.Cleanup(func() { cleanAll(t) })
			var blocked atomic.Bool
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				if blocked.Load() {
					_ = json.NewEncoder(w).Encode(map[string]any{
						"relationState":               "not_following",
						"canCreateDirectConversation": false,
						"canSendMessage":              false,
						"hasFormalConversation":       true,
						"isBlocked":                   testCase.isBlocked,
						"isBlockedBy":                 testCase.isBlockedBy,
					})
					return
				}
				_ = json.NewEncoder(w).Encode(map[string]any{
					"relationState":               "mutual",
					"canCreateDirectConversation": true,
					"canSendMessage":              true,
					"hasFormalConversation":       true,
					"isBlocked":                   false,
					"isBlockedBy":                 false,
				})
			}))
			t.Cleanup(server.Close)

			gate := chathttp.NewUserRelationshipGate(server.URL, server.Client())
			convSvc, msgSvc := newGateTestMessageService(t, gate)
			conv, err := convSvc.CreateOrReuseDirect(
				context.Background(),
				"sender_retained",
				"peer_retained",
				application.DirectConversationPromotion{},
			)
			if err != nil {
				t.Fatalf("create existing direct conversation: %v", err)
			}
			if _, err := msgSvc.SendMessage(context.Background(), application.SendMessageRequest{
				ConversationId: conv.ID,
				SenderId:       "sender_retained",
				Type:           "text",
				Content:        "before block",
				ClientMsgId:    "before-block-1",
			}); err != nil {
				t.Fatalf("send before block: %v", err)
			}
			assertCollectionCount(t, "messages", bson.M{"conversationId": conv.ID}, 1)

			blocked.Store(true)
			retained, err := convSvc.GetConversation(context.Background(), conv.ID)
			if err != nil {
				t.Fatalf("read existing conversation after block: %v", err)
			}
			if retained == nil || retained.ID != conv.ID {
				t.Fatalf("retained conversation=%+v, want id=%s", retained, conv.ID)
			}

			_, err = msgSvc.SendMessage(context.Background(), application.SendMessageRequest{
				ConversationId: conv.ID,
				SenderId:       "sender_retained",
				Type:           "text",
				Content:        "after block",
				ClientMsgId:    "after-block-1",
			})
			if err == nil {
				t.Fatal("expected blocked relationship to reject a new message")
			}
			appErr, ok := err.(*rterr.AppError)
			if !ok {
				t.Fatalf("expected AppError, got %T (%v)", err, err)
			}
			if got := appErr.Code.String(); got != "CHAT.USER.blocked" {
				t.Fatalf("code = %q, want CHAT.USER.blocked", got)
			}
			assertCollectionCount(t, "messages", bson.M{"conversationId": conv.ID}, 1)
		})
	}
}
