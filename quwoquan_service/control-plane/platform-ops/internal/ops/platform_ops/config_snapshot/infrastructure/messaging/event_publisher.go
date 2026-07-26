// Package messaging 提供 platform-ops-service 的 ops 域事件发布 adapter。
package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
)

// RedisEventPublisher 把 ops 域领域事件（如 ConfigLayerValueSet）发布到
// events.ops.{EventType} 频道，与 product-ops 的 ops 域频道口径一致。
type RedisEventPublisher struct {
	redis   rtredis.Client
	service string
	logger  *slog.Logger
}

func NewRedisEventPublisher(redis rtredis.Client, serviceName string, logger *slog.Logger) *RedisEventPublisher {
	if logger == nil {
		logger = slog.Default()
	}
	return &RedisEventPublisher{redis: redis, service: serviceName, logger: logger}
}

func (p *RedisEventPublisher) Publish(ctx context.Context, event runtimemessaging.DomainEvent) error {
	channel := fmt.Sprintf("events.ops.%s", event.Type)
	envelope := map[string]any{
		"meta": map[string]any{
			"topic":  channel,
			"src":    event.AggregateType + "/" + event.AggregateID,
			"sentAt": time.Now().UTC().Format(time.RFC3339),
			"svc":    p.service,
		},
		"eventId":       event.EventID,
		"type":          event.Type,
		"aggregateType": event.AggregateType,
		"aggregateId":   event.AggregateID,
		"payload":       event.Payload,
		"occurredAt":    event.OccurredAt,
	}
	raw, err := json.Marshal(envelope)
	if err != nil {
		return fmt.Errorf("marshal ops event envelope: %w", err)
	}
	if err := p.redis.Publish(ctx, channel, string(raw)); err != nil {
		return fmt.Errorf("publish ops event %s: %w", event.Type, err)
	}
	p.logger.Debug("ops event published", "channel", channel, "eventId", event.EventID)
	return nil
}

var _ runtimemessaging.EventPublisher = (*RedisEventPublisher)(nil)
