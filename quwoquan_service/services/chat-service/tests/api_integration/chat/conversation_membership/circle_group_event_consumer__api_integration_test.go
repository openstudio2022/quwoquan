// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-001
// readiness_case: project-circle-group-membership-api
package api_integration

import (
	"context"
	"fmt"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
	conversationapp "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	conversationpersistence "quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/persistence"
	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
	membershipmodel "quwoquan_service/services/chat-service/internal/chat/conversation_membership/domain/model"
	userstatepersistence "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/infrastructure/persistence"
)

type membershipProjectionBackend struct {
	projector conversationapp.CircleGroupChatSyncProjector
}

func (backend membershipProjectionBackend) ProjectCircleGroupMembership(
	ctx context.Context,
	fact membershipapp.CircleGroupMembershipFact,
) error {
	return backend.projector.Apply(ctx, conversationapp.CircleGroupChatSourceEvent{
		EventID: fact.EventID, EventType: fact.EventType, GroupID: fact.GroupID,
		CircleID: fact.CircleID, Version: fact.Version, UserID: fact.UserID,
		Role: fact.Role, State: fact.State, OccurredAt: fact.OccurredAt,
	})
}

type membershipConsumerProjector struct {
	handler *membershipapp.CircleGroupMembershipProjectionHandler
}

func (projector membershipConsumerProjector) Apply(
	ctx context.Context,
	event conversationapp.CircleGroupChatSourceEvent,
) error {
	return projector.handler.Apply(ctx, membershipapp.CircleGroupMembershipFact{
		EventID: event.EventID, EventType: event.EventType, GroupID: event.GroupID,
		CircleID: event.CircleID, Version: event.Version, UserID: event.UserID,
		Role: event.Role, State: event.State, OccurredAt: event.OccurredAt,
	})
}

