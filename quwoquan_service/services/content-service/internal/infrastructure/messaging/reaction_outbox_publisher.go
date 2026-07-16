package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	reactionports "quwoquan_service/services/content-service/internal/domain/reaction/ports"
)

// ContentReactionOutboxPublisher 把 durable object fact 翻译成共享事件 envelope。
type ContentReactionOutboxPublisher struct {
	publisher runtimemessaging.EventPublisher
}

func NewContentReactionOutboxPublisher(
	publisher runtimemessaging.EventPublisher,
) *ContentReactionOutboxPublisher {
	return &ContentReactionOutboxPublisher{publisher: publisher}
}

func (p *ContentReactionOutboxPublisher) Publish(
	ctx context.Context,
	fact reactionports.OutboxFact,
) error {
	if p == nil || p.publisher == nil {
		return fmt.Errorf("ContentReaction outbox publisher is not configured")
	}
	if fact.EventID == "" || fact.EventType == "" {
		return fmt.Errorf("ContentReaction outbox fact identity is incomplete")
	}
	var payload map[string]any
	if err := json.Unmarshal(fact.Payload, &payload); err != nil {
		return fmt.Errorf("decode ContentReaction outbox payload: %w", err)
	}
	return p.publisher.Publish(ctx, runtimemessaging.DomainEvent{
		EventID:       fact.EventID,
		Type:          fact.EventType,
		AggregateType: "ContentReaction",
		AggregateID:   fact.AggregateID,
		Payload:       payload,
		OccurredAt:    fact.OccurredAt.UTC().Format(time.RFC3339Nano),
	})
}

var _ reactionports.OutboxPublisher = (*ContentReactionOutboxPublisher)(nil)
