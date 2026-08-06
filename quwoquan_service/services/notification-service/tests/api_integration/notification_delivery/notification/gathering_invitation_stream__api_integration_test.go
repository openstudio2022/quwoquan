// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/interaction-notification-inbox/spec.md#gwt-002
// readiness_case: project-gathering-invitation-api
package api_integration

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	streamadapter "quwoquan_service/services/notification-service/internal/notification_delivery/notification/adapters/inbound/stream"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/persistence"
)

func TestGatheringInvitationStreamReplayAndCancellationConverge(t *testing.T) {
	resetNotificationCollections(t)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	realRedis, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		t.Fatalf("Gathering invitation api_integration requires real Redis: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cleanupCancel()
		_ = realRedis.Close(cleanupCtx)
	})
	if err := realRedis.FlushDBs(ctx, 0); err != nil {
		t.Fatalf("flush redis: %v", err)
	}
	router, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode: "standalone", Addr: realRedis.Addr,
				Password: realRedis.Password, DB: 0, TLS: realRedis.TLS,
			},
		},
		DefaultScene: "general",
	})
	if err != nil {
		t.Fatalf("redis router: %v", err)
	}
	redisClient := router.Scene("general")
	transport, err := runtimemessaging.NewRedisMessageTransport(redisClient, redisClient)
	if err != nil {
		t.Fatalf("message transport: %v", err)
	}
	commands, err := application.NewAppMessageCommandFacade(
		notificationAppMessageStore,
		notificationAppMessageStore,
		notificationReliableStore,
	)
	if err != nil {
		t.Fatalf("command facade: %v", err)
	}
	queries, err := application.NewAppMessageQueryFacade(
		notificationAppMessageStore,
		notificationAppMessageStore,
		notificationAppMessageStore,
	)
	if err != nil {
		t.Fatalf("query facade: %v", err)
	}
	failures := persistence.NewMongoInteractionFailureStore(notificationMongoDB)
	if err := failures.EnsureIndexes(ctx); err != nil {
		t.Fatalf("failure indexes: %v", err)
	}
	invitations, err := application.NewGatheringInvitationProjection(
		notificationAppMessageStore,
	)
	if err != nil {
		t.Fatalf("Gathering projection: %v", err)
	}
	consumer, err := streamadapter.NewInteractionNotificationConsumer(
		transport,
		commands,
		failures,
		"gathering-invitation-api-consumer",
		nil,
		invitations,
	)
	if err != nil {
		t.Fatalf("consumer: %v", err)
	}

	now := time.Now().UTC()
	invitationPayload, err := json.Marshal(map[string]any{
		"gatheringId":        "gathering-api-1",
		"inviterPersonaId":   "persona-inviter-api",
		"recipientPersonaId": "persona-recipient-api",
		"purposeSummary":     "周末看展",
		"schedule": map[string]any{
			"timezone": "Asia/Shanghai", "dateLabel": "2026-08-08",
		},
		"place": map[string]any{
			"mode": "physical", "coarsePlaceLabel": "浦东新区",
		},
		"participationVersion": 1,
		"status":               "pending",
		"actionIntents": []map[string]any{
			{"action": "accept", "expectedGatheringVersion": 11, "expectedParticipationVersion": 1},
			{"action": "decline", "expectedGatheringVersion": 11, "expectedParticipationVersion": 1},
		},
		"expiresAt":  now.Add(time.Hour),
		"occurredAt": now,
	})
	if err != nil {
		t.Fatalf("marshal invitation: %v", err)
	}
	appendInvitation := func(eventID string) {
		t.Helper()
		if _, err := redisClient.XAdd(ctx, "events.circle.gatherings", map[string]string{
			"eventId": eventID, "eventName": "GatheringInvitationChanged",
			"aggregateId": "gathering-api-1", "aggregateVersion": "11",
			"payload":    string(invitationPayload),
			"occurredAt": now.Format(time.RFC3339Nano),
		}); err != nil {
			t.Fatalf("xadd invitation: %v", err)
		}
	}
	appendInvitation("invitation-api-1")
	appendInvitation("invitation-api-replay")
	if _, err := consumer.ProcessOnce(ctx); err != nil {
		t.Fatalf("consume invitation replay: %v", err)
	}
	inbox, err := queries.ListInbox(ctx, application.AppMessageInboxQuery{
		UserID: "persona-recipient-api", Limit: 20,
	})
	if err != nil {
		t.Fatalf("list invitation inbox: %v", err)
	}
	if len(inbox.Items) != 1 || inbox.Items[0].GatheringInvitation == nil ||
		len(inbox.Items[0].GatheringInvitation.ActionIntents) != 2 {
		t.Fatalf("invitation inbox=%+v", inbox)
	}

	cancelPayload, _ := json.Marshal(map[string]any{
		"gatheringId":     "gathering-api-1",
		"lifecycleStatus": "cancelled",
		"occurredAt":      now.Add(time.Minute),
	})
	if _, err := redisClient.XAdd(ctx, "events.circle.gatherings", map[string]string{
		"eventId": "gathering-cancel-api-1", "eventName": "GatheringCancelled",
		"aggregateId": "gathering-api-1", "aggregateVersion": "12",
		"payload":    string(cancelPayload),
		"occurredAt": now.Add(time.Minute).Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("xadd cancellation: %v", err)
	}
	if _, err := consumer.ProcessOnce(ctx); err != nil {
		t.Fatalf("consume cancellation: %v", err)
	}
	inbox, err = queries.ListInbox(ctx, application.AppMessageInboxQuery{
		UserID: "persona-recipient-api", Limit: 20,
	})
	if err != nil {
		t.Fatalf("list cancelled invitation: %v", err)
	}
	card := inbox.Items[0].GatheringInvitation
	if card.Status != "cancelled" || len(card.ActionIntents) != 0 {
		t.Fatalf("cancelled invitation=%+v", card)
	}

	appendInvitation("invitation-api-stale-after-cancel")
	if _, err := consumer.ProcessOnce(ctx); err != nil {
		t.Fatalf("consume stale invitation after cancellation: %v", err)
	}
	inbox, err = queries.ListInbox(ctx, application.AppMessageInboxQuery{
		UserID: "persona-recipient-api", Limit: 20,
	})
	if err != nil {
		t.Fatalf("list invitation after stale replay: %v", err)
	}
	card = inbox.Items[0].GatheringInvitation
	if len(inbox.Items) != 1 || card.Status != "cancelled" || len(card.ActionIntents) != 0 {
		t.Fatalf("stale replay restored cancelled invitation=%+v", inbox)
	}
}
