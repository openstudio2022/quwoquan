package runtimeobservability

import (
	"bytes"
	"context"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"
)

type mockRoundTripper struct {
	lastRequest *http.Request
	response    *http.Response
	err         error
}

func (m *mockRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	m.lastRequest = req
	if m.err != nil {
		return nil, m.err
	}
	return m.response, nil
}

func TestLoggedRoundTripper_OutboundSuccessAndHeaderInjection(t *testing.T) {
	var standard bytes.Buffer
	var errorBuf bytes.Buffer

	ioLogger := NewIOAccessLogger(&standard)
	processLogger, _ := NewProcessTraceLogger(&standard, &errorBuf, TraceLogLevelInfo, NewKVMetadataFilter(nil))
	exceptionLogger, _ := NewExceptionLogger(&standard, &errorBuf, NewKVMetadataFilter(nil))

	mockRT := &mockRoundTripper{
		response: &http.Response{
			StatusCode:    http.StatusOK,
			ContentLength: 88,
			Body:          io.NopCloser(strings.NewReader("ok")),
		},
	}
	rt := NewLoggedRoundTripper(mockRT, HTTPClientMiddlewareConfig{
		Service:           "orchestrator-service",
		Origin:            "service.http",
		Direction:         DirectionOutbound,
		SourceID:          "orchestrator-service",
		Src:               "service",
		ServiceName:       "orchestrator-service",
		ServiceInstanceID: "orch-pod-01",
		EndpointResolver: func(r *http.Request) string {
			return "content.feed.list"
		},
	}, ioLogger, processLogger, exceptionLogger)

	req, _ := http.NewRequest(http.MethodGet, "http://content.internal/v1/content/feed", nil)
	ctx := WithCorrelationMeta(context.Background(), CorrelationMeta{
		TraceID:   "SVC.sess.content.feed.list.l9z1y4.2f8k",
		RequestID: "SVC.content.feed.list.l9z1y4.2f8k",
		SessionID: "run-001",
		UserID:    "u-1",
	})
	req = req.WithContext(ctx)

	resp, err := rt.RoundTrip(req)
	if err != nil {
		t.Fatalf("round trip failed: %v", err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("unexpected status: %d", resp.StatusCode)
	}
	if mockRT.lastRequest.Header.Get("X-Trace-Id") == "" || mockRT.lastRequest.Header.Get("X-Request-Id") == "" {
		t.Fatalf("trace headers should be injected for outbound call")
	}

	standardLogs, err := parseJSONLines(standard.String())
	if err != nil {
		t.Fatalf("parse standard logs failed: %v", err)
	}
	if len(standardLogs) < 2 {
		t.Fatalf("expected process+io logs in standard sink")
	}
	if errorBuf.Len() != 0 {
		t.Fatalf("error sink should be empty on success")
	}
}

func TestLoggedRoundTripper_OutboundFailureToExceptionSink(t *testing.T) {
	var standard bytes.Buffer
	var errorBuf bytes.Buffer

	ioLogger := NewIOAccessLogger(&standard)
	processLogger, _ := NewProcessTraceLogger(&standard, &errorBuf, TraceLogLevelInfo, NewKVMetadataFilter(nil))
	exceptionLogger, _ := NewExceptionLogger(&standard, &errorBuf, NewKVMetadataFilter(nil))

	mockRT := &mockRoundTripper{
		err: errors.New("dial tcp: connection refused"),
	}
	rt := NewLoggedRoundTripper(mockRT, HTTPClientMiddlewareConfig{
		Service:           "orchestrator-service",
		Origin:            "service.http",
		Direction:         DirectionOutbound,
		SourceID:          "orchestrator-service",
		Src:               "service",
		ServiceName:       "orchestrator-service",
		ServiceInstanceID: "orch-pod-01",
		EndpointResolver: func(r *http.Request) string {
			return "content.feed.list"
		},
	}, ioLogger, processLogger, exceptionLogger)

	req, _ := http.NewRequest(http.MethodGet, "http://content.internal/v1/content/feed", nil)
	_, err := rt.RoundTrip(req)
	if err == nil {
		t.Fatalf("expected transport error")
	}

	standardLogs, parseErr := parseJSONLines(standard.String())
	if parseErr != nil {
		t.Fatalf("parse standard logs failed: %v", parseErr)
	}
	if len(standardLogs) < 2 {
		t.Fatalf("expected process+io logs in standard sink")
	}

	errorLogs, parseErr := parseJSONLines(errorBuf.String())
	if parseErr != nil {
		t.Fatalf("parse error logs failed: %v", parseErr)
	}
	if len(errorLogs) == 0 {
		t.Fatalf("expected exception log in error sink")
	}
	if errorLogs[0]["errorCode"] == "" {
		t.Fatalf("exception log should contain errorCode")
	}
}

