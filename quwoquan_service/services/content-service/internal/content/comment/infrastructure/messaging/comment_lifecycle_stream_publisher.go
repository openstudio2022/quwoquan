package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
)

const (
	CommentLifecycleStream          = "events.content.comment_lifecycle"
	CommentLifecycleStreamRetention = 7 * 24 * time.Hour
)

// CommentLifecycleStreamPublisher is the durable cross-context delivery adapter
// for Comment facts (interaction notification producers). The authoritative
// event remains in Mongo outbox; Redis Stream is an at-least-once transport
// and consumers must dedupe by eventId.
type CommentLifecycleStreamPublisher struct {
	redis rtredis.Client
}

func NewCommentLifecycleStreamPublisher(redis rtredis.Client) *CommentLifecycleStreamPublisher {
	return &CommentLifecycleStreamPublisher{redis: redis}
}

func (publisher *CommentLifecycleStreamPublisher) Publish(ctx context.Context, event commentports.OutboxEvent) error {
	if publisher == nil || publisher.redis == nil {
		return fmt.Errorf("comment lifecycle stream publisher is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 || event.OccurredAt.IsZero() {
		return fmt.Errorf("comment lifecycle event identity is incomplete")
	}
	if !json.Valid(event.Payload) {
		return fmt.Errorf("comment lifecycle event payload is not valid JSON")
	}
	_, err := publisher.redis.XAdd(ctx, CommentLifecycleStream, map[string]string{
		"eventId":          event.EventID,
		"eventType":        event.EventType,
		"aggregateType":    commentEventAggregateType(event.EventType),
		"aggregateId":      event.AggregateID,
		"aggregateVersion": strconv.FormatInt(event.AggregateVersion, 10),
		"payload":          string(event.Payload),
		"occurredAt":       event.OccurredAt.UTC().Format(time.RFC3339Nano),
	})
	if err != nil {
		return fmt.Errorf("append comment lifecycle stream: %w", err)
	}
	if err := publisher.redis.XTrimOlderThan(ctx, CommentLifecycleStream, CommentLifecycleStreamRetention); err != nil {
		return fmt.Errorf("trim comment lifecycle stream retention: %w", err)
	}
	if err := publisher.redis.Expire(ctx, CommentLifecycleStream, CommentLifecycleStreamRetention); err != nil {
		return fmt.Errorf("refresh comment lifecycle stream retention: %w", err)
	}
	return nil
}

var _ commentports.OutboxPublisher = (*CommentLifecycleStreamPublisher)(nil)
