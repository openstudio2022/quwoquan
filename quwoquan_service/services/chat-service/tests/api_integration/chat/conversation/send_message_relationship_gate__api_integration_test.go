// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/conversation-entry-matrix/spec.md#gwt-001
package api_integration

import (
	"context"
	"testing"

	rterr "quwoquan_service/runtime/errors"
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
