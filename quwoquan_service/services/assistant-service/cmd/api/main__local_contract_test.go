package main

import (
	"context"
	"errors"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	assistantgenerated "quwoquan_service/services/assistant-service/internal/generated"
	"quwoquan_service/services/assistant-service/internal/infrastructure/searchclient"
)

func TestAccessTokenConfigFailsClosed(t *testing.T) {
	for _, key := range []string{
		"AUTH_JWT_SECRET",
		"AUTH_JWT_ISSUER",
		"AUTH_JWT_AUDIENCE",
		"AUTH_JWT_TOKEN_VERSION",
	} {
		t.Setenv(key, "")
	}
	if _, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	); err == nil {
		t.Fatal("missing access token config must fail")
	}

	t.Setenv("AUTH_JWT_SECRET", "short")
	t.Setenv("AUTH_JWT_ISSUER", "https://auth.quwoquan.test")
	t.Setenv("AUTH_JWT_AUDIENCE", "quwoquan-api")
	t.Setenv("AUTH_JWT_TOKEN_VERSION", "1")
	if _, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	); err == nil {
		t.Fatal("weak access token config must fail")
	}

	const secret = "0123456789abcdef0123456789abcdef"
	t.Setenv("AUTH_JWT_SECRET", secret)
	got, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		t.Fatalf("valid access token config rejected: %v", err)
	}
	if string(got.Secret) != secret ||
		got.Issuer != "https://auth.quwoquan.test" ||
		got.Audience != "quwoquan-api" ||
		got.TokenVersion != 1 {
		t.Fatalf("unexpected access token config: %+v", got)
	}
}

func TestRuntimeDependenciesRejectMissingOrMemoryStorage(t *testing.T) {
	valid := config{}
	valid.MongoDB.URI = "mongodb://mongo:27017"
	valid.MongoDB.Database = "quwoquan_assistant"
	valid.Postgres.DSN = "postgres://assistant:secret@postgres:5432/quwoquan"
	valid.NotificationService.BaseURL = "http://notification-service:18087"
	valid.SearchService.BaseURL = "http://search-service:18095"
	valid.EntityService.BaseURL = "http://entity-service:18084"
	valid.ContentService.BaseURL = "http://content-service:18080"
	valid.Redis.General.Mode = "standalone"
	valid.Redis.General.Addr = "redis:6379"
	valid.Redis.Rec.Mode = "cluster"
	valid.Redis.Rec.Addrs = []string{"redis-a:6379", "redis-b:6379"}

	if err := validateRuntimeDependenciesConfig(valid); err != nil {
		t.Fatalf("valid dependency config rejected: %v", err)
	}

	tests := []struct {
		name      string
		mutate    func(*config)
		wantToken string
	}{
		{
			name:      "mongodb uri",
			mutate:    func(cfg *config) { cfg.MongoDB.URI = "" },
			wantToken: "mongodb.uri",
		},
		{
			name:      "mongodb database",
			mutate:    func(cfg *config) { cfg.MongoDB.Database = "" },
			wantToken: "mongodb.database",
		},
		{
			name:      "postgres dsn",
			mutate:    func(cfg *config) { cfg.Postgres.DSN = "" },
			wantToken: "postgres.dsn",
		},
		{
			name:      "notification service",
			mutate:    func(cfg *config) { cfg.NotificationService.BaseURL = "" },
			wantToken: "notification_service.base_url",
		},
		{
			name:      "general redis memory",
			mutate:    func(cfg *config) { cfg.Redis.General.Mode = "memory" },
			wantToken: "redis.general.mode",
		},
		{
			name:      "general redis address",
			mutate:    func(cfg *config) { cfg.Redis.General.Addr = "" },
			wantToken: "redis.general.addr",
		},
		{
			name:      "rec redis cluster addresses",
			mutate:    func(cfg *config) { cfg.Redis.Rec.Addrs = nil },
			wantToken: "redis.rec.addrs",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := valid
			cfg.Redis.Rec.Addrs = append([]string(nil), valid.Redis.Rec.Addrs...)
			tt.mutate(&cfg)
			err := validateRuntimeDependenciesConfig(cfg)
			if err == nil {
				t.Fatal("invalid dependency config should fail")
			}
			if !strings.Contains(err.Error(), tt.wantToken) {
				t.Fatalf("error=%q, want token %q", err, tt.wantToken)
			}
		})
	}
}

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

func TestGeneratedProviderBindingsFailClosedWithoutEnabledMaterial(t *testing.T) {
	configProvider := runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{}}
	newEgressClient := func(_ string, _ int) *http.Client {
		return &http.Client{Timeout: time.Second}
	}
	for _, appEnv := range []string{"alpha", "beta", "gamma", "prod"} {
		if _, err := buildModelProvider(
			appEnv,
			configProvider,
			newEgressClient,
		); err == nil {
			t.Fatalf("%s incomplete binding must fail closed", appEnv)
		}
	}
	if _, err := buildModelProvider(
		"unknown",
		configProvider,
		newEgressClient,
	); err == nil {
		t.Fatal("unknown environment binding must fail closed")
	}
}

