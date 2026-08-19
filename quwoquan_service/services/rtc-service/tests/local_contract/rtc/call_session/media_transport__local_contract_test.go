package local_contract

import (
	"context"
	"net/http"
	"net/http/httptest"
	"slices"
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	rtcgenerated "quwoquan_service/services/rtc-service/generated/rtc/call_session"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/livekit"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/providerbinding"
)

const mediaTransportCapabilityID = "rtc.room.transport"

// 声明层拥有「哪个环境选哪个 SFU adapter 与材料键」，它是打包期 overlay 的输入；
// 未打包源码树不固化任何环境，多环境发射器只写出恒 false 的 CompiledBindingFor，
// 因此 ResolveMediaTransport 在四环境、任何材料组合下都必须 fail closed。
func TestMediaTransportBindingAndProviderFailureRemainBounded(t *testing.T) {
	if _, found := rtcgenerated.CompiledBindingFor(mediaTransportCapabilityID); found {
		t.Fatalf(
			"源码树编译进了环境绑定 capability=%s；环境只能由打包期 overlay 固化",
			mediaTransportCapabilityID,
		)
	}
	materials := []struct {
		name   string
		config runtimeconfig.MapRuntimeConfigProvider
	}{
		{name: "no material", config: runtimeconfig.MapRuntimeConfigProvider{}},
		{
			name: "complete material",
			config: runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{
				"RTC_MEDIA_CONNECTION_URL": "wss://rtc.example.test",
				"RTC_MEDIA_API_KEY":        "contract-key",
				"RTC_MEDIA_API_SECRET":     "contract-secret",
			}},
		},
	}
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		t.Run(environment, func(t *testing.T) {
			declared, found := rtcgenerated.ExternalProviderBindingFor(
				environment,
				mediaTransportCapabilityID,
			)
			if !found {
				t.Fatalf(
					"环境 %s 缺少 %s 声明，打包期无可固化输入",
					environment,
					mediaTransportCapabilityID,
				)
			}
			if declared.State != "enabled" || declared.AdapterID != livekit.AdapterID ||
				declared.TimeoutMilliseconds <= 0 {
				t.Fatalf("环境 %s 的媒体传输声明漂移: %+v", environment, declared)
			}
			if declared.EndpointEnvironmentKeys["connection"] !=
				"RTC_MEDIA_CONNECTION_URL" {
				t.Fatalf(
					"环境 %s 的连接材料键漂移: %+v",
					environment,
					declared.EndpointEnvironmentKeys,
				)
			}
			for _, environmentKey := range []string{
				"RTC_MEDIA_API_KEY",
				"RTC_MEDIA_API_SECRET",
			} {
				if !slices.Contains(declared.SecretEnvironmentKeys, environmentKey) {
					t.Fatalf("环境 %s 缺少凭据材料键 %s", environment, environmentKey)
				}
			}

			for _, material := range materials {
				_, err := providerbinding.ResolveMediaTransport(
					environment,
					material.config,
				)
				if err == nil || !strings.Contains(err.Error(), "binding is missing") {
					t.Fatalf(
						"环境 %s（%s）未打包时必须 fail closed，got %v",
						environment,
						material.name,
						err,
					)
				}
			}
		})
	}

	if _, err := providerbinding.ResolveMediaTransport("prod", nil); err == nil ||
		!strings.Contains(err.Error(), "no runtime config provider") {
		t.Fatalf("missing config provider must fail closed, got %v", err)
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
