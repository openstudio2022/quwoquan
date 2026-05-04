package main

import (
	"net/http"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestAlphaRuntimeIdentityAndConfigLoadsSameNamedOverlay(t *testing.T) {
	t.Setenv("SERVICE_NAME", "assistant-service")
	t.Setenv("APP_ENV", "alpha")
	t.Setenv("CONFIG_VERSION", "")
	t.Setenv("IMAGE_VERSION", "")

	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		t.Fatalf("resolveRuntimeIdentity() error = %v", err)
	}
	if serviceName != "assistant-service" || appEnv != "alpha" || configRoot != "" || configVersion != "" || imageVersion != "" {
		t.Fatalf("runtime identity = %q %q %q %q %q", serviceName, appEnv, configRoot, configVersion, imageVersion)
	}

	root := t.TempDir()
	writeConfig(t, root, "default", `service:
  http:
    addr: ":18080"
`)
	writeConfig(t, root, "alpha", `service:
  http:
    addr: ":18087"
`)
	writeConfig(t, root, "beta", `service:
  http:
    addr: ":18088"
`)

	cfg, err := loadRuntimeConfig(serviceName, appEnv, root, "")
	if err != nil {
		t.Fatalf("loadRuntimeConfig() error = %v", err)
	}
	if cfg.Service.HTTP.Addr != ":18087" {
		t.Fatalf("addr=%q, want alpha overlay :18087", cfg.Service.HTTP.Addr)
	}
}

func TestCurrentRuntimeEnvIsRejected(t *testing.T) {
	t.Setenv("APP_ENV", "local")
	if _, _, _, _, _, err := resolveRuntimeIdentity(); err == nil {
		t.Fatal("resolveRuntimeIdentity() should reject APP_ENV=local")
	}

	t.Setenv("APP_ENV", "integration")
	if _, _, _, _, _, err := resolveRuntimeIdentity(); err == nil {
		t.Fatal("resolveRuntimeIdentity() should reject APP_ENV=integration")
	}
}

func TestAssistantHTTPWriteTimeoutDefaultsForStreaming(t *testing.T) {
	t.Setenv("ASSISTANT_HTTP_WRITE_TIMEOUT_SECONDS", "")
	if got := assistantHTTPWriteTimeout(); got != 180*time.Second {
		t.Fatalf("write timeout=%s, want 180s", got)
	}
}

func TestSearchProviderTimeoutHasRealtimeFloor(t *testing.T) {
	if got := searchProviderTimeout(10_000); got != 45*time.Second {
		t.Fatalf("search timeout=%s, want 45s", got)
	}
	client := searchHTTPClient(10_000)
	if client.Timeout != 45*time.Second {
		t.Fatalf("client timeout=%s, want 45s", client.Timeout)
	}
	transport, ok := client.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("transport type=%T, want *http.Transport", client.Transport)
	}
	if transport.TLSHandshakeTimeout != 45*time.Second {
		t.Fatalf("tls handshake timeout=%s, want 45s", transport.TLSHandshakeTimeout)
	}
}

func TestShouldTryWeatherLookupUsesModelLocationAndSearchQueries(t *testing.T) {
	if !shouldTryWeatherLookup("", "outdoor plan", "", "Shenzhen", nil) {
		t.Fatal("locationSearchName should route to weather lookup")
	}
	if !shouldTryWeatherLookup("", "outdoor plan", "", "", map[string]any{
		"searchQueries": []any{
			map[string]any{"dimension": "weather", "query": "Shenzhen forecast"},
		},
	}) {
		t.Fatal("weather searchQueries should route to weather lookup")
	}
}

func writeConfig(t *testing.T, root, env, content string) {
	t.Helper()
	dir := filepath.Join(root, "configs", "assistant-service", env)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatalf("mkdir %s: %v", dir, err)
	}
	if err := os.WriteFile(filepath.Join(dir, "config.yaml"), []byte(content), 0o644); err != nil {
		t.Fatalf("write config %s: %v", env, err)
	}
}
