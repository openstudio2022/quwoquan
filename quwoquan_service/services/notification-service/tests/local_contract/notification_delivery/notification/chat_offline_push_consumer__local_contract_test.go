// chat 离线推送 consumer 接线契约：events.chat.messages 经注入的投影
// handler 消费（不落 AppMessage inbox）；stream 重放由幂等键收敛；
// 未注入 handler 时不消费该 stream。
//
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/chat-offline-push-delivery/spec.md#req-001
package local_contract

import (
	"context"
	"sync"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/reliabletask"
	streamadapter "quwoquan_service/services/notification-service/internal/notification_delivery/notification/adapters/inbound/stream"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	jobapplication "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
)

type recordingChatPushOutbox struct {
	mu      sync.Mutex
	records []reliabletask.NotificationOutboxRecord
	byKey   map[string]struct{}
}

func newRecordingChatPushOutbox() *recordingChatPushOutbox {
	return &recordingChatPushOutbox{byKey: map[string]struct{}{}}
}

func (o *recordingChatPushOutbox) CreateNotification(
	_ context.Context,
	record reliabletask.NotificationOutboxRecord,
) (reliabletask.NotificationOutboxRecord, error) {
	o.mu.Lock()
	defer o.mu.Unlock()
	// 生产 outbox 以 DedupeKey 唯一索引收敛重放；double 保持同一语义。
	if _, exists := o.byKey[record.DedupeKey]; exists {
		return record, nil
	}
	o.byKey[record.DedupeKey] = struct{}{}
	o.records = append(o.records, record)
	return record, nil
}

func (o *recordingChatPushOutbox) recorded() []reliabletask.NotificationOutboxRecord {
	o.mu.Lock()
	defer o.mu.Unlock()
	return append([]reliabletask.NotificationOutboxRecord(nil), o.records...)
}

type offlinePresenceDouble struct{}

func (offlinePresenceDouble) GetPersonaPresence(
	_ context.Context,
	personaID string,
) (jobapplication.PersonaPresenceView, error) {
	return jobapplication.PersonaPresenceView{PersonaID: personaID}, nil
}

func appendChatMessageSent(t *testing.T, redis rtredis.Client, eventID string) {
	t.Helper()
	if _, err := redis.XAdd(
		context.Background(),
		application.ChatOfflinePushStream,
		map[string]string{
			"eventId":                   eventID,
			"eventType":                 "MessageSent",
			"conversationId":            "conversation-1",
			"messageId":                 "message-1",
			"seq":                       "9",
			"senderId":                  "user-sender",
			"senderDisplayNameSnapshot": "小满",
			"messageType":               "text",
			"content":                   "周六去黄龙",
			"recipients":                `["user-offline"]`,
			"occurredAt":                time.Now().UTC().Format(time.RFC3339Nano),
		},
	); err != nil {
		t.Fatalf("xadd chat message: %v", err)
	}
}

func TestChatOfflinePushConsumerProjectsWithoutInboxRows(t *testing.T) {
	redis := rtredis.NewMemoryClient()
	store := newMemoryAppMessageStore()
	facade, err := application.NewAppMessageCommandFacade(
		store, passthroughTx{}, noopDeliveryOutbox{},
	)
	if err != nil {
		t.Fatalf("facade init: %v", err)
	}
	transport, err := runtimemessaging.NewRedisMessageTransport(redis, redis)
	if err != nil {
		t.Fatalf("message transport init: %v", err)
	}
	consumer, err := streamadapter.NewInteractionNotificationConsumer(
		transport, facade, newMemoryFailureStore(), "test-chat-push-consumer", nil,
	)
	if err != nil {
		t.Fatalf("consumer init: %v", err)
	}
	pushOutbox := newRecordingChatPushOutbox()
	handler, err := application.NewChatOfflinePushProjectionHandler(
		offlinePresenceDouble{},
		pushOutbox,
	)
	if err != nil {
		t.Fatalf("projection init: %v", err)
	}
	consumer = consumer.WithChatOfflinePush(handler)

	ctx := context.Background()
	appendChatMessageSent(t, redis, "chat-evt-1")
	// at-least-once 重放：同一事件第二次投递必须被幂等键收敛。
	appendChatMessageSent(t, redis, "chat-evt-1")

	if _, err := consumer.ProcessOnce(ctx); err != nil {
		t.Fatalf("process: %v", err)
	}

	records := pushOutbox.recorded()
	if len(records) != 1 {
		t.Fatalf("push delivery records = %#v", records)
	}
	if records[0].DedupeKey != "chat-message:chat-evt-1:user-offline" {
		t.Fatalf("dedupe key = %q", records[0].DedupeKey)
	}
	if store.insertedCount() != 0 {
		t.Fatalf(
			"chat messages must not create AppMessage inbox rows, inserted=%d",
			store.insertedCount(),
		)
	}
}
