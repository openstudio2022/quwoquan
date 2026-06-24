package tests

import (
	"context"
	"testing"

	"github.com/alicebob/miniredis/v2"

	rtredis "quwoquan_service/runtime/redis"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/chat-service/internal/application"
	chatcache "quwoquan_service/services/chat-service/internal/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

type stubRelationshipGate struct {
	cap application.RelationshipCapability
	err error
}

func (g stubRelationshipGate) GetCapability(context.Context, string, string) (application.RelationshipCapability, error) {
	return g.cap, g.err
}

func newGateTestConversationService(t *testing.T, gate application.RelationshipGate) *application.ConversationService {
	t.Helper()
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
	store := persistence.NewMongoChatStore(requireMongoDB(t))
	cache := chatcache.NewConversationCache(router.Scene("general"))
	return application.NewConversationService(store, cache, nil, testProfileResolver{}, gate, nil, nil, nil)
}

func TestCreateConversation_Direct_RequiresMutualOrFormal(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	svc := newGateTestConversationService(t, stubRelationshipGate{
		cap: application.RelationshipCapability{},
	})

	_, err := svc.CreateConversation(context.Background(), application.CreateConversationRequest{
		Type:             "direct",
		CreatorId:        "user_a",
		InitialMemberIds: []string{"user_b"},
	})
	if err == nil {
		t.Fatal("expected greeting/mutual gate error")
	}
	appErr, ok := err.(*rterr.AppError)
	if !ok {
		t.Fatalf("expected AppError, got %T (%v)", err, err)
	}
	if got := appErr.Code.String(); got != "CHAT.USER.greeting_required" {
		t.Fatalf("code = %q, want CHAT.USER.greeting_required", got)
	}
}

func TestCreateConversation_Direct_AllowsMutual(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	svc := newGateTestConversationService(t, stubRelationshipGate{
		cap: application.RelationshipCapability{
			CanCreateDirectConversation: true,
			CanSendMessage:              true,
			IsMutual:                    true,
		},
	})

	conv, err := svc.CreateConversation(context.Background(), application.CreateConversationRequest{
		Type:             "direct",
		CreatorId:        "user_a",
		InitialMemberIds: []string{"user_b"},
	})
	if err != nil {
		t.Fatalf("create direct conversation: %v", err)
	}
	if conv == nil || conv.ID == "" {
		t.Fatal("expected conversation id")
	}
}

func TestCreateConversation_Direct_Blocked(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	svc := newGateTestConversationService(t, stubRelationshipGate{
		cap: application.RelationshipCapability{
			IsBlocked: true,
		},
	})

	_, err := svc.CreateConversation(context.Background(), application.CreateConversationRequest{
		Type:             "direct",
		CreatorId:        "user_a",
		InitialMemberIds: []string{"user_b"},
	})
	if err == nil {
		t.Fatal("expected blocked gate error")
	}
	appErr, ok := err.(*rterr.AppError)
	if !ok {
		t.Fatalf("expected AppError, got %T (%v)", err, err)
	}
	if got := appErr.Code.String(); got != "CHAT.USER.blocked" {
		t.Fatalf("code = %q, want CHAT.USER.blocked", got)
	}
}
