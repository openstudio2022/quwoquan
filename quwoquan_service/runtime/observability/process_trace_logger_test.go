package runtimeobservability

import (
	"bytes"
	"strings"
	"testing"
)

func TestProcessTraceLogger_LevelControl(t *testing.T) {
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

	logger, err := NewProcessTraceLogger(&standard, &errorBuf, TraceLogLevelInfo, filter)
	if err != nil {
		t.Fatalf("new logger failed: %v", err)
	}

	entry := ProcessTraceLog{
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
		Step:              "persist_message",
		Event:             "db_write",
		Result:            "ok",
		Level:             TraceLogLevelDebug,
	}

	// info mode skips debug trace logs
	if err := logger.Write(entry, "Message", "create", map[string]any{"content": "hello"}, map[string]any{"messageId": "m-1"}); err != nil {
		t.Fatalf("write failed: %v", err)
	}
	if standard.Len() != 0 {
		t.Fatalf("debug log should be skipped in info mode")
	}

	entry.Level = TraceLogLevelInfo
	if err := logger.Write(entry, "Message", "create", map[string]any{"content": "hello"}, map[string]any{"messageId": "m-1"}); err != nil {
		t.Fatalf("write failed: %v", err)
	}
	if !strings.Contains(standard.String(), "\"inputKv\":{\"content\":\"***\"}") {
		t.Fatalf("expected metadata filtered input kv in payload: %s", standard.String())
	}
}

