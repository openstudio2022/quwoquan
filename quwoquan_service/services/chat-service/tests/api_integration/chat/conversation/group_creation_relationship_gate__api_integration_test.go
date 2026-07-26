// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/group-create-flow/spec.md#gwt-002
package api_integration

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	chatcache "quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/persistence"
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
	"conversation_memberships_command_receipts",
	"conversation_memberships_outbox",
	"conversation_user_states",
	"conversation_user_states_command_receipts",
	"conversation_user_states_outbox",
	"conversations_command_receipts",
	"conversations_outbox",
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
	return newGroupCreationConversationServiceWithScheduler(
		t,
		gate,
		groupAvatarSchedulerForContractTest(),
	)
}

func newGroupCreationConversationServiceWithScheduler(
	t *testing.T,
	gate application.RelationshipGate,
	scheduler application.GroupAvatarTaskScheduler,
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
		scheduler,
	)
}

type failingGroupAvatarTaskScheduler struct{}

func (failingGroupAvatarTaskScheduler) EnqueueRecompute(
	context.Context,
	application.GroupAvatarRecomputeTask,
) error {
	return errors.New("injected group avatar task enqueue failure")
}

func (failingGroupAvatarTaskScheduler) EnqueueConversationAvatarPatch(
	context.Context,
	application.ConversationAvatarPatchTask,
) error {
	return errors.New("injected group avatar patch enqueue failure")
}

func groupCreationCommandContext(idempotencyKey string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID:    "api_integration.group_create",
		IdempotencyKey: idempotencyKey,
		Actor: operation.ActorContext{
			AccountID: "user_a",
			PersonaID: "user_a",
		},
	})
}

