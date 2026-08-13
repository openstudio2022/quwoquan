// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-001.t3
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-001.t4
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-002
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-002.t3
// readiness_case: project-circle-group-conversation-api
//
// 绑定同步可靠性负例：重复重放不建第二对象、role_changed 只更新既有名册行、
// 毒信按受控重试上限进入带 TTL 的 DLQ（source message 最终 ACK、健康检查可见失败摘要）。
package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/persistence"
	membershippersistence "quwoquan_service/services/chat-service/internal/chat/conversation_membership/infrastructure/persistence"
)

// suffix 让每个用例使用独立 consumer group / DLQ：平台 redis client 会按
// 实例 memoize 已创建的组，cleanAll 冲掉服务端组后同名组不会被重建。
func newBindingReliabilityConsumers(
	t *testing.T,
	suffix string,
) (*persistence.MongoChatStore, *membershippersistence.MongoStore, *mq.CircleGroupChatSyncConsumer, *mq.CircleGroupChatSyncConsumer) {
	t.Helper()
	ctx := context.Background()
	store := persistence.NewMongoChatStore(requireMongoDB(t))
	membershipStore := membershippersistence.NewMongoStore(requireMongoDB(t))
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
	syncService := application.NewCircleGroupConversationProjectionHandler(conversations, members)
	failures := persistence.NewMongoCircleGroupChatSyncFailureStore(requireMongoDB(t))
	if err := failures.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	groupConsumer, err := mq.NewCircleGroupChatSyncConsumer(
		redisRouter.Scene("general"),
		syncService,
		failures,
		"chat-circle-group-reliability-"+suffix,
		nil,
		mq.CircleGroupChatSyncConsumerConfig{
			Stream:       mq.CircleGroupEventStream,
			Group:        "chat.circle_group_projection.reliability." + suffix,
			DLQ:          "events.circle.groups.chat-reliability-" + suffix + ".dlq",
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
	if err := groupConsumer.EnsureGroup(ctx); err != nil {
		t.Fatal(err)
	}
	membershipConsumer, err := mq.NewCircleGroupChatSyncConsumer(
		redisRouter.Scene("general"),
		syncService,
		failures,
		"chat-circle-group-membership-reliability-"+suffix,
		nil,
		mq.CircleGroupChatSyncConsumerConfig{
			Stream:       mq.CircleGroupMembershipEventStream,
			Group:        "chat.circle_group_membership_projection.reliability." + suffix,
			DLQ:          "events.circle.group-memberships.chat-reliability-" + suffix + ".dlq",
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
	return store, membershipStore, groupConsumer, membershipConsumer
}

func TestCircleGroupCreatedReplayDoesNotCreateSecondConversation(t *testing.T) {
	cleanAll(t)
	ctx := context.Background()
	store, _, groupConsumer, _ := newBindingReliabilityConsumers(t, "replay")
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}

	created := circleGroupStreamValues(
		"cg-replay-1", "CircleGroupCreated", "group-replay", "circle-replay", 1,
		`"name":"重放测试组","createdByPersonaId":"owner-replay","status":"active"`,
	)
	if _, err := redisRouter.Scene("general").XAdd(ctx, mq.CircleGroupEventStream, created); err != nil {
		t.Fatal(err)
	}
	if processed, err := groupConsumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("first delivery must provision binding: processed=%d err=%v", processed, err)
	}
	// 同一逻辑事件（相同 eventId/aggregateVersion）经 relay 重投或 reclaim 重放。
	if _, err := redisRouter.Scene("general").XAdd(ctx, mq.CircleGroupEventStream, created); err != nil {
		t.Fatal(err)
	}
	if _, err := groupConsumer.ProcessOnce(ctx); err != nil {
		t.Fatalf("replayed delivery must converge idempotently: %v", err)
	}

	count, err := requireMongoDB(t).Collection("conversations").CountDocuments(
		ctx, bson.M{"circleGroupId": "group-replay"},
	)
	if err != nil {
		t.Fatal(err)
	}
	if count != 1 {
		t.Fatalf("replay must not create a second bound conversation: count=%d", count)
	}
	conv, err := store.FindConversationByCircleGroupID(ctx, "group-replay")
	if err != nil {
		t.Fatal(err)
	}
	memberRows, err := requireMongoDB(t).Collection("conversation_memberships").CountDocuments(
		ctx, bson.M{"conversationId": conv.ID, "userId": "owner-replay"},
	)
	if err != nil {
		t.Fatal(err)
	}
	if memberRows != 1 {
		t.Fatalf("replay must not duplicate the owner roster row: count=%d", memberRows)
	}
}

func TestCircleGroupMembershipRoleChangeUpdatesExistingRosterRow(t *testing.T) {
	cleanAll(t)
	ctx := context.Background()
	store, membershipStore, groupConsumer, membershipConsumer := newBindingReliabilityConsumers(t, "role")

	created := circleGroupStreamValues(
		"cg-role-1", "CircleGroupCreated", "group-role", "circle-role", 1,
		`"name":"角色测试组","createdByPersonaId":"owner-role","status":"active"`,
	)
	if _, err := redisRouter.Scene("general").XAdd(ctx, mq.CircleGroupEventStream, created); err != nil {
		t.Fatal(err)
	}
	if processed, err := groupConsumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("provision bound conversation: processed=%d err=%v", processed, err)
	}
	conv, err := store.FindConversationByCircleGroupID(ctx, "group-role")
	if err != nil {
		t.Fatal(err)
	}

	activated := circleGroupStreamValues(
		"cgm-role-activate", "CircleGroupMembershipActivated", "group-role", "circle-role", 2,
		`"personaId":"member-role","role":"member","state":"active"`,
	)
	if _, err := redisRouter.Scene("general").XAdd(ctx, mq.CircleGroupMembershipEventStream, activated); err != nil {
		t.Fatal(err)
	}
	if processed, err := membershipConsumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("project active member: processed=%d err=%v", processed, err)
	}

	roleChanged := circleGroupStreamValues(
		"cgm-role-changed", "CircleGroupMembershipRoleChanged", "group-role", "circle-role", 3,
		`"personaId":"member-role","role":"manager","state":"active"`,
	)
	if _, err := redisRouter.Scene("general").XAdd(ctx, mq.CircleGroupMembershipEventStream, roleChanged); err != nil {
		t.Fatal(err)
	}
	if processed, err := membershipConsumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("project role change: processed=%d err=%v", processed, err)
	}

	member, err := membershipStore.FindMember(ctx, conv.ID, "member-role")
	if err != nil {
		t.Fatalf("role change must keep the roster row: %v", err)
	}
	if member.Role != "admin" {
		t.Fatalf("role change must update the existing roster row, got role=%q", member.Role)
	}
	rows, err := requireMongoDB(t).Collection("conversation_memberships").CountDocuments(
		ctx, bson.M{"conversationId": conv.ID, "userId": "member-role"},
	)
	if err != nil {
		t.Fatal(err)
	}
	if rows != 1 {
		t.Fatalf("role change must not create duplicate roster rows: count=%d", rows)
	}
}

