package runtimeobservability

import (
	"context"
	"fmt"
	"time"

	runtimefailures "quwoquan_service/runtime/failures"
)

type MQMessage struct {
	Topic   string
	ID      string
	Payload []byte
}

type MQConsumerHandler func(ctx context.Context, msg MQMessage) error
type MQPublisher func(ctx context.Context, msg MQMessage) error

type MQMiddlewareConfig struct {
	Service           string
	Origin            string
	Direction         string
	Endpoint          string
	SourceID          string
	Src               string
	ServiceName       string
	ServiceInstanceID string
	Model             string
	Operation         string
}

func WrapMQConsumer(
	handler MQConsumerHandler,
	cfg MQMiddlewareConfig,
	ioLogger *IOAccessLogger,
	processLogger *ProcessTraceLogger,
	exceptionLogger *ExceptionLogger,
) MQConsumerHandler {
	return func(ctx context.Context, msg MQMessage) error {
		start := time.Now()
		meta, ok := CorrelationMetaFromContext(ctx)
		if !ok {
			seed := fmt.Sprintf("%d", time.Now().UnixNano())
			meta = CorrelationMeta{
				TraceID:   "MQ.trace." + seed,
				RequestID: "MQ.req." + seed,
				SessionID: "mq-sess-" + seed,
				UserID:    "anonymous",
			}
			ctx = WithCorrelationMeta(ctx, meta)
		}

		input := map[string]any{
			"topic":     msg.Topic,
			"messageId": msg.ID,
		}
		_ = processLogger.Write(ProcessTraceLog{
			SchemaVersion:     defaultSchemaVersion,
			Service:           cfg.Service,
			Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
			Origin:            cfg.Origin,
			Direction:         cfg.Direction,
			Endpoint:          cfg.Endpoint,
			SourceID:          cfg.SourceID,
			TraceID:           meta.TraceID,
			RequestID:         meta.RequestID,
			SessionID:         meta.SessionID,
			Src:               cfg.Src,
			UserID:            meta.UserID,
			PersonaID:         meta.PersonaID,
			PageID:            meta.PageID,
			DevicePlatform:    meta.DevicePlatform,
			AppVersion:        meta.AppVersion,
			ServiceName:       cfg.ServiceName,
			ServiceInstanceID: cfg.ServiceInstanceID,
			Step:              "mq_consume",
			Event:             "received",
			Result:            "start",
			Level:             TraceLogLevelInfo,
		}, cfg.Model, cfg.Operation, input, nil)

		err := handler(ctx, msg)
		status := "success"
		errorCode := ""
		if err != nil {
			status = "failed"
			errorCode = "MQ.SYSTEM.consume_failed"
			_ = exceptionLogger.Write(ExceptionLog{
				SchemaVersion:     defaultSchemaVersion,
				Service:           cfg.Service,
				Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
				Origin:            cfg.Origin,
				Direction:         cfg.Direction,
				Endpoint:          cfg.Endpoint,
				SourceID:          cfg.SourceID,
				TraceID:           meta.TraceID,
				RequestID:         meta.RequestID,
				SessionID:         meta.SessionID,
				Src:               cfg.Src,
				UserID:            meta.UserID,
				PersonaID:         meta.PersonaID,
				PageID:            meta.PageID,
				DevicePlatform:    meta.DevicePlatform,
				AppVersion:        meta.AppVersion,
				ServiceName:       cfg.ServiceName,
				ServiceInstanceID: cfg.ServiceInstanceID,
				ErrorCode:         errorCode,
				ErrorModule:       "MQ",
				ErrorKind:         string(runtimefailures.KindInternal),
				ErrorReason:       "consume_failed",
				UserMessage:       "消息消费失败，请稍后重试",
				DebugMessage:      err.Error(),
				FailurePoint:      cfg.Endpoint,
			}, cfg.Model, cfg.Operation, input, nil)
		}

		output := map[string]any{
			"result": status,
		}
		_ = processLogger.Write(ProcessTraceLog{
			SchemaVersion:     defaultSchemaVersion,
			Service:           cfg.Service,
			Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
			Origin:            cfg.Origin,
			Direction:         cfg.Direction,
			Endpoint:          cfg.Endpoint,
			SourceID:          cfg.SourceID,
			TraceID:           meta.TraceID,
			RequestID:         meta.RequestID,
			SessionID:         meta.SessionID,
			Src:               cfg.Src,
			UserID:            meta.UserID,
			PersonaID:         meta.PersonaID,
			PageID:            meta.PageID,
			DevicePlatform:    meta.DevicePlatform,
			AppVersion:        meta.AppVersion,
			ServiceName:       cfg.ServiceName,
			ServiceInstanceID: cfg.ServiceInstanceID,
			Step:              "mq_consume",
			Event:             "completed",
			Result:            status,
			Level:             TraceLogLevelInfo,
		}, cfg.Model, cfg.Operation, input, output)

		_ = ioLogger.Write(IOAccessLog{
			SchemaVersion:     defaultSchemaVersion,
			Service:           cfg.Service,
			Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
			Origin:            cfg.Origin,
			Direction:         cfg.Direction,
			Endpoint:          cfg.Endpoint,
			SourceID:          cfg.SourceID,
			TraceID:           meta.TraceID,
			RequestID:         meta.RequestID,
			SessionID:         meta.SessionID,
			Src:               cfg.Src,
			UserID:            meta.UserID,
			PersonaID:         meta.PersonaID,
			PageID:            meta.PageID,
			DevicePlatform:    meta.DevicePlatform,
			AppVersion:        meta.AppVersion,
			ServiceName:       cfg.ServiceName,
			ServiceInstanceID: cfg.ServiceInstanceID,
			Status:            status,
			DurationMs:        time.Since(start).Milliseconds(),
			ErrorCode:         errorCode,
			ErrorLocation:     "mq/message_consumer",
			ErrorContext:      "topic=" + msg.Topic + ";messageId=" + msg.ID,
			MessageSize:       int64(len(msg.Payload)),
		})
		return err
	}
}

