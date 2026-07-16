package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	commentports "quwoquan_service/services/content-service/internal/domain/comment/ports"
)

type CommentOutboxPublisher struct {
	publisher runtimemessaging.EventPublisher
}

func NewCommentOutboxPublisher(publisher runtimemessaging.EventPublisher) *CommentOutboxPublisher {
	return &CommentOutboxPublisher{publisher: publisher}
}

func (p *CommentOutboxPublisher) Publish(ctx context.Context, event commentports.OutboxEvent) error {
	if p == nil || p.publisher == nil {
		return fmt.Errorf("Comment outbox publisher is not configured")
	}
	if event.EventID == "" || event.EventType == "" {
		return fmt.Errorf("Comment outbox identity is incomplete")
	}
	var payload map[string]any
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode Comment outbox payload: %w", err)
	}
	return p.publisher.Publish(ctx, runtimemessaging.DomainEvent{
		EventID: event.EventID, Type: event.EventType, AggregateType: "Comment",
		AggregateID: event.AggregateID, Payload: payload,
		OccurredAt: event.OccurredAt.UTC().Format(time.RFC3339Nano),
	})
}

var _ commentports.OutboxPublisher = (*CommentOutboxPublisher)(nil)
