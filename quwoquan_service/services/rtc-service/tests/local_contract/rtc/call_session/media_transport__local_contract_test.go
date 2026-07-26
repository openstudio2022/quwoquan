package local_contract

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/livekit"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/providerbinding"
)

func TestMediaTransportBindingAndProviderFailureRemainBounded(t *testing.T) {
	binding, err := providerbinding.ResolveMediaTransport("alpha", runtimeconfig.MapRuntimeConfigProvider{
		Values: map[string]string{
			"RTC_MEDIA_FIXTURE_CONNECTION_URL": "wss://fixture.local/rtc",
			"RTC_MEDIA_FIXTURE_API_KEY":        "fixture-key",
			"RTC_MEDIA_FIXTURE_API_SECRET":     "fixture-secret",
		},
	})
	if err != nil || binding.AdapterID != livekit.ProtocolFixtureAdapterID {
		t.Fatalf("alpha media binding = %#v, %v", binding, err)
	}
	if _, err := providerbinding.ResolveMediaTransport(
		"prod",
		runtimeconfig.MapRuntimeConfigProvider{},
	); err == nil {
		t.Fatal("blocked prod media binding must fail closed")
	}

	fixture := livekit.NewProtocolFixtureRoomAdapter()
	if err := fixture.CreateRoom(context.Background(), "call-123", 2); err != nil {
		t.Fatalf("protocol fixture CreateRoom: %v", err)
	}
	if err := fixture.DeleteRoom(context.Background(), "call-123"); err != nil {
		t.Fatalf("protocol fixture DeleteRoom: %v", err)
	}
	if _, err := fixture.IssueParticipantAccess(
		context.Background(),
		"call-123",
		"persona-123",
	); err == nil {
		t.Fatal("deleted fixture room was silently recreated for media access")
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"error":"provider diagnostic must remain private"}`))
	}))
	defer server.Close()

	err = livekit.NewLiveKitRoomAdapter(server.URL, "api-key", "api-secret").
		CreateRoom(context.Background(), "call-123", 2)
	if err == nil || !strings.Contains(err.Error(), "status=401") ||
		strings.Contains(err.Error(), "provider diagnostic") {
		t.Fatalf("bounded provider error = %v", err)
	}

	notFoundServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"code":"not_found"}`))
	}))
	defer notFoundServer.Close()
	if err := livekit.NewLiveKitRoomAdapter(
		notFoundServer.URL,
		"api-key",
		"api-secret",
	).DeleteRoom(context.Background(), "call-123"); err != nil {
		t.Fatalf("DeleteRoom() must tolerate already-revoked room retry: %v", err)
	}
}
