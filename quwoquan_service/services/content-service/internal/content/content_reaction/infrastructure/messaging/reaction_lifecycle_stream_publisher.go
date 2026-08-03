package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
)

const (
	ReactionLifecycleStream          = "events.content.reaction_lifecycle"
	ReactionLifecycleStreamRetention = 7 * 24 * time.Hour
)

// ReactionLifecycleStreamPublisher is the durable cross-context delivery
// adapter for ContentReaction facts (interaction notification producers). The
// authoritative fact remains in Mongo outbox; Redis Stream is an at-least-once
// transport and consumers must dedupe by eventId.
type ReactionLifecycleStreamPublisher struct {
	redis rtredis.Client
}

func NewReactionLifecycleStreamPublisher(redis rtredis.Client) *ReactionLifecycleStreamPublisher {
	return &ReactionLifecycleStreamPublisher{redis: redis}
}

func (publisher *ReactionLifecycleStreamPublisher) Publish(ctx context.Context, fact reactionports.OutboxFact) error {
	if publisher == nil || publisher.redis == nil {
		return fmt.Errorf("reaction lifecycle stream publisher is not configured")
	}
	if strings.TrimSpace(fact.EventID) == "" || strings.TrimSpace(fact.EventType) == "" ||
		strings.TrimSpace(fact.AggregateID) == "" || fact.AggregateVersion <= 0 || fact.OccurredAt.IsZero() {
		return fmt.Errorf("reaction lifecycle fact identity is incomplete")
	}
	if !json.Valid(fact.Payload) {
		return fmt.Errorf("reaction lifecycle fact payload is not valid JSON")
	}
	_, err := publisher.redis.XAdd(ctx, ReactionLifecycleStream, map[string]string{
		"eventId":          fact.EventID,
		"eventType":        fact.EventType,
		"aggregateType":    "ContentReaction",
		"aggregateId":      fact.AggregateID,
		"aggregateVersion": strconv.FormatInt(fact.AggregateVersion, 10),
		"payload":          string(fact.Payload),
		"occurredAt":       fact.OccurredAt.UTC().Format(time.RFC3339Nano),
	})
	if err != nil {
		return fmt.Errorf("append reaction lifecycle stream: %w", err)
	}
	if err := publisher.redis.XTrimOlderThan(ctx, ReactionLifecycleStream, ReactionLifecycleStreamRetention); err != nil {
		return fmt.Errorf("trim reaction lifecycle stream retention: %w", err)
	}
	if err := publisher.redis.Expire(ctx, ReactionLifecycleStream, ReactionLifecycleStreamRetention); err != nil {
		return fmt.Errorf("refresh reaction lifecycle stream retention: %w", err)
	}
	return nil
}

var _ reactionports.OutboxPublisher = (*ReactionLifecycleStreamPublisher)(nil)
