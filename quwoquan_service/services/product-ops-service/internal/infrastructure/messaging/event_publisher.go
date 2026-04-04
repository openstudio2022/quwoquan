package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/repository"
)

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

func (p *RedisEventPublisher) Publish(ctx context.Context, event repository.DomainEvent) error {
	channel := fmt.Sprintf("events.ops.%s", event.Type)
	envelope := map[string]any{
		"meta": map[string]any{
			"topic":  channel,
			"src":    event.AggregateType + "/" + event.AggregateID,
			"sentAt": time.Now().UTC().Format(time.RFC3339Nano),
			"producer": map[string]string{
				"service": p.service,
			},
		},
		"payload": map[string]any{
			"type":          event.Type,
			"aggregateType": event.AggregateType,
			"aggregateId":   event.AggregateID,
			"data":          event.Payload,
			"occurredAt":    event.OccurredAt,
		},
	}
	data, err := json.Marshal(envelope)
	if err != nil {
		return fmt.Errorf("marshal ops event: %w", err)
	}
	if err := p.redis.Publish(ctx, channel, string(data)); err != nil {
		p.logger.Warn("ops event publish failed", "channel", channel, "err", err)
		return fmt.Errorf("publish ops event: %w", err)
	}
	return nil
}
