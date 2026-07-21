package providerbinding

import (
	"strings"
	"testing"
	"time"

	runtimeconfig "quwoquan_service/runtime/config"
)

func TestResolveMediaTransportUsesGeneratedBindingAndFailsClosed(t *testing.T) {
	config := runtimeconfig.MapRuntimeConfigProvider{
		Values: map[string]string{
			"RTC_MEDIA_CONNECTION_URL": "wss://media.example.test",
			"RTC_MEDIA_API_KEY":        "test-key",
			"RTC_MEDIA_API_SECRET":     "test-secret",
		},
	}
	resolved, err := ResolveMediaTransport("alpha", config)
	if err != nil {
		t.Fatalf("ResolveMediaTransport(alpha) error = %v", err)
	}
	if resolved.AdapterID != "infra.livekit_sfu" ||
		resolved.ConnectionURL != "wss://media.example.test" ||
		resolved.APIKey != "test-key" ||
		resolved.APISecret != "test-secret" ||
		resolved.Timeout != 10*time.Second {
		t.Fatalf("resolved media transport = %#v", resolved)
	}

	if _, err := ResolveMediaTransport("beta", config); err == nil ||
		!strings.Contains(err.Error(), "not enabled") {
		t.Fatalf("blocked beta binding error = %v", err)
	}
	if _, err := ResolveMediaTransport(
		"alpha",
		runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{}},
	); err == nil || !strings.Contains(err.Error(), "connection material") {
		t.Fatalf("missing alpha connection error = %v", err)
	}
}
