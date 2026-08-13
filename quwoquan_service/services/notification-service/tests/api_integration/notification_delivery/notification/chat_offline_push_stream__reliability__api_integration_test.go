// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/chat-offline-push-delivery/spec.md#gwt-002
// readiness_case: project-chat-offline-push-api
//
// chat 离线推送链的 api_integration 证据（真 Redis durable stream + 真 Mongo
// 投递记录 + 真 PresenceClient 经受控 realtime endpoint）：
//   - MessageSent durable 事件经 consumer 投影为离线收件人的 push 投递记录，
//     在线收件人被 presence 抑制；
//   - 记录 payload 只带裁剪预览与 targetType/targetId 路由锚点；
//   - stream 重放经 DedupeKey 收敛，不产生第二条投递记录。
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/reliabletask"
	streamadapter "quwoquan_service/services/notification-service/internal/notification_delivery/notification/adapters/inbound/stream"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/persistence"
	realtimeclient "quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/realtime"
)

func TestChatOfflinePushStreamProjectsOfflineRecipientsAndConvergesReplay(t *testing.T) {
	resetNotificationCollections(t)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	realRedis, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		t.Fatalf("chat offline push api_integration requires real Redis: %v", err)
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

	// 真 PresenceClient 经受控 realtime endpoint：persona-online-api 在线，
	// 其余离线（0 设备）。
	presenceServer := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			parts := strings.Split(r.URL.Path, "/")
			personaID := ""
			for index, part := range parts {
				if part == "personas" && index+1 < len(parts) {
					personaID = parts[index+1]
				}
			}
			devices := []map[string]string{}
			if personaID == "persona-online-api" {
				devices = append(devices, map[string]string{
					"accountId": "account-online",
					"personaId": personaID,
					"deviceId":  "device-online-1",
				})
			}
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{
				"personaId": personaID,
				"devices":   devices,
			})
		},
	))
	t.Cleanup(presenceServer.Close)
	presence, err := realtimeclient.NewPresenceClient(
		realtimeclient.PresenceClientConfig{
			BaseURL:     presenceServer.URL,
			Credentials: fixedServiceCredential("service-token"),
			Timeout:     2 * time.Second,
		},
		http.DefaultClient,
	)
	if err != nil {
		t.Fatalf("presence client: %v", err)
	}

	commands, err := application.NewAppMessageCommandFacade(
		notificationAppMessageStore,
		notificationAppMessageStore,
		notificationReliableStore,
	)
	if err != nil {
		t.Fatalf("command facade: %v", err)
	}
	failures := persistence.NewMongoInteractionFailureStore(notificationMongoDB)
	if err := failures.EnsureIndexes(ctx); err != nil {
		t.Fatalf("failure indexes: %v", err)
	}
	chatOfflinePush, err := application.NewChatOfflinePushProjectionHandler(
		presence,
		notificationReliableStore,
	)
	if err != nil {
		t.Fatalf("chat offline push projection: %v", err)
	}
	consumer, err := streamadapter.NewInteractionNotificationConsumer(
		transport,
		commands,
		failures,
		"chat-offline-push-api-consumer",
		nil,
		nil,
	)
	if err != nil {
		t.Fatalf("consumer: %v", err)
	}
	consumer = consumer.WithChatOfflinePush(chatOfflinePush)

	now := time.Now().UTC()
	appendMessageSent := func(redisEntryID string) {
		t.Helper()
		if _, err := redisClient.XAdd(ctx, "events.chat.messages", map[string]string{
			"eventId":                   "chat-msg-evt-api-1",
			"eventName":                 "MessageSent",
			"conversationId":            "conversation-api-1",
			"messageId":                 "message-api-1",
			"seq":                       "42",
			"messageType":               "text",
			"senderId":                  "persona-sender-api",
			"senderDisplayNameSnapshot": "李明",
			"content":                   "周六的观星聚会记得带上三脚架，顺便看看英仙座流星雨的极大期预报",
			"recipients":                `["persona-online-api","persona-offline-api"]`,
			"occurredAt":                now.Format(time.RFC3339Nano),
			"marker":                    redisEntryID,
		}); err != nil {
			t.Fatalf("xadd MessageSent: %v", err)
		}
	}
	appendMessageSent("first")
	if _, err := consumer.ProcessOnce(ctx); err != nil {
		t.Fatalf("consume MessageSent: %v", err)
	}

	jobs := notificationMongoDB.Collection("notification_delivery_jobs")
	countFor := func(recipient string) int64 {
		count, err := jobs.CountDocuments(ctx, bson.M{
			"eventType":      application.NotificationPushRequestedEvent,
			"destinationRef": recipient,
		})
		if err != nil {
			t.Fatalf("count jobs for %s: %v", recipient, err)
		}
		return count
	}
	if countFor("persona-offline-api") != 1 {
		t.Fatalf("offline recipient must own one push record, got %d", countFor("persona-offline-api"))
	}
	if countFor("persona-online-api") != 0 {
		t.Fatalf("online recipient must be suppressed, got %d", countFor("persona-online-api"))
	}
	var record reliabletask.NotificationOutboxRecord
	if err := jobs.FindOne(ctx, bson.M{
		"eventType":      application.NotificationPushRequestedEvent,
		"destinationRef": "persona-offline-api",
	}).Decode(&record); err != nil {
		t.Fatalf("read offline push record: %v", err)
	}
	if record.DedupeKey != "chat-message:chat-msg-evt-api-1:persona-offline-api" ||
		record.Payload["targetType"] != "conversation" ||
		record.Payload["targetId"] != "conversation-api-1" ||
		record.Payload["title"] != "李明" ||
		record.Status != reliabletask.NotificationStatusPending {
		t.Fatalf("offline push record drifted: %+v", record)
	}
	if len([]rune(record.Payload["summary"])) > 64 ||
		strings.TrimSpace(record.Payload["summary"]) == "" {
		t.Fatalf("push preview must be clipped and non-empty: %q", record.Payload["summary"])
	}

	// stream 重放：同一 eventId 的第二条 durable 记录经 DedupeKey 收敛。
	appendMessageSent("replay")
	if _, err := consumer.ProcessOnce(ctx); err != nil {
		t.Fatalf("consume replay: %v", err)
	}
	if countFor("persona-offline-api") != 1 {
		t.Fatalf("replay must converge by DedupeKey, got %d records", countFor("persona-offline-api"))
	}
}