func TestCircleGroupMembershipConsumerCommitsStateAndAcksWithRealProviders(t *testing.T) {
	ctx := context.Background()
	for _, collection := range []string{
		"conversations", "conversation_memberships", "conversation_user_states",
		"conversation_memberships_outbox", "conversation_memberships_command_receipts",
		"chat_aggregate_outbox_sequences", "circle_group_membership_projection_states",
		"circle_group_chat_binding_projection_states", "circle_group_chat_sync_failures",
	} {
		if _, err := membershipMongoDatabase.Collection(collection).DeleteMany(ctx, bson.M{}); err != nil {
			t.Fatal(err)
		}
	}
	chatStore := conversationpersistence.NewMongoChatStore(membershipMongoDatabase)
	if err := chatStore.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	userStates := userstatepersistence.NewMongoStore(membershipMongoDatabase)
	if err := userStates.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	membershipCommands := conversationpersistence.NewMongoAggregateCommandStore(
		membershipMongoDatabase,
		"conversation_memberships_command_receipts",
		"conversation_memberships_outbox",
	)
	if err := membershipCommands.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	failures := conversationpersistence.NewMongoCircleGroupChatSyncFailureStore(membershipMongoDatabase)
	if err := failures.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC().Truncate(time.Millisecond)
	conversation := &conversationmodel.Conversation{
		ID: "conversation-circle-readiness", Type: "group", Status: conversationmodel.ConversationStatusActive,
		CircleId: "circle-readiness", CircleGroupId: "group-readiness", CreatorId: "owner-readiness",
		MaxGroupSize: 1000, MemberCount: 1, MembersRosterRevision: 1, CreatedAt: now, UpdatedAt: now,
	}
	if err := chatStore.CreateConversation(ctx, conversation); err != nil {
		t.Fatal(err)
	}
	if err := membershipStore.CreateMember(ctx, &membershipmodel.Member{
		ID: "membership-owner-readiness", ConversationId: conversation.ID, UserId: conversation.CreatorId,
		MemberType: "user", Role: "owner", JoinedAt: now,
	}); err != nil {
		t.Fatal(err)
	}
	if err := chatStore.SaveCircleGroupChatBindingProjection(ctx, conversationapp.CircleGroupChatBindingProjectionState{
		CircleGroupID: conversation.CircleGroupId, CircleID: conversation.CircleId,
		SourceVersion: 1, Status: "active", LastEventID: "group-created-readiness", UpdatedAt: now,
	}); err != nil {
		t.Fatal(err)
	}
	ports := conversationapp.ChatStoragePorts{
		Transactions: chatStore, Conversations: chatStore, CircleGroupConversations: chatStore,
		Members: membershipStore, RosterProjection: chatStore, UserStates: userStates,
		MembershipCommands:                membershipCommands,
		CircleGroupMembershipProjections:  chatStore,
		CircleGroupChatBindingProjections: chatStore,
	}
	scheduler := circleGroupMembershipAPIScheduler{}
	conversations := conversationapp.NewConversationService(
		ports, circleGroupMembershipAPICache{}, circleGroupMembershipAPIPublisher{},
		nil, nil, nil, nil, scheduler,
	)
	members := conversationapp.NewMemberService(
		ports, circleGroupMembershipAPICache{}, circleGroupMembershipAPIPublisher{},
		nil, nil, nil, scheduler,
	)

	redisRuntime, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		t.Fatalf("start real Redis: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := redisRuntime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real Redis: %v", closeErr)
		}
	})
	if err := redisRuntime.FlushDBs(ctx, 0); err != nil {
		t.Fatal(err)
	}
	router := platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode: "standalone", Addr: redisRuntime.Addr, Password: redisRuntime.Password,
				DB: 0, TLS: redisRuntime.TLS,
			},
		},
		DefaultScene: "general",
	})
	t.Cleanup(func() {
		if closeErr := router.Close(); closeErr != nil {
			t.Errorf("close Redis router: %v", closeErr)
		}
	})
	redisClient := router.Scene("general")
	config := mq.DefaultCircleGroupMembershipConsumerConfig()
	config.Group = "chat-conversation-membership-readiness-api"
	config.DLQ = "events.circle.group-memberships.readiness-api.dlq"
	config.MinIdle = 0
	config.ReadBlock = 0
	consumer, err := mq.NewCircleGroupChatSyncConsumer(
		redisClient,
		membershipConsumerProjector{handler: membershipapp.NewCircleGroupMembershipProjectionHandler(
			membershipProjectionBackend{
				projector: conversationapp.NewCircleGroupConversationProjectionHandler(conversations, members),
			},
		)},
		failures,
		"readiness-api-runner",
		nil,
		config,
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatal(err)
	}
	eventID := "circle-membership-readiness-active-2"
	if _, err := redisClient.XAdd(ctx, mq.CircleGroupMembershipEventStream, map[string]string{
		"eventId": eventID, "eventType": "CircleGroupMembershipActivated",
		"aggregateType": "CircleGroupMembership", "aggregateId": "group-readiness:persona-readiness",
		"aggregateVersion": "2", "occurredAt": now.Format(time.RFC3339Nano),
		"payload": fmt.Sprintf(
			`{"groupId":%q,"version":2,"circleId":%q,"personaId":%q,"role":"member","state":"active"}`,
			conversation.CircleGroupId, conversation.CircleId, "persona-readiness",
		),
	}); err != nil {
		t.Fatal(err)
	}
	if processed, err := consumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("ProcessOnce() processed=%d error=%v", processed, err)
	}
	if _, err := membershipStore.FindMember(ctx, conversation.ID, "persona-readiness"); err != nil {
		t.Fatalf("projected membership missing: %v", err)
	}
	if _, err := userStates.FindUserState(ctx, "persona-readiness", conversation.ID); err != nil {
		t.Fatalf("projected user state missing: %v", err)
	}
	state, found, err := chatStore.LoadCircleGroupMembershipProjection(
		ctx, conversation.CircleGroupId, "persona-readiness",
	)
	if err != nil || !found || state.SourceVersion != 2 || state.LastEventID != eventID {
		t.Fatalf("projection checkpoint=%+v found=%v error=%v", state, found, err)
	}
	if count, err := membershipMongoDatabase.Collection("conversation_memberships_outbox").CountDocuments(
		ctx, bson.M{"eventType": "ConversationMemberAdded"},
	); err != nil || count != 1 {
		t.Fatalf("membership outbox count=%d error=%v", count, err)
	}
	pending, err := redisClient.XReadGroup(
		ctx, config.Group, "readiness-api-runner",
		map[string]string{mq.CircleGroupMembershipEventStream: "0"}, 10, 0,
	)
	if err != nil || len(pending) != 0 {
		t.Fatalf("consumer ACK pending=%d error=%v", len(pending), err)
	}
}

type circleGroupMembershipAPICache struct{}

func (circleGroupMembershipAPICache) InvalidateConversation(context.Context, string) error {
	return nil
}

type circleGroupMembershipAPIPublisher struct{}

func (circleGroupMembershipAPIPublisher) PublishDomainEvent(context.Context, string, string, string, map[string]any) error {
	return nil
}

func (circleGroupMembershipAPIPublisher) PublishRecordedDomainEvent(context.Context, string, string, string, string, map[string]any) error {
	return nil
}

type circleGroupMembershipAPIScheduler struct{}

func (circleGroupMembershipAPIScheduler) EnqueueRecompute(context.Context, conversationapp.GroupAvatarRecomputeTask) error {
	return nil
}

func (circleGroupMembershipAPIScheduler) EnqueueConversationAvatarPatch(context.Context, conversationapp.ConversationAvatarPatchTask) error {
	return nil
}
