package runtimeobservability

import (
	"bytes"
	"strings"
	"testing"
)

func TestExceptionLogger_WritesToErrorSink(t *testing.T) {
	var standard bytes.Buffer
	var errorBuf bytes.Buffer

	filter := NewKVMetadataFilter([]KVPolicy{
		{
			Model:     "Message",
			Operation: "create",
			Input: []KVRule{
				{Key: "content", Strategy: KVStrategyMask},
			},
			Output: []KVRule{
				{Key: "messageId", Strategy: KVStrategyAllow},
			},
		},
	})

	logger, err := NewExceptionLogger(&standard, &errorBuf, filter)
	if err != nil {
		t.Fatalf("new logger failed: %v", err)
	}

	entry := ExceptionLog{
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
		ErrorCode:         "CHAT.SYSTEM.internal_error",
		ErrorModule:       "CHAT",
		ErrorKind:         "SYSTEM",
		ErrorReason:       "internal_error",
		UserMessage:       "消息发送失败，请稍后重试",
		DebugMessage:      "db transaction rollback",
		FailurePoint:      "chat.message.create.persist",
	}

	if err := logger.Write(entry, "Message", "create", map[string]any{"content": "hello"}, map[string]any{"messageId": "m-1"}); err != nil {
		t.Fatalf("write failed: %v", err)
	}
	if standard.Len() != 0 {
		t.Fatalf("exception log should not write to standard sink")
	}
	if !strings.Contains(errorBuf.String(), "\"errorCode\":\"CHAT.SYSTEM.internal_error\"") {
		t.Fatalf("expected exception payload in error sink: %s", errorBuf.String())
	}
	if !strings.Contains(errorBuf.String(), "\"inputKv\":{\"content\":\"***\"}") {
		t.Fatalf("expected metadata filtered input kv in exception payload")
	}
}

