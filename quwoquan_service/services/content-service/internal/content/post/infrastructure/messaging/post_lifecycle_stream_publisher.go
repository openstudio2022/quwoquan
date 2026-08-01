package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

const (
	PostLifecycleStream          = "events.content.post_lifecycle"
	PostLifecycleStreamRetention = 7 * 24 * time.Hour
)

// PostLifecycleStreamPublisher is the durable cross-context delivery adapter
// for Post facts. The authoritative event remains in Mongo outbox; Redis
// Stream is an at-least-once transport and consumers must dedupe by eventId.
type PostLifecycleStreamPublisher struct {
	redis rtredis.Client
}

func NewPostLifecycleStreamPublisher(redis rtredis.Client) *PostLifecycleStreamPublisher {
	return &PostLifecycleStreamPublisher{redis: redis}
}

func (publisher *PostLifecycleStreamPublisher) Publish(ctx context.Context, event postports.OutboxEvent) error {
	if publisher == nil || publisher.redis == nil {
		return fmt.Errorf("post lifecycle stream publisher is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 || event.OccurredAt.IsZero() {
		return fmt.Errorf("post lifecycle event identity is incomplete")
	}
	if strings.TrimSpace(event.AggregateType) != "Post" {
		return fmt.Errorf("post lifecycle aggregate type must be Post")
	}
	if !json.Valid(event.Payload) {
		return fmt.Errorf("post lifecycle event payload is not valid JSON")
	}
	_, err := publisher.redis.XAdd(ctx, PostLifecycleStream, map[string]string{
		"eventId":          event.EventID,
		"eventType":        event.EventType,
		"aggregateType":    event.AggregateType,
		"aggregateId":      event.AggregateID,
		"aggregateVersion": strconv.FormatInt(event.AggregateVersion, 10),
		"payload":          string(event.Payload),
		"occurredAt":       event.OccurredAt.UTC().Format(time.RFC3339Nano),
	})
	if err != nil {
		return fmt.Errorf("append post lifecycle stream: %w", err)
	}
	if err := publisher.redis.XTrimOlderThan(ctx, PostLifecycleStream, PostLifecycleStreamRetention); err != nil {
		return fmt.Errorf("trim post lifecycle stream retention: %w", err)
	}
	if err := publisher.redis.Expire(ctx, PostLifecycleStream, PostLifecycleStreamRetention); err != nil {
		return fmt.Errorf("bound inactive post lifecycle stream retention: %w", err)
	}
	return nil
}

var _ postports.OutboxPublisher = (*PostLifecycleStreamPublisher)(nil)
