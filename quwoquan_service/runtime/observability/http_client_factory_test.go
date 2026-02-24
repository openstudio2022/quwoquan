package runtimeobservability

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"
)

type sequenceRoundTripper struct {
	attempts int
	results  []struct {
		status int
		err    error
	}
	lastReq *http.Request
}

func (s *sequenceRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	s.attempts++
	s.lastReq = req
	idx := s.attempts - 1
	if idx >= len(s.results) {
		idx = len(s.results) - 1
	}
	r := s.results[idx]
	if r.err != nil {
		return nil, r.err
	}
	return &http.Response{
		StatusCode:    r.status,
		ContentLength: 10,
		Body:          io.NopCloser(strings.NewReader("response")),
	}, nil
}

func TestNewObservedHTTPClient_RetryAndSingleTerminalLogging(t *testing.T) {
	var standard bytes.Buffer
	var errorBuf bytes.Buffer

	ioLogger := NewIOAccessLogger(&standard)
	processLogger, _ := NewProcessTraceLogger(&standard, &errorBuf, TraceLogLevelInfo, NewKVMetadataFilter(nil))
	exceptionLogger, _ := NewExceptionLogger(&standard, &errorBuf, NewKVMetadataFilter(nil))

	seqRT := &sequenceRoundTripper{
		results: []struct {
			status int
			err    error
		}{
			{status: http.StatusServiceUnavailable, err: nil},
			{status: http.StatusOK, err: nil},
		},
	}

	client := NewObservedHTTPClient(
		seqRT,
		HTTPClientFactoryConfig{
			Timeout:      2 * time.Second,
			MaxRetries:   2,
			RetryBackoff: 1 * time.Millisecond,
			RetryOnCodes: map[int]struct{}{
				http.StatusServiceUnavailable: {},
			},
		},
		HTTPClientMiddlewareConfig{
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
		},
		ioLogger,
		processLogger,
		exceptionLogger,
	)

	req, _ := http.NewRequest(http.MethodGet, "http://content.internal/v1/content/feed", nil)
	req = req.WithContext(WithCorrelationMeta(context.Background(), CorrelationMeta{
		TraceID:   "SVC.sess.content.feed.list.t1.r1",
		RequestID: "SVC.content.feed.list.t1.r1",
		SessionID: "run-001",
		UserID:    "u-1",
	}))
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("client do failed: %v", err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("unexpected status: %d", resp.StatusCode)
	}
	if seqRT.attempts != 2 {
		t.Fatalf("expected 2 attempts by retry transport, got=%d", seqRT.attempts)
	}

	standardLogs, err := parseJSONLines(standard.String())
	if err != nil {
		t.Fatalf("parse logs failed: %v", err)
	}
	if len(standardLogs) < 2 {
		t.Fatalf("expected process+io logs, got=%d", len(standardLogs))
	}
	if errorBuf.Len() != 0 {
		t.Fatalf("error sink should be empty in success flow")
	}
}

