package local_contract

import (
	"context"
	. "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
	"testing"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	messageevent "quwoquan_service/services/chat-service/generated/chat/message/contract/event"
)

func TestAssistantMentionDurableStreamUsesDedicatedGeneralTransport(t *testing.T) {
	ctx := context.Background()
	realtime := rtredis.NewMemoryClient()
	general := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"chat-service-api",
		runtimemessaging.RedisMessageTransportAdapter,
		realtime,
		general,
	)
	if err != nil {
		t.Fatalf("NewRedisMessageTransportForRoot() error = %v", err)
	}
	publisher := NewEventPublisherWithTransport(
		transport,
		NewMemberRecipientResolver(func(context.Context, string) ([]string, error) {
			return []string{"user-a"}, nil
		}),
	)

	if err := publisher.PublishDomainEvent(
		ctx,
		messageevent.AssistantMentioned,
		"conversation-1",
		"user-a",
		map[string]any{
			"messageId":         "message-1",
			"assistantMemberId": "assistant",
			"content":           "@小趣 总结",
		},
	); err != nil {
		t.Fatalf("PublishDomainEvent() error = %v", err)
	}
	if err := general.XGroupCreateMkStream(
		ctx,
		AssistantMentionedStream,
		"contract",
		"0",
	); err != nil {
		t.Fatalf("create durable group: %v", err)
	}
	messages, err := general.XReadGroup(
		ctx,
		"contract",
		"reader",
		map[string]string{AssistantMentionedStream: ">"},
		1,
		0,
	)
	if err != nil {
		t.Fatalf("read durable stream: %v", err)
	}
	if len(messages) != 1 || messages[0].Values["messageId"] != "message-1" {
		t.Fatalf("general durable stream = %#v", messages)
	}
	if err := realtime.XGroupCreateMkStream(
		ctx,
		AssistantMentionedStream,
		"contract",
		"0",
	); err != nil {
		t.Fatalf("create realtime group: %v", err)
	}
	realtimeMessages, err := realtime.XReadGroup(
		ctx,
		"contract",
		"reader",
		map[string]string{AssistantMentionedStream: ">"},
		1,
		0,
	)
	if err != nil {
		t.Fatalf("read realtime stream: %v", err)
	}
	if len(realtimeMessages) != 0 {
		t.Fatalf("realtime transport must not contain durable assistant mentions: %#v", realtimeMessages)
	}
}
