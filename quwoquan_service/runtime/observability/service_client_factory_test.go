package runtimeobservability

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"strings"
	"testing"
)

type fixedResponseRoundTripper struct{}

func (f fixedResponseRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	return &http.Response{
		StatusCode:    http.StatusOK,
		ContentLength: 20,
		Body:          io.NopCloser(strings.NewReader("ok")),
	}, nil
}

func TestFallbackEndpointName(t *testing.T) {
	got := fallbackEndpointName("chat-service", http.MethodGet, "/v1/chat/conversations/{conversationId}/messages")
	expect := "chat.get.v1_chat_conversations_id_messages"
	if got != expect {
		t.Fatalf("fallback endpoint mismatch, got=%s expect=%s", got, expect)
	}
}

func TestNewOrchestratorClient_UsesMappedEndpoint(t *testing.T) {
	var standard bytes.Buffer
	var errorBuf bytes.Buffer
	ioLogger := NewIOAccessLogger(&standard)
	processLogger, _ := NewProcessTraceLogger(&standard, &errorBuf, TraceLogLevelInfo, NewKVMetadataFilter(nil))
	exceptionLogger, _ := NewExceptionLogger(&standard, &errorBuf, NewKVMetadataFilter(nil))

	client := NewOrchestratorClient(fixedResponseRoundTripper{}, ioLogger, processLogger, exceptionLogger)

	req, _ := http.NewRequest(http.MethodGet, "http://example/v1/content/feed", nil)
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
	_ = resp.Body.Close()

	logs, err := parseJSONLines(standard.String())
	if err != nil {
		t.Fatalf("parse logs failed: %v", err)
	}
	found := false
	for _, log := range logs {
		if endpoint, ok := log["endpoint"].(string); ok && endpoint == "content.feed.list" {
			found = true
		}
	}
	if !found {
		t.Fatalf("expected mapped endpoint content.feed.list in logs")
	}
}