func TestBuildSearchRegistryRequiresCanonicalSearchServiceAndNeverRegistersMock(t *testing.T) {
	if _, err := buildSearchRegistry(
		nil,
		"alpha",
		runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{}},
		func(_ string, _ int) *http.Client { return &http.Client{Timeout: time.Second} },
	); err == nil {
		t.Fatal("missing search-service URL must fail closed")
	}
	canonicalSearch, err := searchclient.New(
		"http://127.0.0.1:18095",
		&http.Client{Timeout: 100 * time.Millisecond},
	)
	if err != nil {
		t.Fatalf("build search client: %v", err)
	}
	registry, err := buildSearchRegistry(
		canonicalSearch,
		"alpha",
		runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{}},
		func(_ string, _ int) *http.Client { return &http.Client{Timeout: time.Second} },
	)
	if err != nil {
		t.Fatalf("build canonical app_search registry: %v", err)
	}
	if _, ok := registry.Metadata("app_search"); !ok {
		t.Fatal("canonical app_search must be registered")
	}
	if _, ok := registry.Metadata("mock_search"); ok {
		t.Fatal("mock_search must never be reachable")
	}
}

func TestRequireAssistantAPIMessageTransportUsesDescriptorAndFailsClosed(t *testing.T) {
	const capability = runtimemessaging.RuntimeMessageTransportCapability
	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {Mode: "memory"},
		},
		DefaultScene: "general",
	})
	t.Cleanup(func() { _ = router.Close() })

	transport, err := requireAssistantAPIMessageTransport(
		context.Background(),
		"alpha",
		router,
		map[string]string{"general": "memory"},
	)
	if err != nil {
		t.Fatalf("alpha fixture transport error = %v", err)
	}
	if transport == nil {
		t.Fatal("alpha fixture transport is nil")
	}

	bindings := assistantgenerated.ExternalProviderBindings["beta"]
	original, hadBinding := bindings[capability]
	t.Cleanup(func() {
		if hadBinding {
			bindings[capability] = original
			return
		}
		delete(bindings, capability)
	})
	enabledRedis := assistantgenerated.ExternalProviderBinding{
		State:               "enabled",
		AdapterID:           runtimemessaging.RedisMessageTransportAdapter,
		TimeoutMilliseconds: 100,
	}
	tests := []struct {
		name       string
		binding    assistantgenerated.ExternalProviderBinding
		found      bool
		router     *rtredis.Router
		sceneModes map[string]string
	}{
		{
			name:       "binding missing",
			found:      false,
			router:     router,
			sceneModes: map[string]string{"general": "standalone"},
		},
		{
			name: "unexpected adapter",
			binding: assistantgenerated.ExternalProviderBinding{
				State:               "enabled",
				AdapterID:           "infra.message.nats",
				TimeoutMilliseconds: 100,
			},
			found:      true,
			router:     router,
			sceneModes: map[string]string{"general": "standalone"},
		},
		{
			name:       "memory outside alpha fixture",
			binding:    enabledRedis,
			found:      true,
			router:     router,
			sceneModes: map[string]string{"general": "memory"},
		},
		{
			name:       "Redis preflight failure",
			binding:    enabledRedis,
			found:      true,
			router:     unavailableMessageTransportRouter(t),
			sceneModes: map[string]string{"general": "standalone"},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if test.found {
				bindings[capability] = test.binding
			} else {
				delete(bindings, capability)
			}
			if _, err := requireAssistantAPIMessageTransport(
				context.Background(),
				"beta",
				test.router,
				test.sceneModes,
			); err == nil {
				t.Fatal("message transport error = nil, want fail-closed")
			}
		})
	}
}

type unavailableMessageTransportClient struct {
	rtredis.Client
}

func (unavailableMessageTransportClient) Ping(context.Context) error {
	return errors.New("Redis unavailable")
}

func (unavailableMessageTransportClient) Close() error {
	return nil
}

func unavailableMessageTransportRouter(t *testing.T) *rtredis.Router {
	t.Helper()
	router, err := rtredis.NewRouterWithFactory(
		rtredis.RouterConfig{
			Scenes: map[string]rtredis.SceneConfig{
				"general": {Mode: "standalone"},
			},
			DefaultScene: "general",
		},
		func(rtredis.SceneConfig) (rtredis.Client, error) {
			return unavailableMessageTransportClient{}, nil
		},
	)
	if err != nil {
		t.Fatalf("NewRouterWithFactory() error = %v", err)
	}
	t.Cleanup(func() { _ = router.Close() })
	return router
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
