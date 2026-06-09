package tests

import (
	"context"
	"testing"

	"github.com/alicebob/miniredis/v2"

	rterr "quwoquan_service/runtime/errors"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/chat-service/internal/application"
	chatcache "quwoquan_service/services/chat-service/internal/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

func newGateTestMessageService(t *testing.T, gate application.RelationshipGate) (*application.ConversationService, *application.MessageService) {
	t.Helper()
	if mongoDB == nil {
		t.Skip("MongoDB unavailable")
	}
	mr, err := miniredis.Run()
	if err != nil {
		t.Fatalf("miniredis: %v", err)
	}
	t.Cleanup(mr.Close)
	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {Mode: "standalone", Addr: mr.Addr()},
		},
		DefaultScene: "general",
	})
	t.Cleanup(func() { _ = router.Close() })
	store := persistence.NewMongoChatStore(mongoDB)
	cache := chatcache.NewConversationCache(router.Scene("general"))
	convSvc := application.NewConversationService(store, cache, nil, testProfileResolver{}, application.AllowRelationshipGateForTest(), nil, nil, nil)
	msgSvc := application.NewMessageService(store, cache, nil, gate)
	return convSvc, msgSvc
}

func TestSendMessage_Direct_RequiresRelationshipGate(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	convSvc, msgSvc := newGateTestMessageService(t, stubRelationshipGate{
		cap: application.RelationshipCapability{},
	})

	conv, err := convSvc.CreateOrReuseDirect(context.Background(), "sender_gate", "peer_gate")
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
	convSvc, msgSvc := newGateTestMessageService(t, stubRelationshipGate{
		cap: application.RelationshipCapability{
			CanSendMessage:        true,
			HasFormalConversation: true,
		},
	})

	conv, err := convSvc.CreateOrReuseDirect(context.Background(), "sender_ok", "peer_ok")
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