func assertGroupCreationCollectionCount(
	t *testing.T,
	collection string,
	want int64,
) {
	t.Helper()
	got, err := requireGroupCreationMongoDB(t).Collection(collection).
		CountDocuments(context.Background(), bson.M{})
	if err != nil {
		t.Fatalf("count %s: %v", collection, err)
	}
	if got != want {
		t.Fatalf("%s documents=%d want=%d", collection, got, want)
	}
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

func TestCreateConversation_GroupReplaysSameIdempotencyKeyWithoutDuplicateFacts(
	t *testing.T,
) {
	t.Cleanup(func() { cleanGroupCreationCollections(t) })
	svc := newGroupCreationConversationService(
		t,
		relationshipGateForContractTest(t, mutualCapability(), nil),
	)
	ctx := groupCreationCommandContext("group-create-replay-key")
	req := application.CreateConversationRequest{
		Type:             "group",
		Title:            "幂等群",
		MaxGroupSize:     1000,
		CreatorId:        "user_a",
		InitialMemberIds: []string{"user_b", "user_c"},
	}

	created, err := svc.CreateConversation(ctx, req)
	if err != nil {
		t.Fatalf("create group: %v", err)
	}
	replayed, err := svc.CreateConversation(ctx, req)
	if err != nil {
		t.Fatalf("replay group creation: %v", err)
	}
	if created.ID != replayed.ID {
		t.Fatalf("replayed conversation=%s want=%s", replayed.ID, created.ID)
	}

	assertGroupCreationCollectionCount(t, "conversations", 1)
	assertGroupCreationCollectionCount(t, "conversation_memberships", 3)
	assertGroupCreationCollectionCount(t, "conversation_user_states", 3)
	assertGroupCreationCollectionCount(t, "conversations_command_receipts", 1)
	assertGroupCreationCollectionCount(t, "conversations_outbox", 2)
}

func TestCreateConversation_GroupConcurrentReplaysReturnFirstConversation(t *testing.T) {
	t.Cleanup(func() { cleanGroupCreationCollections(t) })
	svc := newGroupCreationConversationService(
		t,
		relationshipGateForContractTest(t, mutualCapability(), nil),
	)
	ctx := groupCreationCommandContext("group-create-concurrent-replay-key")
	req := application.CreateConversationRequest{
		Type:             "group",
		Title:            "并发幂等群",
		MaxGroupSize:     1000,
		CreatorId:        "user_a",
		InitialMemberIds: []string{"user_b", "user_c"},
	}

	type createResult struct {
		conversationID string
		err            error
	}
	start := make(chan struct{})
	results := make(chan createResult, 2)
	var workers sync.WaitGroup
	for worker := 0; worker < 2; worker++ {
		workers.Add(1)
		go func() {
			defer workers.Done()
			<-start
			created, err := svc.CreateConversation(ctx, req)
			result := createResult{err: err}
			if created != nil {
				result.conversationID = created.ID
			}
			results <- result
		}()
	}
	close(start)
	workers.Wait()
	close(results)

	var conversationIDs []string
	for result := range results {
		if result.err != nil {
			t.Fatalf("concurrent group creation: %v", result.err)
		}
		if result.conversationID == "" {
			t.Fatal("concurrent group creation returned empty conversation id")
		}
		conversationIDs = append(conversationIDs, result.conversationID)
	}
	if len(conversationIDs) != 2 || conversationIDs[0] != conversationIDs[1] {
		t.Fatalf("concurrent replay ids=%v, want one shared conversation id", conversationIDs)
	}
	assertGroupCreationCollectionCount(t, "conversations", 1)
	assertGroupCreationCollectionCount(t, "conversation_memberships", 3)
	assertGroupCreationCollectionCount(t, "conversation_user_states", 3)
	assertGroupCreationCollectionCount(t, "conversations_command_receipts", 1)
	assertGroupCreationCollectionCount(t, "conversations_outbox", 2)
}

func TestCreateConversation_GroupRejectsSameKeyWithDifferentPayload(t *testing.T) {
	t.Cleanup(func() { cleanGroupCreationCollections(t) })
	svc := newGroupCreationConversationService(
		t,
		relationshipGateForContractTest(t, mutualCapability(), nil),
	)
	ctx := groupCreationCommandContext("group-create-conflicting-replay-key")
	req := application.CreateConversationRequest{
		Type:             "group",
		Title:            "首次群名",
		MaxGroupSize:     1000,
		CreatorId:        "user_a",
		InitialMemberIds: []string{"user_b"},
	}
	if _, err := svc.CreateConversation(ctx, req); err != nil {
		t.Fatalf("create first group: %v", err)
	}
	req.Title = "冲突群名"
	_, err := svc.CreateConversation(ctx, req)
	appErr, ok := err.(*rterr.AppError)
	if !ok {
		t.Fatalf("expected idempotency conflict AppError, got %T (%v)", err, err)
	}
	if got := appErr.Code.String(); got != "CHAT.USER.conversation_idempotency_conflict" {
		t.Fatalf("code=%q want=CHAT.USER.conversation_idempotency_conflict", got)
	}
	assertGroupCreationCollectionCount(t, "conversations", 1)
	assertGroupCreationCollectionCount(t, "conversations_command_receipts", 1)
	assertGroupCreationCollectionCount(t, "conversations_outbox", 2)
}

func TestCreateConversation_GroupDeduplicatesInitialMembers(t *testing.T) {
	t.Cleanup(func() { cleanGroupCreationCollections(t) })
	svc := newGroupCreationConversationService(
		t,
		relationshipGateForContractTest(t, mutualCapability(), nil),
	)

	created, err := svc.CreateConversation(
		groupCreationCommandContext("group-create-dedupe-key"),
		application.CreateConversationRequest{
			Type:             "group",
			Title:            "去重群",
			MaxGroupSize:     1000,
			CreatorId:        "user_a",
			InitialMemberIds: []string{"user_a", "user_b", "user_b", "user_c"},
		},
	)
	if err != nil {
		t.Fatalf("create deduplicated group: %v", err)
	}
	if created.MemberCount != 3 {
		t.Fatalf("member count=%d want=3", created.MemberCount)
	}
	assertGroupCreationCollectionCount(t, "conversation_memberships", 3)
	assertGroupCreationCollectionCount(t, "conversation_user_states", 3)
}

func TestCreateConversation_GroupAllowsExactMaximumCapacity(t *testing.T) {
	t.Cleanup(func() { cleanGroupCreationCollections(t) })
	svc := newGroupCreationConversationService(
		t,
		relationshipGateForContractTest(t, mutualCapability(), nil),
	)
	initialMemberIDs := make([]string, 0, 999)
	for index := 0; index < 999; index++ {
		initialMemberIDs = append(initialMemberIDs, fmt.Sprintf("user_%04d", index))
	}

	created, err := svc.CreateConversation(
		groupCreationCommandContext("group-create-exact-capacity-key"),
		application.CreateConversationRequest{
			Type:             "group",
			Title:            "千人边界群",
			MaxGroupSize:     1000,
			CreatorId:        "user_a",
			InitialMemberIds: initialMemberIDs,
		},
	)
	if err != nil {
		t.Fatalf("create exact-capacity group: %v", err)
	}
	if created.MemberCount != 1000 {
		t.Fatalf("member count=%d want=1000", created.MemberCount)
	}
	assertGroupCreationCollectionCount(t, "conversations", 1)
	assertGroupCreationCollectionCount(t, "conversation_memberships", 1000)
	assertGroupCreationCollectionCount(t, "conversation_user_states", 1000)
	assertGroupCreationCollectionCount(t, "conversations_command_receipts", 1)
	assertGroupCreationCollectionCount(t, "conversations_outbox", 2)
}

func TestCreateConversation_GroupRejectsCapacityBeforeWritingFacts(t *testing.T) {
	t.Cleanup(func() { cleanGroupCreationCollections(t) })
	svc := newGroupCreationConversationService(
		t,
		relationshipGateForContractTest(t, mutualCapability(), nil),
	)
	initialMemberIDs := make([]string, 0, 1000)
	for index := 0; index < 1000; index++ {
		initialMemberIDs = append(initialMemberIDs, fmt.Sprintf("user_%04d", index))
	}

	_, err := svc.CreateConversation(
		groupCreationCommandContext("group-create-capacity-key"),
		application.CreateConversationRequest{
			Type:             "group",
			Title:            "容量群",
			MaxGroupSize:     1000,
			CreatorId:        "user_a",
			InitialMemberIds: initialMemberIDs,
		},
	)
	appErr, ok := err.(*rterr.AppError)
	if !ok {
		t.Fatalf("expected group_full AppError, got %T (%v)", err, err)
	}
	if got := appErr.Code.String(); got != "CHAT.USER.group_full" {
		t.Fatalf("code=%s want=CHAT.USER.group_full", got)
	}
	for _, collection := range []string{
		"conversations",
		"conversation_memberships",
		"conversation_user_states",
		"conversations_command_receipts",
		"conversations_outbox",
	} {
		assertGroupCreationCollectionCount(t, collection, 0)
	}
}

func TestCreateConversation_GroupRollsBackWhenDeferredTaskCannotCommit(t *testing.T) {
	t.Cleanup(func() { cleanGroupCreationCollections(t) })
	svc := newGroupCreationConversationServiceWithScheduler(
		t,
		relationshipGateForContractTest(t, mutualCapability(), nil),
		failingGroupAvatarTaskScheduler{},
	)

	_, err := svc.CreateConversation(
		groupCreationCommandContext("group-create-rollback-key"),
		application.CreateConversationRequest{
			Type:             "group",
			Title:            "回滚群",
			MaxGroupSize:     1000,
			CreatorId:        "user_a",
			InitialMemberIds: []string{"user_b"},
		},
	)
	if err == nil {
		t.Fatal("expected injected scheduler failure")
	}
	for _, collection := range []string{
		"conversations",
		"conversation_memberships",
		"conversation_user_states",
		"conversations_command_receipts",
		"conversations_outbox",
	} {
		assertGroupCreationCollectionCount(t, collection, 0)
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
