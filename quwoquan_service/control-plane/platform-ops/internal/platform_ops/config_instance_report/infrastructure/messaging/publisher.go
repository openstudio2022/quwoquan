package messaging

import (
	"context"
	"encoding/json"
	"errors"
	"sort"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
)

const (
	configInstanceReportStream    = "events.ops.config_instance_report"
	configInstanceReportRetention = 7 * 24 * time.Hour
)

type durableTransport interface {
	AppendDurable(context.Context, runtimemessaging.DurableMessage) (string, error)
	SetDurableRetention(context.Context, string, time.Duration) error
}

type Publisher struct{ transport durableTransport }

func NewPublisher(transport durableTransport) (*Publisher, error) {
	if transport == nil {
		return nil, errors.New("config instance report publisher requires durable transport")
	}
	return &Publisher{transport: transport}, nil
}

func (publisher *Publisher) Publish(
	ctx context.Context,
	event runtimemessaging.DomainEvent,
) error {
	if strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.Type) != "ConfigInstanceReported" ||
		strings.TrimSpace(event.AggregateType) != "ConfigInstanceReport" ||
		strings.TrimSpace(event.AggregateID) == "" ||
		strings.TrimSpace(event.OccurredAt) == "" || event.Payload == nil {
		return errors.New("config instance report event is invalid")
	}
	payload, err := json.Marshal(event.Payload)
	if err != nil {
		return err
	}
	fields := map[string]string{
		"eventId": event.EventID, "eventType": event.Type,
		"aggregateType": event.AggregateType, "aggregateId": event.AggregateID,
		"occurredAt": event.OccurredAt, "payloadJson": string(payload),
	}
	keys := make([]string, 0, len(fields))
	for key := range fields {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	durableFields := make([]runtimemessaging.DurableField, 0, len(keys))
	for _, key := range keys {
		durableFields = append(durableFields, runtimemessaging.DurableField{
			Name: key, Value: strings.TrimSpace(fields[key]),
		})
	}
	if _, err := publisher.transport.AppendDurable(
		ctx,
		runtimemessaging.DurableMessage{
			Stream: configInstanceReportStream,
			Fields: durableFields,
		},
	); err != nil {
		return err
	}
	return publisher.transport.SetDurableRetention(
		ctx,
		configInstanceReportStream,
		configInstanceReportRetention,
	)
}
