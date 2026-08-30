// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/conversation-entry-matrix/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/conversation-entry-matrix/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/conversation-entry-matrix/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/conversation-entry-matrix/spec.md#gwt-001.t3
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-002.t2
package api_integration

import (
	"testing"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	chatcache "quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/persistence"
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

func TestCreateConversation_Direct_BlockedInEitherDirection(t *testing.T) {
	for _, testCase := range []struct {
		name       string
		capability application.RelationshipCapability
	}{
		{
			name:       "creator_blocks_peer",
			capability: application.RelationshipCapability{IsBlocked: true},
		},
		{
			name:       "peer_blocks_creator",
			capability: application.RelationshipCapability{IsBlockedBy: true},
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			t.Cleanup(func() { cleanAll(t) })
			svc := newGateTestConversationService(t, relationshipGateForContractTest(
				t,
				testCase.capability,
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
		})
	}
}
