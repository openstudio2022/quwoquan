package runtimeobservability

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rterr "quwoquan_service/runtime/errors"
)

func parseJSONLines(raw string) ([]map[string]any, error) {
	lines := strings.Split(strings.TrimSpace(raw), "\n")
	results := make([]map[string]any, 0, len(lines))
	for _, line := range lines {
		if strings.TrimSpace(line) == "" {
			continue
		}
		obj := map[string]any{}
		if err := json.Unmarshal([]byte(line), &obj); err != nil {
			return nil, err
		}
		results = append(results, obj)
	}
	return results, nil
}

func TestHTTPServerMiddleware_EmitIOProcessException(t *testing.T) {
	var standard bytes.Buffer
	var errorBuf bytes.Buffer

	ioLogger := NewIOAccessLogger(&standard)
	filter := NewKVMetadataFilter(nil)
	processLogger, err := NewProcessTraceLogger(&standard, &errorBuf, TraceLogLevelInfo, filter)
	if err != nil {
		t.Fatalf("new process logger failed: %v", err)
	}
	exceptionLogger, err := NewExceptionLogger(&standard, &errorBuf, filter)
	if err != nil {
		t.Fatalf("new exception logger failed: %v", err)
	}

	mw := HTTPServerMiddleware(HTTPMiddlewareConfig{
		Service:           "gateway-service",
		Origin:            "service.http",
		Direction:         DirectionInbound,
		SourceID:          "gateway-service",
		Src:               "service",
		ServiceName:       "gateway-service",
		ServiceInstanceID: "gw-pod-01",
		EndpointResolver: func(r *http.Request) string {
			return "chat.message.create"
		},
	}, ioLogger, processLogger, exceptionLogger)

	handler := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rterr.WriteHTTPError(
			w,
			rterr.NewAppError(
				rterr.NewCode(rterr.ModuleChat, rterr.KindSystem, "message_persist_failed"),
				"消息发送失败，请稍后重试",
				"mongo write failed",
			),
			rterr.HTTPWriteOptionsFromRequest(r),
		)
	}))

	req := httptest.NewRequest(http.MethodPost, "/v1/chat/conversations/1/messages", nil)
	req.Header.Set("X-Trace-Id", "APP.sess.chat.message.create.t1.r1")
	req.Header.Set("X-Request-Id", "APP.chat.message.create.t1.r1")
	req.Header.Set("X-Client-Session-Id", "sess-001")
	req.Header.Set("X-User-Id", "u-1")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	standardLogs, err := parseJSONLines(standard.String())
	if err != nil {
		t.Fatalf("parse standard logs failed: %v", err)
	}
	if len(standardLogs) < 2 {
		t.Fatalf("expected process + io logs, got=%d", len(standardLogs))
	}

	foundIO := false
	for _, obj := range standardLogs {
		if obj["endpoint"] == "chat.message.create" {
			if obj["status"] == "failed" {
				foundIO = true
				break
			}
		}
	}
	if !foundIO {
		t.Fatalf("expected failed io access log in standard sink")
	}

	errorLogs, err := parseJSONLines(errorBuf.String())
	if err != nil {
		t.Fatalf("parse error logs failed: %v", err)
	}
	if len(errorLogs) == 0 {
		t.Fatalf("expected exception log in error sink")
	}
	if errorLogs[0]["errorCode"] == "" {
		t.Fatalf("expected errorCode in exception log")
	}
	if errorLogs[0]["errorCode"] != "CHAT.SYSTEM.message_persist_failed" {
		t.Fatalf("expected real error code, got=%v", errorLogs[0]["errorCode"])
	}
	if errorLogs[0]["businessObject"] != "cloud_request" || errorLogs[0]["functionModule"] != "runtime_errors" {
		t.Fatalf("expected runtime location fields, got=%+v", errorLogs[0])
	}
}

func TestHTTPServerMiddleware_PanicWritesRuntimeErrorResponse(t *testing.T) {
	var standard bytes.Buffer
	var errorBuf bytes.Buffer

	ioLogger := NewIOAccessLogger(&standard)
	filter := NewKVMetadataFilter(nil)
	processLogger, err := NewProcessTraceLogger(&standard, &errorBuf, TraceLogLevelInfo, filter)
	if err != nil {
		t.Fatalf("new process logger failed: %v", err)
	}
	exceptionLogger, err := NewExceptionLogger(&standard, &errorBuf, filter)
	if err != nil {
		t.Fatalf("new exception logger failed: %v", err)
	}

	mw := HTTPServerMiddleware(HTTPMiddlewareConfig{
		Service:           "gateway-service",
		Origin:            "service.http",
		Direction:         DirectionInbound,
		SourceID:          "gateway-service",
		Src:               "service",
		ServiceName:       "gateway-service",
		ServiceInstanceID: "gw-pod-01",
	}, ioLogger, processLogger, exceptionLogger)

	handler := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		panic("boom")
	}))
	req := httptest.NewRequest(http.MethodGet, "/panic", nil)
	req.Header.Set("X-Trace-Id", "trace-panic")
	req.Header.Set("X-Request-Id", "req-panic")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("unexpected status: %d", rec.Code)
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("panic response should be runtime error json: %v body=%q", err, rec.Body.String())
	}
	if body["code"] != "UNKNOWN.SYSTEM.internal_error" {
		t.Fatalf("unexpected code: %+v", body)
	}
	if body["requestId"] != "req-panic" || body["traceId"] != "trace-panic" {
		t.Fatalf("missing request/trace ids: %+v", body)
	}
	if _, ok := body["location"].(map[string]any); !ok {
		t.Fatalf("missing runtime location: %+v", body)
	}
	if _, ok := body["context"].(map[string]any); !ok {
		t.Fatalf("missing runtime context: %+v", body)
	}
}