func WrapMQPublisher(
	publisher MQPublisher,
	cfg MQMiddlewareConfig,
	ioLogger *IOAccessLogger,
	processLogger *ProcessTraceLogger,
	exceptionLogger *ExceptionLogger,
) MQPublisher {
	return func(ctx context.Context, msg MQMessage) error {
		start := time.Now()
		meta, ok := CorrelationMetaFromContext(ctx)
		if !ok {
			seed := fmt.Sprintf("%d", time.Now().UnixNano())
			meta = CorrelationMeta{
				TraceID:   "MQ.trace." + seed,
				RequestID: "MQ.req." + seed,
				SessionID: "mq-sess-" + seed,
				UserID:    "anonymous",
			}
		}
		input := map[string]any{
			"topic":     msg.Topic,
			"messageId": msg.ID,
		}
		err := publisher(ctx, msg)
		status := "success"
		errorCode := ""
		if err != nil {
			status = "failed"
			errorCode = "MQ.SYSTEM.publish_failed"
			_ = exceptionLogger.Write(ExceptionLog{
				SchemaVersion:     defaultSchemaVersion,
				Service:           cfg.Service,
				Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
				Origin:            cfg.Origin,
				Direction:         cfg.Direction,
				Endpoint:          cfg.Endpoint,
				SourceID:          cfg.SourceID,
				TraceID:           meta.TraceID,
				RequestID:         meta.RequestID,
				SessionID:         meta.SessionID,
				Src:               cfg.Src,
				UserID:            meta.UserID,
				PersonaID:         meta.PersonaID,
				PageID:            meta.PageID,
				DevicePlatform:    meta.DevicePlatform,
				AppVersion:        meta.AppVersion,
				ServiceName:       cfg.ServiceName,
				ServiceInstanceID: cfg.ServiceInstanceID,
				ErrorCode:         errorCode,
				ErrorModule:       "MQ",
				ErrorKind:         string(runtimefailures.KindInternal),
				ErrorReason:       "publish_failed",
				UserMessage:       "消息发送失败，请稍后重试",
				DebugMessage:      err.Error(),
				FailurePoint:      cfg.Endpoint,
			}, cfg.Model, cfg.Operation, input, nil)
		}

		output := map[string]any{
			"result": status,
		}
		_ = processLogger.Write(ProcessTraceLog{
			SchemaVersion:     defaultSchemaVersion,
			Service:           cfg.Service,
			Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
			Origin:            cfg.Origin,
			Direction:         cfg.Direction,
			Endpoint:          cfg.Endpoint,
			SourceID:          cfg.SourceID,
			TraceID:           meta.TraceID,
			RequestID:         meta.RequestID,
			SessionID:         meta.SessionID,
			Src:               cfg.Src,
			UserID:            meta.UserID,
			PersonaID:         meta.PersonaID,
			PageID:            meta.PageID,
			DevicePlatform:    meta.DevicePlatform,
			AppVersion:        meta.AppVersion,
			ServiceName:       cfg.ServiceName,
			ServiceInstanceID: cfg.ServiceInstanceID,
			Step:              "mq_publish",
			Event:             "completed",
			Result:            status,
			Level:             TraceLogLevelInfo,
		}, cfg.Model, cfg.Operation, input, output)

		_ = ioLogger.Write(IOAccessLog{
			SchemaVersion:     defaultSchemaVersion,
			Service:           cfg.Service,
			Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
			Origin:            cfg.Origin,
			Direction:         cfg.Direction,
			Endpoint:          cfg.Endpoint,
			SourceID:          cfg.SourceID,
			TraceID:           meta.TraceID,
			RequestID:         meta.RequestID,
			SessionID:         meta.SessionID,
			Src:               cfg.Src,
			UserID:            meta.UserID,
			PersonaID:         meta.PersonaID,
			PageID:            meta.PageID,
			DevicePlatform:    meta.DevicePlatform,
			AppVersion:        meta.AppVersion,
			ServiceName:       cfg.ServiceName,
			ServiceInstanceID: cfg.ServiceInstanceID,
			Status:            status,
			DurationMs:        time.Since(start).Milliseconds(),
			ErrorCode:         errorCode,
			ErrorLocation:     "mq/message_publisher",
			ErrorContext:      "topic=" + msg.Topic + ";messageId=" + msg.ID,
			MessageSize:       int64(len(msg.Payload)),
		})
		return err
	}
}
