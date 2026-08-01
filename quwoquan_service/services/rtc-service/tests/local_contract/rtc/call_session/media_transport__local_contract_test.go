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
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		t.Run(environment, func(t *testing.T) {
			binding, err := providerbinding.ResolveMediaTransport(
				environment,
				runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{
					"RTC_MEDIA_CONNECTION_URL": "wss://rtc.example.test",
					"RTC_MEDIA_API_KEY":        "contract-key",
					"RTC_MEDIA_API_SECRET":     "contract-secret",
				}},
			)
			if err != nil || binding.AdapterID != livekit.AdapterID {
				t.Fatalf("media binding = %#v, %v", binding, err)
			}
			if _, err := providerbinding.ResolveMediaTransport(
				environment,
				runtimeconfig.MapRuntimeConfigProvider{},
			); err == nil {
				t.Fatal("missing Provider material must fail closed")
			}
		})
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"error":"provider diagnostic must remain private"}`))
	}))
	defer server.Close()

	err := livekit.NewLiveKitRoomAdapter(server.URL, "api-key", "api-secret").
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
