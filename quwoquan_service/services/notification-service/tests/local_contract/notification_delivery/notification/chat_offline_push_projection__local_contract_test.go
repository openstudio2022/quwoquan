// chat 离线推送投影契约：presence 在线抑制、离线收件人各一条 push 投递
// 作业（幂等键 = 事件 + 收件人）、投递记录只携带裁剪预览不保留正文、
// 单收件人失败不中断其余收件人。
//
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/chat-offline-push-delivery/spec.md#req-001
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/chat-offline-push-delivery/spec.md#req-004
package local_contract

import (
	"context"
	"fmt"
	"strings"
	"testing"

	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	jobapplication "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
)

type chatPushPresenceDouble struct {
	onlinePersonas map[string]bool
	failPersonas   map[string]bool
}

func (d *chatPushPresenceDouble) GetPersonaPresence(
	_ context.Context,
	personaID string,
) (jobapplication.PersonaPresenceView, error) {
	if d.failPersonas[personaID] {
		return jobapplication.PersonaPresenceView{}, fmt.Errorf("presence unavailable")
	}
	view := jobapplication.PersonaPresenceView{PersonaID: personaID}
	if d.onlinePersonas[personaID] {
		view.Devices = []jobapplication.PersonaPresenceDevice{{DeviceID: "device-1"}}
	}
	return view, nil
}

type chatPushOutboxDouble struct {
	records []reliabletask.NotificationOutboxRecord
}

func (d *chatPushOutboxDouble) CreateNotification(
	_ context.Context,
	record reliabletask.NotificationOutboxRecord,
) (reliabletask.NotificationOutboxRecord, error) {
	d.records = append(d.records, record)
	return record, nil
}

func chatOfflinePushEvent(recipients string) application.InteractionStreamEvent {
	return application.InteractionStreamEvent{
		Stream:    application.ChatOfflinePushStream,
		MessageID: "1-1",
		EventID:   "chat-event-1",
		EventType: "MessageSent",
		Values: map[string]string{
			"eventId":                   "chat-event-1",
			"eventType":                 "MessageSent",
			"conversationId":            "conversation-1",
			"messageId":                 "message-1",
			"seq":                       "9",
			"senderId":                  "user-sender",
			"senderDisplayNameSnapshot": "小满",
			"messageType": "text",
			"content": "周六去黄龙五彩池吗，顺路可以先去牟尼沟看瀑布，中午在镇上找一家本地菜馆歇脚，" +
				"下午沿栈道慢慢往上走看钙化池，傍晚回程路上再一起吃一顿藏餐收尾",
			"recipients": recipients,
		},
	}
}

func TestChatOfflinePushProjectsOfflineRecipientsOnly(t *testing.T) {
	presence := &chatPushPresenceDouble{
		onlinePersonas: map[string]bool{"user-online": true},
	}
	outbox := &chatPushOutboxDouble{}
	handler, err := application.NewChatOfflinePushProjectionHandler(presence, outbox)
	if err != nil {
		t.Fatal(err)
	}

	err = handler.Handle(
		context.Background(),
		chatOfflinePushEvent(`["user-online","user-offline"]`),
	)
	if err != nil {
		t.Fatalf("Handle() error = %v", err)
	}
	if len(outbox.records) != 1 {
		t.Fatalf("only offline recipients may enter push delivery, got %#v", outbox.records)
	}
	record := outbox.records[0]
	if record.Channel != "push" ||
		record.DestinationRef != "user-offline" ||
		record.DedupeKey != "chat-message:chat-event-1:user-offline" {
		t.Fatalf("push delivery record = %#v", record)
	}
	if record.Payload["targetType"] != "conversation" ||
		record.Payload["targetId"] != "conversation-1" ||
		record.Payload["title"] != "小满" {
		t.Fatalf("push payload routing anchors = %#v", record.Payload)
	}
	// REQ-004：投递记录不保留正文全文，只允许裁剪后的预览。
	preview := record.Payload["summary"]
	if strings.Contains(preview, "藏餐") {
		t.Fatalf("delivery record must not carry the full message body: %q", preview)
	}
	if len([]rune(preview)) > 64 || preview == "" {
		t.Fatalf("push preview must be a non-empty clipped summary: %q", preview)
	}
}

func TestChatOfflinePushIsolatesSingleRecipientFailure(t *testing.T) {
	presence := &chatPushPresenceDouble{
		failPersonas: map[string]bool{"user-broken": true},
	}
	outbox := &chatPushOutboxDouble{}
	handler, err := application.NewChatOfflinePushProjectionHandler(presence, outbox)
	if err != nil {
		t.Fatal(err)
	}

	err = handler.Handle(
		context.Background(),
		chatOfflinePushEvent(`["user-broken","user-offline"]`),
	)
	if err == nil {
		t.Fatal("recipient failure must surface for retry, not be swallowed")
	}
	if !strings.Contains(err.Error(), "user-broken") {
		t.Fatalf("failure must identify the failing recipient: %v", err)
	}
	if len(outbox.records) != 1 || outbox.records[0].DestinationRef != "user-offline" {
		t.Fatalf("healthy recipients must still be projected, got %#v", outbox.records)
	}
}

func TestChatOfflinePushMediaPreviewCarriesNoContent(t *testing.T) {
	presence := &chatPushPresenceDouble{}
	outbox := &chatPushOutboxDouble{}
	handler, err := application.NewChatOfflinePushProjectionHandler(presence, outbox)
	if err != nil {
		t.Fatal(err)
	}

	event := chatOfflinePushEvent(`["user-offline"]`)
	event.Values["messageType"] = "image"
	event.Values["content"] = ""
	if err := handler.Handle(context.Background(), event); err != nil {
		t.Fatalf("Handle() error = %v", err)
	}
	if len(outbox.records) != 1 {
		t.Fatalf("records = %#v", outbox.records)
	}
	if outbox.records[0].Payload["summary"] != "" {
		t.Fatalf("media push preview must stay empty, got %q", outbox.records[0].Payload["summary"])
	}
	if outbox.records[0].Payload["messageType"] != "chat_message" {
		t.Fatalf("payload messageType = %#v", outbox.records[0].Payload)
	}
}
