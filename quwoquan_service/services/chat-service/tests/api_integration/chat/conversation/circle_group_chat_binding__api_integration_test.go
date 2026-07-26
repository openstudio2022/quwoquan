package api_integration

import (
	"context"
	"fmt"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/persistence"
)

func TestCircleGroupStreamProjectsBoundConversationLifecycle(t *testing.T) {
	cleanAll(t)
	ctx := context.Background()
	store := persistence.NewMongoChatStore(requireMongoDB(t))
	storage := chatStoragePorts(store)
	convCache := cache.NewConversationCache(redisRouter.Scene("general"))
	conversations := application.NewConversationService(
		storage,
		convCache,
		testEventPublisher,
		testProfileResolver{},
		testRelationshipGate,
		testGroupAvatarMedia,
		testUserSyncPublisher,
		testGroupAvatarScheduler,
	)
	members := application.NewMemberService(
		storage,
		convCache,
		testEventPublisher,
		testProfileResolver{},
		testGroupAvatarMedia,
		testUserSyncPublisher,
		testGroupAvatarScheduler,
		application.WithRelationshipGate(testRelationshipGate),
	)
	syncService := application.NewCircleGroupChatSyncService(conversations, members)
	failures := persistence.NewMongoCircleGroupChatSyncFailureStore(requireMongoDB(t))
	if err := failures.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	consumer, err := mq.NewCircleGroupChatSyncConsumer(
		redisRouter.Scene("general"),
		syncService,
		failures,
		"chat-circle-group-api-integration",
		nil,
		mq.CircleGroupChatSyncConsumerConfig{
			Stream:       mq.CircleGroupEventStream,
			Group:        "chat.circle_group_projection.api_integration",
			DLQ:          "events.circle.groups.chat-circle-group-api-integration.dlq",
			BatchSize:    10,
			MaxAttempts:  2,
			MinIdle:      0,
			PollInterval: time.Millisecond,
			ReadBlock:    0,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatal(err)
	}
	membershipConsumer, err := mq.NewCircleGroupChatSyncConsumer(
		redisRouter.Scene("general"),
		syncService,
		failures,
		"chat-circle-group-membership-api-integration",
		nil,
		mq.CircleGroupChatSyncConsumerConfig{
			Stream:       mq.CircleGroupMembershipEventStream,
			Group:        "chat.circle_group_membership_projection.api_integration",
			DLQ:          "events.circle.group-memberships.chat-api-integration.dlq",
			BatchSize:    10,
			MaxAttempts:  2,
			MinIdle:      0,
			PollInterval: time.Millisecond,
			ReadBlock:    0,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := membershipConsumer.EnsureGroup(ctx); err != nil {
		t.Fatal(err)
	}

	created := circleGroupStreamValues(
		"cg-created-1", "CircleGroupCreated", "group-1", "circle-1", 1,
		`"name":"摄影小组","createdByPersonaId":"owner-1","status":"active"`,
	)
	if _, err := redisRouter.Scene("general").XAdd(ctx, mq.CircleGroupEventStream, created); err != nil {
		t.Fatal(err)
	}
	if processed, err := consumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("provision bound conversation: processed=%d err=%v", processed, err)
	}
	conv, err := store.FindConversationByCircleGroupID(ctx, "group-1")
	if err != nil {
		t.Fatalf("bound conversation must be persisted: %v", err)
	}
	if conv.CircleId != "circle-1" || conv.CircleGroupId != "group-1" ||
		conv.Status != model.ConversationStatusActive {
		t.Fatalf("unexpected bound conversation: %+v", conv)
	}
	if _, err := store.FindMember(ctx, conv.ID, "owner-1"); err != nil {
		t.Fatalf("owner member must be atomically provisioned: %v", err)
	}
	if _, err := store.FindUserState(ctx, "owner-1", conv.ID); err != nil {
		t.Fatalf("owner inbox state must be atomically provisioned: %v", err)
	}

	activated := circleGroupStreamValues(
		"cgm-activated-1", "CircleGroupMembershipActivated", "group-1", "circle-1", 2,
		`"personaId":"member-1","role":"member","state":"active"`,
	)
	if _, err := redisRouter.Scene("general").XAdd(ctx, mq.CircleGroupMembershipEventStream, activated); err != nil {
		t.Fatal(err)
	}
	if processed, err := membershipConsumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("project active member: processed=%d err=%v", processed, err)
	}
	if _, err := store.FindMember(ctx, conv.ID, "member-1"); err != nil {
		t.Fatalf("activated circle member must gain Chat roster row: %v", err)
	}
	if _, err := store.FindUserState(ctx, "member-1", conv.ID); err != nil {
		t.Fatalf("activated circle member must gain Chat inbox row: %v", err)
	}

	left := circleGroupStreamValues(
		"cgm-left-1", "CircleGroupMembershipLeft", "group-1", "circle-1", 3,
		`"personaId":"member-1","state":"left"`,
	)
	if _, err := redisRouter.Scene("general").XAdd(ctx, mq.CircleGroupMembershipEventStream, left); err != nil {
		t.Fatal(err)
	}
	if processed, err := membershipConsumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("project terminal member state: processed=%d err=%v", processed, err)
	}
	if _, err := store.FindMember(ctx, conv.ID, "member-1"); err == nil {
		t.Fatal("left circle member must not remain in Chat roster")
	}
	if _, err := store.FindUserState(ctx, "member-1", conv.ID); err == nil {
		t.Fatal("left circle member must lose Chat inbox state")
	}

	archived := circleGroupStreamValues(
		"cg-archived-1", "CircleGroupArchived", "group-1", "circle-1", 4,
		`"status":"archived"`,
	)
	if _, err := redisRouter.Scene("general").XAdd(ctx, mq.CircleGroupEventStream, archived); err != nil {
		t.Fatal(err)
	}
	if processed, err := consumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("archive bound conversation: processed=%d err=%v", processed, err)
	}
	conv, err = store.FindConversationByCircleGroupID(ctx, "group-1")
	if err != nil {
		t.Fatal(err)
	}
	if conv.Status != model.ConversationStatusDissolved || conv.MemberCount != 0 {
		t.Fatalf("archive must terminally dissolve bound conversation: %+v", conv)
	}
	if _, err := store.FindUserState(ctx, "owner-1", conv.ID); err == nil {
		t.Fatal("archive must remove every member inbox state")
	}

	lateActivation := circleGroupStreamValues(
		"cgm-late-activation", "CircleGroupMembershipActivated", "group-1", "circle-1", 5,
		`"personaId":"member-2","role":"member","state":"active"`,
	)
	if _, err := redisRouter.Scene("general").XAdd(ctx, mq.CircleGroupMembershipEventStream, lateActivation); err != nil {
		t.Fatal(err)
	}
	if processed, err := membershipConsumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("late event must be accepted as no-op after archive: processed=%d err=%v", processed, err)
	}
	if _, err := store.FindMember(ctx, conv.ID, "member-2"); err == nil {
		t.Fatal("late membership event must not revive an archived conversation")
	}
}