func TestCircleGroupPoisonEventEntersTTLBackedDLQAfterBoundedRetries(t *testing.T) {
	cleanAll(t)
	ctx := context.Background()
	_, _, groupConsumer, _ := newBindingReliabilityConsumers(t, "poison")
	redis := redisRouter.Scene("general")
	const dlqStream = "events.circle.groups.chat-reliability-poison.dlq"

	now := time.Now().UTC().Format(time.RFC3339Nano)
	poison := map[string]string{
		"eventId":          "cg-poison-1",
		"eventType":        "CircleGroupCreated",
		"aggregateType":    "CircleGroup",
		"aggregateId":      "group-poison",
		"aggregateVersion": "1",
		// 不可解析 payload：持久化前解码即失败，走受控重试。
		"payload":    `{"groupId":"group-poison",`,
		"occurredAt": now,
	}
	if _, err := redis.XAdd(ctx, mq.CircleGroupEventStream, poison); err != nil {
		t.Fatal(err)
	}

	// 第一次投递：失败但未达上限 → 不 ACK（pending 保留）、不产生 DLQ；
	// health/metric 可见：重试期健康检查必须暴露失败摘要。
	if _, err := groupConsumer.ProcessOnce(ctx); err == nil {
		t.Fatal("first poison delivery must surface a retryable failure")
	}
	if err := groupConsumer.Healthy(time.Minute); err == nil {
		t.Fatal("consumer health must surface the poison failure digest during retries")
	}
	if entries, err := redis.XRead(
		ctx, map[string]string{dlqStream: "0"}, 10, 0,
	); err != nil {
		t.Fatal(err)
	} else if len(entries) != 0 {
		t.Fatalf("poison event must not enter DLQ before MaxAttempts: %d", len(entries))
	}
	if pending, err := redis.XPendingCount(
		ctx, mq.CircleGroupEventStream, "chat.circle_group_projection.reliability.poison",
	); err != nil || pending != 1 {
		t.Fatalf("retryable poison must stay pending (not ACKed): pending=%d err=%v", pending, err)
	}

	// 第二次投递（reclaim）：达到 MaxAttempts=2 → 进 DLQ、source ACK。
	// DLQ 交接链 fail-closed：Expire(TTL) 失败会使 ProcessOnce 报错，
	// 故本次成功即证明 DLQ retention TTL 已设置。
	if _, err := groupConsumer.ProcessOnce(ctx); err != nil {
		t.Fatalf("DLQ handoff itself must succeed: %v", err)
	}
	entries, err := redis.XRead(ctx, map[string]string{dlqStream: "0"}, 10, 0)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 1 {
		t.Fatalf("poison event must land exactly once in DLQ: %d", len(entries))
	}
	if pending, err := redis.XPendingCount(
		ctx, mq.CircleGroupEventStream, "chat.circle_group_projection.reliability.poison",
	); err != nil || pending != 0 {
		t.Fatalf("DLQ handoff must ACK the source message: pending=%d err=%v", pending, err)
	}

	// source message 已 ACK：后续扫描不再重复消费毒信。
	if processed, err := groupConsumer.ProcessOnce(ctx); err != nil || processed != 0 {
		t.Fatalf("acked poison must not be reprocessed: processed=%d err=%v", processed, err)
	}
	// 绑定不得被半持久化。
	count, err := requireMongoDB(t).Collection("conversations").CountDocuments(
		ctx, bson.M{"circleGroupId": "group-poison"},
	)
	if err != nil {
		t.Fatal(err)
	}
	if count != 0 {
		t.Fatalf("poison event must not persist a partial binding: count=%d", count)
	}
	// 毒信按治理进入 DLQ 后消费恢复健康（失败摘要随成功扫描清空）。
	if err := groupConsumer.Healthy(time.Minute); err != nil {
		t.Fatalf("consumer health must recover after governed DLQ handoff: %v", err)
	}
}
