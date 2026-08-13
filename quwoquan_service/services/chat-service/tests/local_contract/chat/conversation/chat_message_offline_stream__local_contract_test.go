// MessageSent 面向 notification 的 durable 扇出契约：仅 outbox 主路径（带
// 稳定 eventId）写入 events.chat.messages；载荷最小化且收件人排除发送者；
// 与 realtime resume 坐标物理隔离；撤回与无 eventId 路径不产生投递事实。
//
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/chat-offline-push-delivery/spec.md#req-001
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/chat-offline-push-delivery/spec.md#req-004
package local_contract

import (
	"context"
	"encoding/json"
	"reflect"
	"testing"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	. "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
	messageevent "quwoquan_service/services/chat-service/generated/chat/message/contract/event"
)

func newOfflineStreamPublisher(
	t *testing.T,
	realtime rtredis.Client,
	general rtredis.Client,
) *EventPublisher {
	t.Helper()
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"chat-service-api",
		runtimemessaging.RedisMessageTransportAdapter,
		realtime,
		general,
	)
	if err != nil {
		t.Fatal(err)
	}
	resumeTransport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"chat-service-api-resume",
		runtimemessaging.RedisMessageTransportAdapter,
		realtime,
		realtime,
	)
	if err != nil {
		t.Fatal(err)
	}
	return NewEventPublisherWithTransports(
		transport,
		resumeTransport,
		NewMemberRecipientResolver(func(context.Context, string) ([]string, error) {
			return []string{"user-sender", "user-offline-a", "user-offline-b"}, nil
		}),
	)
}

func TestRecordedMessageSentWritesOfflineDeliveryStream(t *testing.T) {
	ctx := context.Background()
	realtime := rtredis.NewMemoryClient()
	general := rtredis.NewMemoryClient()
	publisher := newOfflineStreamPublisher(t, realtime, general)

	if err := publisher.PublishRecordedDomainEvent(
		ctx,
		"offline-event-1",
		messageevent.MessageSent,
		"conversation-1",
		"user-sender",
		map[string]any{
			"messageId":                 "message-1",
			"conversationId":            "conversation-1",
			"seq":                       int64(9),
			"clientMsgId":               "client-1",
			"senderId":                  "user-sender",
			"senderDisplayNameSnapshot": "小满",
			"type":                      "text",
			"content":                   "周六去黄龙五彩池吗",
		},
	); err != nil {
		t.Fatalf("PublishRecordedDomainEvent() error = %v", err)
	}

	messages, err := general.XRead(
		ctx,
		map[string]string{ChatMessagesStream: "0-0"},
		10,
		0,
	)
	if err != nil {
		t.Fatalf("read offline delivery stream: %v", err)
	}
	if len(messages) != 1 {
		t.Fatalf("offline delivery stream = %#v", messages)
	}
	values := messages[0].Values
	if values["eventId"] != "offline-event-1" ||
		values["messageId"] != "message-1" ||
		values["conversationId"] != "conversation-1" ||
		values["seq"] != "9" ||
		values["senderId"] != "user-sender" ||
		values["senderDisplayNameSnapshot"] != "小满" ||
		values["messageType"] != "text" ||
		values["content"] != "周六去黄龙五彩池吗" {
		t.Fatalf("offline delivery event values = %#v", values)
	}
	var recipients []string
	if err := json.Unmarshal([]byte(values["recipients"]), &recipients); err != nil {
		t.Fatalf("decode recipients: %v", err)
	}
	if !reflect.DeepEqual(recipients, []string{"user-offline-a", "user-offline-b"}) {
		t.Fatalf("recipients must exclude the sender, got %v", recipients)
	}
	// 载荷最小化：不携带 card/media/mentions 细节字段。
	for _, forbidden := range []string{"card", "mediaAssetId", "mentions", "clientMsgId"} {
		if _, exists := values[forbidden]; exists {
			t.Fatalf("offline delivery event must not carry %q", forbidden)
		}
	}

	// 与 realtime resume 坐标物理隔离：realtime scene 不出现该 stream。
	realtimeMessages, err := realtime.XRead(
		ctx,
		map[string]string{ChatMessagesStream: "0-0"},
		10,
		0,
	)
	if err != nil {
		t.Fatalf("read realtime scene: %v", err)
	}
	if len(realtimeMessages) != 0 {
		t.Fatalf("offline delivery stream must stay on the general durable scene: %#v", realtimeMessages)
	}
}

func TestUnrecordedOrRecalledMessagesSkipOfflineDeliveryStream(t *testing.T) {
	ctx := context.Background()
	realtime := rtredis.NewMemoryClient()
	general := rtredis.NewMemoryClient()
	publisher := newOfflineStreamPublisher(t, realtime, general)

	// 无 eventId 的即时路径没有幂等键，不得产生投递事实。
	if err := publisher.PublishDomainEvent(
		ctx,
		messageevent.MessageSent,
		"conversation-1",
		"user-sender",
		map[string]any{
			"messageId": "message-ephemeral",
			"senderId":  "user-sender",
			"type":      "text",
			"content":   "即时路径",
		},
	); err != nil {
		t.Fatalf("PublishDomainEvent() error = %v", err)
	}
	// 撤回不推送。
	if err := publisher.PublishRecordedDomainEvent(
		ctx,
		"recall-event-1",
		messageevent.MessageRecalled,
		"conversation-1",
		"user-sender",
		map[string]any{"messageId": "message-1"},
	); err != nil {
		t.Fatalf("PublishRecordedDomainEvent(recall) error = %v", err)
	}

	messages, err := general.XRead(
		ctx,
		map[string]string{ChatMessagesStream: "0-0"},
		10,
		0,
	)
	if err != nil {
		t.Fatalf("read offline delivery stream: %v", err)
	}
	if len(messages) != 0 {
		t.Fatalf("only recorded MessageSent may enter offline delivery, got %#v", messages)
	}
}
