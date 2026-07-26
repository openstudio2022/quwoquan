package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
)

type RedisEventPublisher struct {
	transport runtimemessaging.MessageTransport
	service   string
	logger    *slog.Logger
}

func NewRedisEventPublisherWithTransport(
	transport runtimemessaging.MessageTransport,
	serviceName string,
	logger *slog.Logger,
) *RedisEventPublisher {
	if transport == nil {
		panic("product-ops event publisher requires a message transport")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &RedisEventPublisher{transport: transport, service: serviceName, logger: logger}
}

func (p *RedisEventPublisher) Publish(ctx context.Context, event runtimemessaging.DomainEvent) error {
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
	if err := p.transport.PublishEphemeral(ctx, runtimemessaging.EphemeralMessage{
		Channel: channel,
		Payload: data,
	}); err != nil {
		p.logger.Warn("ops event publish failed", "channel", channel, "err", err)
		return fmt.Errorf("publish ops event: %w", err)
	}
	return nil
}