func TestCircleGroupBindingIsUniquelyPersistedAcrossReplay(t *testing.T) {
	cleanAll(t)
	ctx := context.Background()
	store := persistence.NewMongoChatStore(requireMongoDB(t))
	// The unique storage constraint is the final guard against concurrent
	// consumer reclaim. This test verifies it with the real Mongo index rather
	// than a memory substitute.
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	_, err := requireMongoDB(t).Collection("conversations").InsertMany(ctx, []any{
		bson.M{"_id": "conv-a", "circleGroupId": "group-unique"},
		bson.M{"_id": "conv-b", "circleGroupId": "group-unique"},
	})
	if err == nil {
		t.Fatal("two conversations must never bind the same CircleGroup")
	}
}

func TestEnsureIndexesCreatesCurrentCircleGroupIndexIdempotently(t *testing.T) {
	ctx := context.Background()
	upgradeDB := mongoClient.Database("chat_circle_group_index_upgrade")
	t.Cleanup(func() {
		if err := upgradeDB.Drop(context.Background()); err != nil {
			t.Errorf("drop chat index upgrade test database: %v", err)
		}
	})
	conversations := upgradeDB.Collection("conversations")
	store := persistence.NewMongoChatStore(upgradeDB)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("create current circle group index: %v", err)
	}
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("replay current index assembly: %v", err)
	}
	cursor, err := conversations.Indexes().List(ctx)
	if err != nil {
		t.Fatalf("list upgraded conversation indexes: %v", err)
	}
	defer cursor.Close(ctx)
	var indexes []bson.M
	if err := cursor.All(ctx, &indexes); err != nil {
		t.Fatalf("decode upgraded conversation indexes: %v", err)
	}
	var target bson.M
	for _, index := range indexes {
		if index["name"] == "uq_conv_circle_group" {
			target = index
		}
	}
	if target == nil {
		t.Fatal("uq_conv_circle_group was not created")
	}
	if unique, ok := target["unique"].(bool); !ok || !unique {
		t.Fatalf("uq_conv_circle_group must be unique, got %#v", target["unique"])
	}
	if sparse, ok := target["sparse"].(bool); !ok || !sparse {
		t.Fatalf("uq_conv_circle_group must be sparse, got %#v", target["sparse"])
	}
}

