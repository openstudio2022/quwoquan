package runtimemessaging

import (
	"context"

	robs "quwoquan_service/runtime/observability"
)

// MessageEnvelope is aligned with contracts/messages/envelope.schema.json.
type MessageEnvelope struct {
	Meta    MessageMeta    `json:"meta"`
	Payload map[string]any `json:"payload"`
}

type MessageMeta struct {
	MessageID     string          `json:"messageId"`
	Topic         string          `json:"topic"`
	Src           string          `json:"src"`
	TraceID       string          `json:"traceId"`
	ParentTraceID string          `json:"parentTraceId,omitempty"`
	CausationID   string          `json:"causationId,omitempty"`
	SentAt        string          `json:"sentAt"`
	Producer      MessageProducer `json:"producer"`
}

type MessageProducer struct {
	Service string `json:"service"`
	Env     string `json:"env,omitempty"`
	Version string `json:"version,omitempty"`
}

// EventPublisher 是跨域事件发布的公共机制接口；业务事件 payload 的强类型由
// ContractGraph 为各对象生成，公共层不提供通用 CRUD Repository。
type EventPublisher interface {
	Publish(ctx context.Context, event DomainEvent) error
}

// DomainEvent 是旧通用 Repository 退役期间保留的事件信封。
// 新事件必须由 metadata 生成 typed payload，并逐对象替换动态 Payload。
type DomainEvent struct {
	EventID       string         `json:"eventId,omitempty"`
	Type          string         `json:"type"`
	AggregateType string         `json:"aggregateType"`
	AggregateID   string         `json:"aggregateId"`
	Payload       map[string]any `json:"payload"`
	OccurredAt    string         `json:"occurredAt"`
}

type MQMiddlewareConfig = robs.MQMiddlewareConfig
type MQMessage = robs.MQMessage
type MQConsumerHandler = robs.MQConsumerHandler
type MQPublisher = robs.MQPublisher

func WrapMQConsumer(
	handler MQConsumerHandler,
	cfg MQMiddlewareConfig,
	ioLogger *robs.IOAccessLogger,
	processLogger *robs.ProcessTraceLogger,
	exceptionLogger *robs.ExceptionLogger,
) MQConsumerHandler {
	return robs.WrapMQConsumer(handler, cfg, ioLogger, processLogger, exceptionLogger)
}

func WrapMQPublisher(
	publisher MQPublisher,
	cfg MQMiddlewareConfig,
	ioLogger *robs.IOAccessLogger,
	processLogger *robs.ProcessTraceLogger,
	exceptionLogger *robs.ExceptionLogger,
) MQPublisher {
	return robs.WrapMQPublisher(publisher, cfg, ioLogger, processLogger, exceptionLogger)
}
