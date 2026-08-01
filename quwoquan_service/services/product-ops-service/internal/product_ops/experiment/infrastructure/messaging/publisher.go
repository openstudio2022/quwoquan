package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
)

const (
	ExperimentPolicyActivatedStream = "events.ops.experiment_policy_activated"
	experimentPolicyRetention       = 7 * 24 * time.Hour
)

type Publisher struct {
	transport Transport
}

type Transport interface {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
}

func NewPublisher(transport Transport) (*Publisher, error) {
	if transport == nil {
		return nil, fmt.Errorf("Experiment policy publisher requires message transport")
	}
	return &Publisher{transport: transport}, nil
}

func (p *Publisher) Publish(ctx context.Context, event runtimemessaging.DomainEvent) error {
	if strings.TrimSpace(event.Type) != "ExperimentPolicyActivated" {
		return fmt.Errorf("Experiment publisher rejects event type %q", event.Type)
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.AggregateID) == "" {
		return fmt.Errorf("Experiment policy event identity is required")
	}
	payload, err := json.Marshal(event.Payload)
	if err != nil {
		return fmt.Errorf("marshal Experiment policy payload: %w", err)
	}
	fields := map[string]string{
		"eventId": event.EventID, "eventType": event.Type,
		"aggregateType": event.AggregateType, "experimentId": event.AggregateID,
		"occurredAt": event.OccurredAt, "payloadJson": string(payload),
		"producer": "product-ops-service",
	}
	if _, err := p.transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: ExperimentPolicyActivatedStream,
		Fields: durableFields(fields),
	}); err != nil {
		return fmt.Errorf("append Experiment policy event: %w", err)
	}
	if err := p.transport.SetDurableRetention(ctx, ExperimentPolicyActivatedStream, experimentPolicyRetention); err != nil {
		return fmt.Errorf("retain Experiment policy stream: %w", err)
	}
	return nil
}

func durableFields(values map[string]string) []runtimemessaging.DurableField {
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

var _ runtimemessaging.EventPublisher = (*Publisher)(nil)