func TestMQMiddleware_EmitIntegratedLogs(t *testing.T) {
	var standard bytes.Buffer
	var errorBuf bytes.Buffer

	ioLogger := NewIOAccessLogger(&standard)
	filter := NewKVMetadataFilter([]KVPolicy{
		{
			Model:     "Message",
			Operation: "create",
			Input: []KVRule{
				{Key: "topic", Strategy: KVStrategyAllow},
				{Key: "messageId", Strategy: KVStrategyAllow},
			},
			Output: []KVRule{
				{Key: "result", Strategy: KVStrategyAllow},
			},
		},
	})
	processLogger, _ := NewProcessTraceLogger(&standard, &errorBuf, TraceLogLevelInfo, filter)
	exceptionLogger, _ := NewExceptionLogger(&standard, &errorBuf, filter)

	consumer := WrapMQConsumer(func(ctx context.Context, msg MQMessage) error {
		return errors.New("consume failed")
	}, MQMiddlewareConfig{
		Service:           "chat-service",
		Origin:            "service.mq",
		Direction:         DirectionInbound,
		Endpoint:          "chat.message.consume",
		SourceID:          "chat-service",
		Src:               "service",
		ServiceName:       "chat-service",
		ServiceInstanceID: "chat-pod-01",
		Model:             "Message",
		Operation:         "create",
	}, ioLogger, processLogger, exceptionLogger)

	ctx := WithCorrelationMeta(context.Background(), CorrelationMeta{
		TraceID:   "SVC.sess.chat.message.consume.t1.r1",
		RequestID: "SVC.chat.message.consume.t1.r1",
		SessionID: "run-01",
		UserID:    "u-1",
	})
	_ = consumer(ctx, MQMessage{
		Topic:   "chat-message-topic",
		ID:      "msg-001",
		Payload: []byte("hello"),
	})

	standardLogs, err := parseJSONLines(standard.String())
	if err != nil {
		t.Fatalf("parse standard logs failed: %v", err)
	}
	errorLogs, err := parseJSONLines(errorBuf.String())
	if err != nil {
		t.Fatalf("parse error logs failed: %v", err)
	}
	if len(standardLogs) < 2 {
		t.Fatalf("expected process + io logs for mq consumer")
	}
	if len(errorLogs) == 0 {
		t.Fatalf("expected exception log for mq consumer failure")
	}
}

func TestUAT_CorrelationAcrossThreeLogs(t *testing.T) {
	var standard bytes.Buffer
	var errorBuf bytes.Buffer

	ioLogger := NewIOAccessLogger(&standard)
	filter := NewKVMetadataFilter(nil)
	processLogger, _ := NewProcessTraceLogger(&standard, &errorBuf, TraceLogLevelInfo, filter)
	exceptionLogger, _ := NewExceptionLogger(&standard, &errorBuf, filter)

	traceID := "APP.sess.chat.message.create.l9z1y4.2f8k"
	requestID := "APP.chat.message.create.l9z1y4.2f8k"
	sessionID := "sess-001"

	mw := HTTPServerMiddleware(HTTPMiddlewareConfig{
		Service:           "gateway-service",
		Origin:            "service.http",
		Direction:         DirectionInbound,
		SourceID:          "gateway-service",
		Src:               "service",
		ServiceName:       "gateway-service",
		ServiceInstanceID: "gw-pod-01",
		EndpointResolver: func(r *http.Request) string {
			return "chat.message.create"
		},
	}, ioLogger, processLogger, exceptionLogger)

	handler := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/conversations/1/messages", nil)
	req.Header.Set("X-Trace-Id", traceID)
	req.Header.Set("X-Request-Id", requestID)
	req.Header.Set("X-Client-Session-Id", sessionID)
	req.Header.Set("X-User-Id", "u-1")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	standardLogs, _ := parseJSONLines(standard.String())
	errorLogs, _ := parseJSONLines(errorBuf.String())
	if len(standardLogs) == 0 || len(errorLogs) == 0 {
		t.Fatalf("expected both standard and error logs")
	}

	for _, obj := range standardLogs {
		if obj["traceId"] != traceID || obj["requestId"] != requestID || obj["sessionId"] != sessionID {
			t.Fatalf("standard log correlation mismatch: %+v", obj)
		}
	}
	for _, obj := range errorLogs {
		if obj["traceId"] != traceID || obj["requestId"] != requestID || obj["sessionId"] != sessionID {
			t.Fatalf("error log correlation mismatch: %+v", obj)
		}
	}
}
