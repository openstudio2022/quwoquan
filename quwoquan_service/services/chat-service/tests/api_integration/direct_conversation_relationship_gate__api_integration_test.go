package api_integration

import (
	"testing"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/chat-service/internal/application"
	chatcache "quwoquan_service/services/chat-service/internal/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

func newGateTestConversationService(t *testing.T, gate application.RelationshipGate) *application.ConversationService {
	t.Helper()
	store := persistence.NewMongoChatStore(requireMongoDB(t))
	cache := chatcache.NewConversationCache(redisRouter.Scene("general"))
	return application.NewConversationService(
		chatStoragePorts(store),
		cache,
		eventPublisherForContractTest(),
		testProfileResolver{},
		gate,
		nil,
		nil,
		groupAvatarSchedulerForContractTest(),
	)
}

func TestCreateConversation_Direct_RequiresMutualOrFormal(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	svc := newGateTestConversationService(t, relationshipGateForContractTest(
		t,
		application.RelationshipCapability{},
		nil,
	))

	_, err := svc.CreateConversation(commandOperationTestContext(), application.CreateConversationRequest{
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
	svc := newGateTestConversationService(t, relationshipGateForContractTest(
		t,
		application.RelationshipCapability{
			CanCreateDirectConversation: true,
			CanSendMessage:              true,
			IsMutual:                    true,
		},
		nil,
	))

	conv, err := svc.CreateConversation(commandOperationTestContext(), application.CreateConversationRequest{
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
	svc := newGateTestConversationService(t, relationshipGateForContractTest(
		t,
		application.RelationshipCapability{
			IsBlocked: true,
		},
		nil,
	))

	_, err := svc.CreateConversation(commandOperationTestContext(), application.CreateConversationRequest{
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