func TestEnsureIndexesFailsClosedForDuplicateCircleGroupBindings(t *testing.T) {
	ctx := context.Background()
	upgradeDB := mongoClient.Database("chat_circle_group_index_duplicate")
	t.Cleanup(func() {
		if err := upgradeDB.Drop(context.Background()); err != nil {
			t.Errorf("drop duplicate chat index test database: %v", err)
		}
	})
	conversations := upgradeDB.Collection("conversations")
	if _, err := conversations.InsertMany(ctx, []any{
		bson.M{"_id": "duplicate-a", "circleGroupId": "group-duplicate"},
		bson.M{"_id": "duplicate-b", "circleGroupId": "group-duplicate"},
	}); err != nil {
		t.Fatalf("insert duplicate bindings before index assembly: %v", err)
	}

	err := persistence.NewMongoChatStore(upgradeDB).EnsureIndexes(ctx)
	if err == nil {
		t.Fatal("duplicate bindings must fail current unique-index assembly")
	}
	count, countErr := conversations.CountDocuments(
		ctx,
		bson.M{"circleGroupId": "group-duplicate"},
	)
	if countErr != nil || count != 2 {
		t.Fatalf("failed index assembly must preserve duplicate evidence: count=%d err=%v", count, countErr)
	}
}

func TestEnsureIndexesConvergesUnderConcurrentCurrentAssembly(t *testing.T) {
	ctx := context.Background()
	upgradeDB := mongoClient.Database("chat_circle_group_index_concurrent")
	t.Cleanup(func() {
		if err := upgradeDB.Drop(context.Background()); err != nil {
			t.Errorf("drop concurrent chat index test database: %v", err)
		}
	})
	var group sync.WaitGroup
	errs := make(chan error, 2)
	for range 2 {
		group.Add(1)
		go func() {
			defer group.Done()
			errs <- persistence.NewMongoChatStore(upgradeDB).EnsureIndexes(ctx)
		}()
	}
	group.Wait()
	close(errs)
	for err := range errs {
		if err != nil {
			t.Fatalf("concurrent EnsureIndexes must converge: %v", err)
		}
	}
}

func circleGroupStreamValues(
	eventID string,
	eventType string,
	groupID string,
	circleID string,
	version int,
	extraFields string,
) map[string]string {
	now := time.Now().UTC().Format(time.RFC3339Nano)
	return map[string]string{
		"eventId":          eventID,
		"eventType":        eventType,
		"aggregateType":    "CircleGroup",
		"aggregateId":      groupID,
		"aggregateVersion": fmt.Sprintf("%d", version),
		"payload": fmt.Sprintf(
			`{"groupId":%q,"version":%d,"circleId":%q,%s,"createdAt":%q,"updatedAt":%q}`,
			groupID, version, circleID, extraFields, now, now,
		),
		"occurredAt": now,
	}
}
