// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-002
// readiness_case: bind-circle-group-conversation-api
package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	messaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	groupapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	groupmessaging "quwoquan_service/services/circle-service/internal/circle_management/circle_group/infrastructure/messaging"
	grouppersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_group/infrastructure/persistence"
	testsupport "quwoquan_service/services/circle-service/tests/support"
)

func TestConversationBindingConsumerCommitsMongoStateBeforeRedisAck(t *testing.T) {
	ctx := context.Background()
	database := testsupport.StartRealMongo(t, "circle_group_conversation_binding")
	store := grouppersistence.NewMongoAggregateStore(database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := database.Collection("circle_groups").InsertOne(ctx, bson.M{
		"_id": "group-binding-api", "circleId": "circle-binding-api",
		"status": "active", "conversationId": "",
	}); err != nil {
		t.Fatal(err)
	}

	redisRuntime, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := redisRuntime.Close(context.Background()); err != nil {
			t.Errorf("close real Redis: %v", err)
		}
	})
	router := platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode: "standalone", Addr: redisRuntime.Addr,
				Password: redisRuntime.Password, DB: 0, TLS: redisRuntime.TLS,
			},
		},
		DefaultScene: "general",
	})
	t.Cleanup(func() {
		if err := router.Close(); err != nil {
			t.Errorf("close Redis router: %v", err)
		}
	})
	client := router.Scene("general")
	transport, err := messaging.NewRedisMessageTransportForRoot(
		"circle-group-binding-api",
		messaging.RedisMessageTransportAdapter,
		client,
		client,
	)
	if err != nil {
		t.Fatal(err)
	}
	failures := grouppersistence.NewMongoConversationBindingFailureStore(database)
	if err := failures.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	consumer, err := groupmessaging.NewCircleGroupConversationBindingConsumer(
		transport,
		groupapp.NewConversationBindingProjector(store),
		failures,
		"circle-group-binding-api",
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := client.XAdd(ctx, groupmessaging.CircleGroupConversationProvisionedStream, map[string]string{
		"eventId":    "binding-api-1",
		"eventType":  "CircleGroupConversationProvisioned",
		"payload":    `{"conversationId":"conversation-binding-api","circleId":"circle-binding-api","circleGroupId":"group-binding-api"}`,
		"occurredAt": time.Now().UTC().Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatal(err)
	}
	if processed, err := consumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("processed=%d err=%v", processed, err)
	}
	var group struct {
		ConversationID string `bson:"conversationId"`
	}
	if err := database.Collection("circle_groups").FindOne(
		ctx, bson.M{"_id": "group-binding-api"},
	).Decode(&group); err != nil || group.ConversationID != "conversation-binding-api" {
		t.Fatalf("bound group=%+v err=%v", group, err)
	}
	pending, _, err := client.XAutoClaim(
		ctx,
		groupmessaging.CircleGroupConversationProvisionedStream,
		groupmessaging.CircleGroupConversationBindingGroup,
		"binding-observer",
		0,
		"0-0",
		10,
	)
	if err != nil || len(pending) != 0 {
		t.Fatalf("pending=%d err=%v", len(pending), err)
	}
}
