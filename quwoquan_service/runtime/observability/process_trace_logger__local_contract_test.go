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
		Service:           "chat-service",
		TS:                "2026-02-21T10:10:10Z",
		Origin:            "service.http",
		Direction:         DirectionInbound,
		Endpoint:          "chat.message.create",
		SourceID:          "gateway-service",
		Trace:             "SVC.sess.chat.message.create.l9z1y4.2f8k",
		Req:               "SVC.chat.message.create.l9z1y4.2f8k",
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
	if !strings.Contains(standard.String(), `"inputKv":"{\"content\":\"***\"}"`) {
		t.Fatalf("expected string-only filtered input kv in payload: %s", standard.String())
	}
	if strings.Contains(standard.String(), "schema"+"Version") ||
		strings.Contains(standard.String(), `"sessionId"`) {
		t.Fatalf("process log must not contain forbidden fields: %s", standard.String())
	}
	if !strings.Contains(standard.String(), `"event":"db_write"`) ||
		!strings.Contains(standard.String(), `"result":"ok"`) {
		t.Fatalf("expected canonical runtime event/result fields: %s", standard.String())
	}
	if !strings.Contains(standard.String(), `"requestId":"SVC.chat.message.create.l9z1y4.2f8k"`) {
		t.Fatalf("process log must preserve request correlation: %s", standard.String())
	}
	if !strings.Contains(standard.String(), `"message":"persist_message"`) ||
		!strings.Contains(standard.String(), `"attributes":`) {
		t.Fatalf("expected structured message and attributes: %s", standard.String())
	}
}
