package runtimemessaging

import (
	robs "quwoquan_service/runtime/observability"
)

// MessageEnvelope is aligned with contracts/messages/envelope.schema.json.
type MessageEnvelope struct {
	Meta    MessageMeta      `json:"meta"`
	Payload map[string]any   `json:"payload"`
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
