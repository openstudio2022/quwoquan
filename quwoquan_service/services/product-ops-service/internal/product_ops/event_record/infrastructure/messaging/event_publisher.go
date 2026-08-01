package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sort"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
)

const (
	premiumPoolStream    = "events.ops.premium_pool_entry"
	premiumPoolRetention = 7 * 24 * time.Hour
)

var premiumPoolEventTypes = map[string]struct{}{
	"PremiumPoolEntryUpserted":        {},
	"PremiumPoolEntryRolledBack":      {},
	"PremiumPoolEntryTakedownEjected": {},
}

type eventTransport interface {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
}

type RedisEventPublisher struct {
	transport eventTransport
	service   string
	logger    *slog.Logger
}

func NewRedisEventPublisherWithTransport(
	transport eventTransport,
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
	if _, premiumPoolEvent := premiumPoolEventTypes[strings.TrimSpace(event.Type)]; premiumPoolEvent {
		return p.publishPremiumPoolEvent(ctx, event)
	}
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
			"eventId":       event.EventID,
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

func (p *RedisEventPublisher) publishPremiumPoolEvent(
	ctx context.Context,
	event runtimemessaging.DomainEvent,
) error {
	if strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.AggregateType) != "PremiumPoolEntry" ||
		strings.TrimSpace(event.AggregateID) == "" ||
		strings.TrimSpace(event.OccurredAt) == "" {
		return fmt.Errorf("premium pool event identity is incomplete")
	}
	payload, err := json.Marshal(event.Payload)
	if err != nil {
		return fmt.Errorf("marshal premium pool event: %w", err)
	}
	fields := durableEventFields(map[string]string{
		"eventId":       strings.TrimSpace(event.EventID),
		"eventType":     strings.TrimSpace(event.Type),
		"aggregateType": "PremiumPoolEntry",
		"aggregateId":   strings.TrimSpace(event.AggregateID),
		"occurredAt":    strings.TrimSpace(event.OccurredAt),
		"payloadJson":   string(payload),
		"producer":      p.service,
	})
	if _, err := p.transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: premiumPoolStream,
		Fields: fields,
	}); err != nil {
		return fmt.Errorf("append premium pool event: %w", err)
	}
	if err := p.transport.SetDurableRetention(ctx, premiumPoolStream, premiumPoolRetention); err != nil {
		return fmt.Errorf("retain premium pool stream: %w", err)
	}
	return nil
}

func durableEventFields(values map[string]string) []runtimemessaging.DurableField {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	fields := make([]runtimemessaging.DurableField, 0, len(keys))
	for _, key := range keys {
		fields = append(fields, runtimemessaging.DurableField{Name: key, Value: values[key]})
	}
	return fields
}
