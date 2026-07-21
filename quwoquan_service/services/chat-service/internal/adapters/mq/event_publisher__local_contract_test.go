package mq

import (
	"context"
	"reflect"
	"testing"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	membershipevent "quwoquan_service/services/chat-service/internal/domain/chat/conversation_membership/event"
	messageevent "quwoquan_service/services/chat-service/internal/domain/chat/message/event"
)

func TestRecipientsForTerminalMembershipEventIncludesAffectedUserExactlyOnce(t *testing.T) {
	recipients := recipientsForEvent(
		[]string{"owner", "member", "owner"},
		DomainEvent{
			Type:    membershipevent.ConversationMemberRemoved,
			Payload: map[string]any{"userId": "removed"},
		},
	)
	want := []string{"owner", "member", "removed"}
	if !reflect.DeepEqual(recipients, want) {
		t.Fatalf("terminal removal recipients = %v, want %v", recipients, want)
	}
}

func TestRecipientsForLeaveDoesNotDuplicateActiveAffectedUser(t *testing.T) {
	recipients := recipientsForEvent(
		[]string{"owner", "leaving"},
		DomainEvent{
			Type:    membershipevent.ConversationMemberLeft,
			Payload: map[string]any{"userId": "leaving"},
		},
	)
	want := []string{"owner", "leaving"}
	if !reflect.DeepEqual(recipients, want) {
		t.Fatalf("terminal leave recipients = %v, want %v", recipients, want)
	}
}

func TestRecipientsForNonTerminalEventDoesNotTrustPayloadUserID(t *testing.T) {
	recipients := recipientsForEvent(
		[]string{"owner"},
		DomainEvent{
			Type:    "ConversationRosterUpdated",
			Payload: map[string]any{"userId": "unrelated"},
		},
	)
	want := []string{"owner"}
	if !reflect.DeepEqual(recipients, want) {
		t.Fatalf("non-terminal recipients = %v, want %v", recipients, want)
	}
}

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
