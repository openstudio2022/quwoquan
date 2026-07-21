package livekit

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestLiveKitProviderErrorDoesNotExposeResponseBody(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path != "/twirp/livekit.RoomService/CreateRoom" {
			t.Fatalf("path=%q", request.URL.Path)
		}
		writer.WriteHeader(http.StatusUnauthorized)
		_, _ = writer.Write([]byte(`{"error":"provider diagnostic must remain private"}`))
	}))
	defer server.Close()

	adapter := NewLiveKitRoomAdapter(server.URL, "api-key", "api-secret")
	err := adapter.CreateRoom(context.Background(), "call-123", 2)
	if err == nil {
		t.Fatal("CreateRoom() error = nil")
	}

	message := err.Error()
	if !strings.Contains(message, "status=401") || !strings.Contains(message, "body_digest=") {
		t.Fatalf("error=%q", message)
	}
	if strings.Contains(message, "provider diagnostic") {
		t.Fatalf("provider response leaked in error=%q", message)
	}
}
