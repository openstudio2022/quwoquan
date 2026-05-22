package runtimeobservability

import (
	"context"
	"fmt"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	runtimefailures "quwoquan_service/runtime/failures"
)

var (
	mqPublishTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "mq",
		Name:      "publish_total",
		Help:      "Total messages published by topic and status.",
	}, []string{"topic", "status"})

	mqPublishDurationSeconds = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: "mq",
		Name:      "publish_duration_seconds",
		Help:      "Message publish latency in seconds.",
		Buckets:   prometheus.DefBuckets,
	}, []string{"topic"})

	mqConsumeTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "mq",
		Name:      "consume_total",
		Help:      "Total messages consumed by topic, consumer_group, and status.",
	}, []string{"topic", "consumer_group", "status"})

	mqConsumeDurationSeconds = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: "mq",
		Name:      "consume_duration_seconds",
		Help:      "Message consume processing latency in seconds.",
		Buckets:   prometheus.DefBuckets,
	}, []string{"topic", "consumer_group"})
)

type MQMessage struct {
	Topic   string
	ID      string
	Payload []byte
}

type MQConsumerHandler func(ctx context.Context, msg MQMessage) error
type MQPublisher func(ctx context.Context, msg MQMessage) error

type MQMiddlewareConfig struct {
	Service   string
	Origin    string
	Direction string
	Endpoint  string
	SourceID  string
	// ConsumerGroup is used for mq_consume_* Prometheus labels; when empty, SourceID is used.
	ConsumerGroup     string
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
			SubAccountID:      meta.SubAccountID,
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
		durSec := time.Since(start).Seconds()
		consumerGroup := cfg.ConsumerGroup
		if consumerGroup == "" {
			consumerGroup = cfg.SourceID
		}
		if consumerGroup == "" {
			consumerGroup = "unknown"
		}
		metricStatus := "ok"
		if err != nil {
			metricStatus = "error"
		}
		mqConsumeTotal.WithLabelValues(msg.Topic, consumerGroup, metricStatus).Inc()
		mqConsumeDurationSeconds.WithLabelValues(msg.Topic, consumerGroup).Observe(durSec)

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
				SubAccountID:      meta.SubAccountID,
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
			SubAccountID:      meta.SubAccountID,
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
			SubAccountID:      meta.SubAccountID,
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
		durSec := time.Since(start).Seconds()
		metricStatus := "ok"
		if err != nil {
			metricStatus = "error"
		}
		mqPublishTotal.WithLabelValues(msg.Topic, metricStatus).Inc()
		mqPublishDurationSeconds.WithLabelValues(msg.Topic).Observe(durSec)

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
				SubAccountID:      meta.SubAccountID,
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
			SubAccountID:      meta.SubAccountID,
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
			SubAccountID:      meta.SubAccountID,
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
