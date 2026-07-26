package mq

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

const (
	CircleGroupConversationProvisionedStream          = "events.chat.circle-group-conversations"
	CircleGroupConversationProvisionedStreamRetention = 7 * 24 * time.Hour
	circleGroupConversationProvisionedEventType       = "CircleGroupConversationProvisioned"
)

// CircleGroupConversationProvisionedStreamPublisher is a filtered second
// relay target for the Conversation outbox. It does not replace realtime
// EventPublisher: the normal fanout relay remains responsible for clients,
// while this durable stream feeds Circle's binding write-back projector.
type CircleGroupConversationProvisionedStreamPublisher struct {
	redis rtredis.Client
}

var _ application.EventPublisher = (*CircleGroupConversationProvisionedStreamPublisher)(nil)

func NewCircleGroupConversationProvisionedStreamPublisher(
	redis rtredis.Client,
) *CircleGroupConversationProvisionedStreamPublisher {
	return &CircleGroupConversationProvisionedStreamPublisher{redis: redis}
}

func (p *CircleGroupConversationProvisionedStreamPublisher) PublishDomainEvent(
	_ context.Context,
	eventType string,
	_ string,
	_ string,
	_ map[string]any,
) error {
	if strings.TrimSpace(eventType) == circleGroupConversationProvisionedEventType {
		return fmt.Errorf("CircleGroupConversationProvisioned must be published from a recorded aggregate outbox event")
	}
	return nil
}

func (p *CircleGroupConversationProvisionedStreamPublisher) PublishRecordedDomainEvent(
	ctx context.Context,
	eventID string,
	eventType string,
	conversationID string,
	actorID string,
	payload map[string]any,
) error {
	if strings.TrimSpace(eventType) != circleGroupConversationProvisionedEventType {
		return nil
	}
	if p == nil || p.redis == nil {
		return fmt.Errorf("CircleGroupConversationProvisioned stream publisher is not configured")
	}
	eventID = strings.TrimSpace(eventID)
	conversationID = strings.TrimSpace(conversationID)
	if eventID == "" || conversationID == "" {
		return fmt.Errorf("CircleGroupConversationProvisioned outbox identity is incomplete")
	}
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("encode CircleGroupConversationProvisioned payload: %w", err)
	}
	if _, err := p.redis.XAdd(ctx, CircleGroupConversationProvisionedStream, map[string]string{
		"eventId":        eventID,
		"eventType":      eventType,
		"aggregateType":  "Conversation",
		"aggregateId":    conversationID,
		"conversationId": conversationID,
		"actorId":        strings.TrimSpace(actorID),
		"payload":        string(payloadJSON),
		"occurredAt":     time.Now().UTC().Format(time.RFC3339Nano),
	}); err != nil {
		return fmt.Errorf("append CircleGroupConversationProvisioned stream: %w", err)
	}
	if err := p.redis.Expire(ctx, CircleGroupConversationProvisionedStream, CircleGroupConversationProvisionedStreamRetention); err != nil {
		return fmt.Errorf("refresh CircleGroupConversationProvisioned stream retention: %w", err)
	}
	return nil
}
