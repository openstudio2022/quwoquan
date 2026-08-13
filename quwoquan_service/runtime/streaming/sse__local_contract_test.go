package streaming

import (
	"log/slog"
	"net/http"
	"os"
	"strings"
	"testing"
	"time"
)

func TestSSEServer_SendToUser(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))
	server := NewSSEServer(logger)

	client := newSSEClient("test-1", "user1", 10)
	server.addClient(client)

	sent := server.SendToUser("user1", SSEEvent{
		Event: "message",
		Data:  map[string]string{"text": "hello"},
	})
	if sent != 1 {
		t.Errorf("expected 1 sent, got %d", sent)
	}

	select {
	case event := <-client.Events:
		if event.Event != "message" {
			t.Errorf("event type: got %q, want %q", event.Event, "message")
		}
	case <-time.After(time.Second):
		t.Error("timeout waiting for event")
	}

	// Sending to different user should not reach user1
	sent = server.SendToUser("user2", SSEEvent{Data: "nope"})
	if sent != 0 {
		t.Errorf("should not send to user2, got %d", sent)
	}

	server.removeClient("test-1")
}

func TestSSEServer_ConnectedCount(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))
	server := NewSSEServer(logger)

	if server.ConnectedCount() != 0 {
		t.Error("should start with 0 connections")
	}

	c1 := newSSEClient("c1", "u1", 10)
	c2 := newSSEClient("c2", "u2", 10)
	server.addClient(c1)
	server.addClient(c2)

	if server.ConnectedCount() != 2 {
		t.Errorf("expected 2, got %d", server.ConnectedCount())
	}

	server.removeClient("c1")
	if server.ConnectedCount() != 1 {
		t.Errorf("expected 1, got %d", server.ConnectedCount())
	}
}

func TestWriteSSE_Format(t *testing.T) {
	var buf strings.Builder
	w := &fakeResponseWriter{buf: &buf}

	writeSSE(w, SSEEvent{
		ID:    "evt-1",
		Event: "message",
		Data:  map[string]string{"text": "hello"},
	})

	output := buf.String()
	if !strings.Contains(output, "id: evt-1") {
		t.Error("missing id field")
	}
	if !strings.Contains(output, "event: message") {
		t.Error("missing event field")
	}
	if !strings.Contains(output, `"text":"hello"`) {
		t.Error("missing data payload")
	}
}

type fakeResponseWriter struct {
	buf *strings.Builder
}

func (f *fakeResponseWriter) Header() http.Header        { return http.Header{} }
func (f *fakeResponseWriter) WriteHeader(int)             {}
func (f *fakeResponseWriter) Write(b []byte) (int, error) { return f.buf.Write(b) }
