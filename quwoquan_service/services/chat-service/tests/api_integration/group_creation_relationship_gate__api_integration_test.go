package api_integration

import (
	"context"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/chat-service/internal/application"
	chatcache "quwoquan_service/services/chat-service/internal/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

var groupCreationCollections = []string{
	"conversations",
	"messages",
	"messages_sequences",
	"messages_command_receipts",
	"messages_outbox",
	"messages_outbox_sequences",
	"messages_projection_checkpoints",
	"conversation_memberships",
	"conversation_user_states",
	"message_receipts",
	"reliable_task_outbox",
	"reliable_async_task",
	"notification_outbox",
	"notification_delivery_ledger",
}

func requireGroupCreationMongoDB(tb testing.TB) *mongo.Database {
	tb.Helper()
	return requireMongoDB(tb)
}

func cleanGroupCreationCollections(t *testing.T) {
	t.Helper()
	db := requireGroupCreationMongoDB(t)
	for _, name := range groupCreationCollections {
		_, _ = db.Collection(name).DeleteMany(context.Background(), bson.M{})
	}
}

type groupCreationProfileResolver struct{}

func (groupCreationProfileResolver) ResolveMany(
	_ context.Context,
	userIDs []string,
) (map[string]application.ProfileSnapshot, error) {
	out := make(map[string]application.ProfileSnapshot, len(userIDs))
	for _, id := range userIDs {
		out[id] = application.ProfileSnapshot{
			DisplayName:   "Display_" + id,
			AvatarURL:     "https://test.avatar/" + id,
			AvatarAssetID: "ua_" + id,
			AvatarVersion: 1,
			Bio:           "Bio_" + id,
		}
	}
	return out, nil
}

func mutualCapability() application.RelationshipCapability {
	return application.RelationshipCapability{
		CanCreateDirectConversation: true,
		CanSendMessage:              true,
		HasFormalConversation:       true,
		IsMutual:                    true,
	}
}

func newGroupCreationConversationService(
	t *testing.T,
	gate application.RelationshipGate,
) *application.ConversationService {
	t.Helper()
	store := persistence.NewMongoChatStore(requireGroupCreationMongoDB(t))
	cache := chatcache.NewConversationCache(redisRouter.Scene("general"))
	return application.NewConversationService(
		chatStoragePorts(store),
		cache,
		eventPublisherForContractTest(),
		groupCreationProfileResolver{},
		gate,
		nil,
		nil,
		groupAvatarSchedulerForContractTest(),
	)
}

func TestCreateConversation_Group_RequiresMutualMembers(t *testing.T) {
	t.Cleanup(func() { cleanGroupCreationCollections(t) })
	svc := newGroupCreationConversationService(t, relationshipGateForContractTest(
		t,
		application.RelationshipCapability{},
		nil,
	))

	_, err := svc.CreateConversation(commandOperationTestContext(), application.CreateConversationRequest{
		Type:             "group",
		Title:            "非互关群",
		MaxGroupSize:     500,
		CreatorId:        "user_a",
		InitialMemberIds: []string{"user_b", "user_c"},
	})
	if err == nil {
		t.Fatal("expected group_member_not_mutual gate error for non-mutual group member")
	}
	appErr, ok := err.(*rterr.AppError)
	if !ok {
		t.Fatalf("expected AppError, got %T (%v)", err, err)
	}
	if got := appErr.Code.String(); got != "CHAT.USER.group_member_not_mutual" {
		t.Fatalf("code = %q, want CHAT.USER.group_member_not_mutual", got)
	}
}

func TestCreateConversation_Group_BlockedMember(t *testing.T) {
	t.Cleanup(func() { cleanGroupCreationCollections(t) })
	svc := newGroupCreationConversationService(t, relationshipGateForContractTest(
		t,
		application.RelationshipCapability{IsBlocked: true},
		nil,
	))

	_, err := svc.CreateConversation(commandOperationTestContext(), application.CreateConversationRequest{
		Type:             "group",
		Title:            "拉黑群",
		MaxGroupSize:     500,
		CreatorId:        "user_a",
		InitialMemberIds: []string{"user_b"},
	})
	if err == nil {
		t.Fatal("expected group_member_blocked gate error for blocked group member")
	}
	appErr, ok := err.(*rterr.AppError)
	if !ok {
		t.Fatalf("expected AppError, got %T (%v)", err, err)
	}
	if got := appErr.Code.String(); got != "CHAT.USER.group_member_blocked" {
		t.Fatalf("code = %q, want CHAT.USER.group_member_blocked", got)
	}
}

func TestCreateConversation_Group_AllowsMutualMembers(t *testing.T) {
	t.Cleanup(func() { cleanGroupCreationCollections(t) })
	svc := newGroupCreationConversationService(
		t,
		relationshipGateForContractTest(t, mutualCapability(), nil),
	)

	conv, err := svc.CreateConversation(commandOperationTestContext(), application.CreateConversationRequest{
		Type:             "group",
		Title:            "互关群",
		MaxGroupSize:     500,
		CreatorId:        "user_a",
		InitialMemberIds: []string{"user_b", "user_c"},
	})
	if err != nil {
		t.Fatalf("create mutual group conversation: %v", err)
	}
	if conv == nil || conv.ID == "" {
		t.Fatal("expected conversation id")
	}
	if conv.MemberCount != 3 {
		t.Fatalf("member count = %d, want 3 (creator + 2 members)", conv.MemberCount)
	}
}

func TestCreateConversation_Group_MixedMembersRejectsNonMutual(t *testing.T) {
	t.Cleanup(func() { cleanGroupCreationCollections(t) })
	svc := newGroupCreationConversationService(t, relationshipGateForContractTest(
		t,
		application.RelationshipCapability{},
		map[string]application.RelationshipCapability{
			"user_b": mutualCapability(),
			"user_c": {},
		},
	))

	_, err := svc.CreateConversation(commandOperationTestContext(), application.CreateConversationRequest{
		Type:             "group",
		Title:            "混合群",
		MaxGroupSize:     500,
		CreatorId:        "user_a",
		InitialMemberIds: []string{"user_b", "user_c"},
	})
	if err == nil {
		t.Fatal("expected group_member_not_mutual gate error when any member is non-mutual")
	}
	appErr, ok := err.(*rterr.AppError)
	if !ok {
		t.Fatalf("expected AppError, got %T (%v)", err, err)
	}
	if got := appErr.Code.String(); got != "CHAT.USER.group_member_not_mutual" {
		t.Fatalf("code = %q, want CHAT.USER.group_member_not_mutual", got)
	}
}

func TestCreateConversationRejectsCircleBindingBeforeRelationshipGate(t *testing.T) {
	t.Cleanup(func() { cleanGroupCreationCollections(t) })
	svc := newGroupCreationConversationService(t, relationshipGateForContractTest(
		t,
		application.RelationshipCapability{},
		nil,
	))

	conv, err := svc.CreateConversation(commandOperationTestContext(), application.CreateConversationRequest{
		Type:             "group",
		Title:            "圈子群",
		CircleId:         "circle_001",
		CircleGroupId:    "circle_group_default_001",
		MaxGroupSize:     500,
		CreatorId:        "user_a",
		InitialMemberIds: []string{"user_b"},
	})
	if conv != nil {
		t.Fatalf("client-supplied Circle binding must not create a conversation: %+v", conv)
	}
	appErr, ok := err.(*rterr.AppError)
	if !ok {
		t.Fatalf("expected structured circle binding rejection, got %T (%v)", err, err)
	}
	if got := appErr.Code.String(); got != "CHAT.USER.circle_group_binding_write_forbidden" {
		t.Fatalf("code = %q, want CHAT.USER.circle_group_binding_write_forbidden", got)
	}
}
