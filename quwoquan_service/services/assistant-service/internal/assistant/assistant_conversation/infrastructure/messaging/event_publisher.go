package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
)

// RedisEventPublisher publishes assistant learning events for downstream consumers.
type RedisEventPublisher struct {
	transport runtimemessaging.MessageTransport
	service   string
	logger    *slog.Logger
}

// NewRedisEventPublisherWithTransport accepts the preflighted runtime transport
// so composition roots never select a Redis scene for assistant event delivery.
func NewRedisEventPublisherWithTransport(
	transport runtimemessaging.MessageTransport,
	serviceName string,
	logger *slog.Logger,
) *RedisEventPublisher {
	if transport == nil {
		panic("assistant event publisher requires a message transport")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &RedisEventPublisher{transport: transport, service: serviceName, logger: logger}
}

func (p *RedisEventPublisher) Publish(ctx context.Context, event runtimemessaging.DomainEvent) error {
	channel := fmt.Sprintf("events.assistant.%s", event.Type)
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
		p.logger.Error("assistant event marshal failed", "event", event.Type, "err", err)
		return fmt.Errorf("marshal assistant event: %w", err)
	}
	if err := p.transport.PublishEphemeral(ctx, runtimemessaging.EphemeralMessage{
		Channel: channel,
		Payload: data,
	}); err != nil {
		p.logger.Warn("assistant event publish failed", "channel", channel, "err", err)
		return fmt.Errorf("publish to %s: %w", channel, err)
	}
	p.logger.Debug("assistant event published", "channel", channel, "aggregateId", event.AggregateID)
	return nil
}
