package local_contract

import (
	"context"
	. "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
	"testing"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	conversationevent "quwoquan_service/services/chat-service/generated/chat/conversation/contract/event"
	membershipevent "quwoquan_service/services/chat-service/generated/chat/conversation_membership/contract/event"
	messageevent "quwoquan_service/services/chat-service/generated/chat/message/contract/event"
)

func TestCircleGroupConversationProvisionedGeneralRelayIsServerOnly(t *testing.T) {
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
		t.Fatal(err)
	}
	resolverCalled := false
	publisher := NewEventPublisherWithTransport(
		transport,
		NewMemberRecipientResolver(func(context.Context, string) ([]string, error) {
			resolverCalled = true
			return []string{"user-a"}, nil
		}),
	)

	if err := publisher.PublishRecordedDomainEvent(
		ctx,
		"circle-group-conversation-provisioned-1",
		conversationevent.CircleGroupConversationProvisioned,
		"conversation-1",
		"user-a",
		map[string]any{
			"circleId":      "circle-1",
			"circleGroupId": "circle-group-1",
		},
	); err != nil {
		t.Fatalf("PublishRecordedDomainEvent() error = %v", err)
	}
	if resolverCalled {
		t.Fatal("server-only event must not enter client realtime recipient resolution")
	}
	messages, err := general.XRead(
		ctx,
		map[string]string{CircleGroupConversationProvisionedStream: "0-0"},
		10,
		0,
	)
	if err != nil {
		t.Fatalf("read dedicated stream: %v", err)
	}
	if len(messages) != 0 {
		t.Fatalf("general relay must not duplicate dedicated stream publication: %#v", messages)
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

func TestAssistantMembershipDurableStreamCarriesAccountAndPersonaIdentity(t *testing.T) {
	ctx := context.Background()
	redis := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"chat-service-api",
		runtimemessaging.RedisMessageTransportAdapter,
		redis,
		redis,
	)
	if err != nil {
		t.Fatal(err)
	}
	publisher := NewEventPublisherWithTransport(
		transport,
		NewMemberRecipientResolver(func(context.Context, string) ([]string, error) {
			return []string{"persona-owner"}, nil
		}),
	)
	if err := publisher.PublishRecordedDomainEvent(
		ctx,
		"membership-event-1",
		membershipevent.ConversationMemberAdded,
		"conversation-1",
		"persona-owner",
		map[string]any{
			"memberId":           "assistant-membership-1",
			"memberType":         "assistant",
			"invitedBy":          "persona-owner",
			"invitedByAccountId": "account-owner",
		},
	); err != nil {
		t.Fatal(err)
	}
	if err := redis.XGroupCreateMkStream(
		ctx,
		AssistantMembershipStream,
		"placement-projector",
		"0",
	); err != nil {
		t.Fatal(err)
	}
	messages, err := redis.XReadGroup(
		ctx,
		"placement-projector",
		"worker",
		map[string]string{AssistantMembershipStream: ">"},
		1,
		0,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(messages) != 1 ||
		messages[0].Values["eventId"] != "membership-event-1" ||
		messages[0].Values["invitedByAccountId"] != "account-owner" ||
		messages[0].Values["invitedBy"] != "persona-owner" ||
		messages[0].Values["occurredAt"] == "" {
		t.Fatalf("assistant membership durable event=%#v", messages)
	}
}

func TestRecordedChatEventWritesIndependentRecipientResumeStreams(t *testing.T) {
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
	publisher := NewEventPublisherWithTransports(
		transport,
		resumeTransport,
		NewMemberRecipientResolver(func(context.Context, string) ([]string, error) {
			return []string{"user-a", "user-b"}, nil
		}),
	)

	if err := publisher.PublishRecordedDomainEvent(
		ctx,
		"event-1",
		messageevent.MessageSent,
		"conversation-1",
		"user-a",
		map[string]any{"messageId": "message-1", "seq": int64(7)},
	); err != nil {
		t.Fatalf("PublishRecordedDomainEvent() error = %v", err)
	}
	for _, userID := range []string{"user-a", "user-b"} {
		messages, readErr := realtime.XRead(
			ctx,
			map[string]string{RealtimeResumeStream(userID): "0-0"},
			10,
			0,
		)
		if readErr != nil {
			t.Fatalf("read %s resume stream: %v", userID, readErr)
		}
		if len(messages) != 1 ||
			messages[0].Values["eventId"] != "event-1" ||
			messages[0].Values["messageId"] != "message-1" ||
			messages[0].Values["seq"] != "7" {
			t.Fatalf("%s resume stream = %#v", userID, messages)
		}
	}
}
