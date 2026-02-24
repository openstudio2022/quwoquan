package runtimeobservability

import (
	"bytes"
	"testing"
)

func TestIOAccessLogValidateAppOrigin(t *testing.T) {
	entry := IOAccessLog{
		SchemaVersion:  "v1",
		Service:        "gateway-service",
		Timestamp:      "2026-02-21T10:10:10Z",
		Origin:         "app.http",
		Direction:      DirectionInbound,
		Endpoint:       "chat.message.create",
		SourceID:       "quwoquan_app",
		TraceID:        "APP.sess.chat.message.create.l9z1y4.2f8k",
		RequestID:      "APP.chat.message.create.l9z1y4.2f8k",
		SessionID:      "sess-001",
		Src:            "app",
		DevicePlatform: "ios",
		AppVersion:     "1.0.0",
		PageID:         "chat.message.list",
		Status:         "success",
		DurationMs:     45,
		MessageSize:    128,
	}
	if err := entry.Validate(); err != nil {
		t.Fatalf("validate failed: %v", err)
	}
}

func TestIOAccessLogValidateServiceOrigin(t *testing.T) {
	entry := IOAccessLog{
		SchemaVersion:     "v1",
		Service:           "chat-service",
		Timestamp:         "2026-02-21T10:10:10Z",
		Origin:            "service.mq",
		Direction:         DirectionOutbound,
		Endpoint:          "chat.message.deliver",
		SourceID:          "chat-service",
		TraceID:           "SVC.sess.chat.message.deliver.l9z1y4.2f8k",
		RequestID:         "SVC.chat.message.deliver.l9z1y4.2f8k",
		SessionID:         "run-001",
		Src:               "service",
		ServiceName:       "chat-service",
		ServiceInstanceID: "chat-pod-01",
		Status:            "success",
		DurationMs:        20,
		MessageSize:       2048,
	}
	if err := entry.Validate(); err != nil {
		t.Fatalf("validate failed: %v", err)
	}
}

func TestIOAccessLogValidateErrorCodePattern(t *testing.T) {
	var out bytes.Buffer
	logger := NewIOAccessLogger(&out)
	entry := IOAccessLog{
		SchemaVersion:     "v1",
		Service:           "chat-service",
		Timestamp:         "2026-02-21T10:10:10Z",
		Origin:            "service.http",
		Direction:         DirectionInbound,
		Endpoint:          "chat.message.create",
		SourceID:          "gateway-service",
		TraceID:           "SVC.sess.chat.message.create.l9z1y4.2f8k",
		RequestID:         "SVC.chat.message.create.l9z1y4.2f8k",
		SessionID:         "run-001",
		Src:               "service",
		ServiceName:       "chat-service",
		ServiceInstanceID: "chat-pod-01",
		Status:            "failed",
		DurationMs:        10,
		ErrorCode:         "CHAT.USER.invalid_argument",
		MessageSize:       512,
	}
	if err := logger.Write(entry); err != nil {
		t.Fatalf("logger write failed: %v", err)
	}

	entry.ErrorCode = "bad.error.code"
	if err := logger.Write(entry); err == nil {
		t.Fatalf("invalid error code should fail")
	}
}

func TestIOAccessLogValidateStatus(t *testing.T) {
	entry := IOAccessLog{
		SchemaVersion:     "v1",
		Service:           "chat-service",
		Timestamp:         "2026-02-21T10:10:10Z",
		Origin:            "service.http",
		Direction:         DirectionInbound,
		Endpoint:          "chat.message.create",
		SourceID:          "gateway-service",
		TraceID:           "SVC.sess.chat.message.create.l9z1y4.2f8k",
		RequestID:         "SVC.chat.message.create.l9z1y4.2f8k",
		SessionID:         "run-001",
		Src:               "service",
		ServiceName:       "chat-service",
		ServiceInstanceID: "chat-pod-01",
		Status:            "unknown",
		DurationMs:        20,
		MessageSize:       128,
	}
	if err := entry.Validate(); err == nil {
		t.Fatalf("invalid status should fail")
	}
}

