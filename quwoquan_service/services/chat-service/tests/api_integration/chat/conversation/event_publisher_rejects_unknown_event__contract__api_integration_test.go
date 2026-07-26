package api_integration

import (
	"context"
	"testing"

	mqpkg "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
)

func TestEventPublisherRejectsUnknownEventType(t *testing.T) {
	publisher := mqpkg.NewEventPublisher(
		redisRouter.Scene("realtime"),
		redisRouter.Scene("general"),
		fixedRecipientResolver("user_contract"),
	)
	err := publisher.Publish(context.Background(), mqpkg.DomainEvent{
		Type:           "UnsupportedDomainEvent",
		ConversationID: "conv_contract",
	})
	if err == nil {
		t.Fatal("expected unknown retired event type to be rejected")
	}
}
