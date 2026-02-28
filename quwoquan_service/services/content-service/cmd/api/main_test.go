package main

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
)

// ---------------------------------------------------------------------------
// applyRedisSceneEnv
// ---------------------------------------------------------------------------

func TestApplyRedisSceneEnv_Mode(t *testing.T) {
	t.Setenv("TEST_REDIS_MODE", "cluster")
	cfg := redisSceneCfg{}
	applyRedisSceneEnv("TEST_REDIS", &cfg)
	if cfg.Mode != "cluster" {
		t.Errorf("Mode: want %q, got %q", "cluster", cfg.Mode)
	}
}

func TestApplyRedisSceneEnv_Addr(t *testing.T) {
	t.Setenv("TEST_REDIS_ADDR", "redis-host:6379")
	cfg := redisSceneCfg{}
	applyRedisSceneEnv("TEST_REDIS", &cfg)
	if cfg.Addr != "redis-host:6379" {
		t.Errorf("Addr: want %q, got %q", "redis-host:6379", cfg.Addr)
	}
}

func TestApplyRedisSceneEnv_Addrs_CommaSplit(t *testing.T) {
	t.Setenv("TEST_REDIS_ADDRS", "n1:6379,n2:6379,n3:6379")
	cfg := redisSceneCfg{}
	applyRedisSceneEnv("TEST_REDIS", &cfg)
	if len(cfg.Addrs) != 3 {
		t.Fatalf("Addrs: want 3 nodes, got %d", len(cfg.Addrs))
	}
	if cfg.Addrs[0] != "n1:6379" || cfg.Addrs[2] != "n3:6379" {
		t.Errorf("Addrs content incorrect: %v", cfg.Addrs)
	}
}

func TestApplyRedisSceneEnv_Password(t *testing.T) {
	t.Setenv("TEST_REDIS_PASSWORD", "s3cr3t")
	cfg := redisSceneCfg{}
	applyRedisSceneEnv("TEST_REDIS", &cfg)
	if cfg.Password != "s3cr3t" {
		t.Errorf("Password: want %q, got %q", "s3cr3t", cfg.Password)
	}
}

func TestApplyRedisSceneEnv_TLS(t *testing.T) {
	for _, val := range []string{"true", "1"} {
		t.Run("TLS="+val, func(t *testing.T) {
			t.Setenv("TEST_REDIS_TLS", val)
			cfg := redisSceneCfg{}
			applyRedisSceneEnv("TEST_REDIS", &cfg)
			if !cfg.TLS {
				t.Errorf("TLS env=%q should set cfg.TLS=true", val)
			}
		})
	}
}

func TestApplyRedisSceneEnv_NoEnvSet_NoChange(t *testing.T) {
	// Ensure none of the TEST_REDIS_* vars are set
	for _, k := range []string{"TEST_REDIS_MODE", "TEST_REDIS_ADDR", "TEST_REDIS_ADDRS",
		"TEST_REDIS_PASSWORD", "TEST_REDIS_TLS"} {
		t.Setenv(k, "") // t.Setenv restores original value; set to empty = no-op
	}
	cfg := redisSceneCfg{Mode: "standalone", Addr: "original:6379"}
	applyRedisSceneEnv("TEST_REDIS", &cfg)
	if cfg.Mode != "standalone" || cfg.Addr != "original:6379" {
		t.Error("applyRedisSceneEnv should not overwrite with empty env values")
	}
}

// ---------------------------------------------------------------------------
// applyEnvOverrides — backward compat (CONTENT_REDIS_ADDR → rec.addr)
// ---------------------------------------------------------------------------

func TestApplyEnvOverrides_LegacyAddr(t *testing.T) {
	t.Setenv("CONTENT_REDIS_ADDR", "legacy-host:6379")
	cfg := config{}
	applyEnvOverrides(&cfg)
	if cfg.Redis.Rec.Addr != "legacy-host:6379" {
		t.Errorf("legacy CONTENT_REDIS_ADDR should map to Redis.Rec.Addr, got %q", cfg.Redis.Rec.Addr)
	}
}

func TestApplyEnvOverrides_LegacyAddrNotOverrideExisting(t *testing.T) {
	t.Setenv("CONTENT_REDIS_ADDR", "legacy-host:6379")
	cfg := config{}
	cfg.Redis.Rec.Addr = "already-set:6379"
	applyEnvOverrides(&cfg)
	// Legacy env must NOT overwrite a value already set from new env/config
	if cfg.Redis.Rec.Addr != "already-set:6379" {
		t.Errorf("legacy addr should not overwrite existing cfg.Redis.Rec.Addr")
	}
}

func TestApplyEnvOverrides_LegacyPassword(t *testing.T) {
	t.Setenv("CONTENT_REDIS_PASSWORD", "legacy-pass")
	cfg := config{}
	applyEnvOverrides(&cfg)
	if cfg.Redis.Rec.Password != "legacy-pass" {
		t.Errorf("legacy CONTENT_REDIS_PASSWORD should map to Redis.Rec.Password")
	}
}

func TestApplyEnvOverrides_NewRecOverrides(t *testing.T) {
	t.Setenv("CONTENT_REDIS_REC_MODE", "cluster")
	t.Setenv("CONTENT_REDIS_REC_ADDRS", "c1:6379,c2:6379")
	t.Setenv("CONTENT_REDIS_REC_TLS", "true")
	cfg := config{}
	applyEnvOverrides(&cfg)
	if cfg.Redis.Rec.Mode != "cluster" {
		t.Errorf("Rec.Mode: want cluster, got %q", cfg.Redis.Rec.Mode)
	}
	if len(cfg.Redis.Rec.Addrs) != 2 {
		t.Errorf("Rec.Addrs: want 2, got %d", len(cfg.Redis.Rec.Addrs))
	}
	if !cfg.Redis.Rec.TLS {
		t.Error("Rec.TLS should be true")
	}
}

func TestApplyEnvOverrides_RecModelService(t *testing.T) {
	t.Setenv("REC_MODEL_SERVICE_URL", "http://rec:8000")
	t.Setenv("REC_MODEL_SERVICE_ENABLED", "true")
	t.Setenv("REC_MODEL_SERVICE_TIMEOUT_MS", "75")
	cfg := config{}
	applyEnvOverrides(&cfg)
	if cfg.RecModelService.URL != "http://rec:8000" {
		t.Errorf("URL: want http://rec:8000, got %q", cfg.RecModelService.URL)
	}
	if !cfg.RecModelService.Enabled {
		t.Error("Enabled should be true")
	}
	if cfg.RecModelService.TimeoutMs != 75 {
		t.Errorf("TimeoutMs: want 75, got %d", cfg.RecModelService.TimeoutMs)
	}
}

// ---------------------------------------------------------------------------
// resolvePoolConfig
// ---------------------------------------------------------------------------

func TestResolvePoolConfig_StandaloneDefaults(t *testing.T) {
	cfg := redisSceneCfg{Mode: "standalone"} // all pool fields zero
	pool := resolvePoolConfig(cfg)
	base := recinfra.DefaultRedisPoolConfig()
	cpus := runtime.GOMAXPROCS(0)

	if pool.PoolSize != cpus*20 {
		t.Errorf("standalone PoolSize: want %d, got %d", cpus*20, pool.PoolSize)
	}
	if pool.ReadTimeout != base.ReadTimeout {
		t.Errorf("standalone ReadTimeout: want %v, got %v", base.ReadTimeout, pool.ReadTimeout)
	}
}

func TestResolvePoolConfig_ClusterDefaults(t *testing.T) {
	cfg := redisSceneCfg{Mode: "cluster"} // all pool fields zero
	pool := resolvePoolConfig(cfg)
	cpus := runtime.GOMAXPROCS(0)

	if pool.PoolSize != cpus*30 {
		t.Errorf("cluster PoolSize: want %d, got %d", cpus*30, pool.PoolSize)
	}
}

func TestResolvePoolConfig_ExplicitOverridesDefault(t *testing.T) {
	cfg := redisSceneCfg{
		Mode: "standalone",
	}
	cfg.Pool.Size = 50
	cfg.Pool.MinIdle = 10
	cfg.Pool.ReadTimeoutMs = 200
	cfg.Pool.WriteTimeoutMs = 250
	cfg.Pool.DialTimeoutMs = 1000

	pool := resolvePoolConfig(cfg)

	if pool.PoolSize != 50 {
		t.Errorf("explicit PoolSize: want 50, got %d", pool.PoolSize)
	}
	if pool.MinIdleConns != 10 {
		t.Errorf("explicit MinIdleConns: want 10, got %d", pool.MinIdleConns)
	}
	if pool.ReadTimeout != 200*time.Millisecond {
		t.Errorf("explicit ReadTimeout: want 200ms, got %v", pool.ReadTimeout)
	}
	if pool.WriteTimeout != 250*time.Millisecond {
		t.Errorf("explicit WriteTimeout: want 250ms, got %v", pool.WriteTimeout)
	}
	if pool.DialTimeout != 1000*time.Millisecond {
		t.Errorf("explicit DialTimeout: want 1000ms, got %v", pool.DialTimeout)
	}
}

func TestResolvePoolConfig_ZeroFieldsKeptAsDefault(t *testing.T) {
	// Only Size is set; timeouts should keep their CPU-based defaults.
	cfg := redisSceneCfg{Mode: "cluster"}
	cfg.Pool.Size = 100
	pool := resolvePoolConfig(cfg)

	if pool.PoolSize != 100 {
		t.Errorf("PoolSize: want 100, got %d", pool.PoolSize)
	}
	// ReadTimeout should still be the cluster default (100ms), not 0.
	if pool.ReadTimeout == 0 {
		t.Error("ReadTimeout must not be zero when pool.read_timeout_ms is unset")
	}
}

func TestResolveRuntimeIdentity_InvalidEnv(t *testing.T) {
	t.Setenv("APP_ENV", "bad-env")
	_, _, _, _, _, err := resolveRuntimeIdentity()
	if err == nil {
		t.Fatal("expected invalid APP_ENV error")
	}
}

func TestResolveRuntimeIdentity_ProdRequiresConfigVersion(t *testing.T) {
	t.Setenv("APP_ENV", "prod")
	t.Setenv("CONFIG_VERSION", "")
	_, _, _, _, _, err := resolveRuntimeIdentity()
	if err == nil {
		t.Fatal("expected prod CONFIG_VERSION required error")
	}
}

func TestLoadRuntimeConfig_LocalLayered(t *testing.T) {
	tmp := t.TempDir()
	old, _ := os.Getwd()
	if err := os.Chdir(tmp); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chdir(old) })

	if err := os.MkdirAll(filepath.Join("configs", "default"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join("configs", "integration"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join("configs", "default", "config.yaml"), []byte("service:\n  http:\n    addr: \":18080\"\nredis:\n  rec:\n    mode: standalone\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join("configs", "integration", "config.yaml"), []byte("service:\n  http:\n    addr: \":19090\"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	cfg, err := loadRuntimeConfig("content-service", "integration", "", "")
	if err != nil {
		t.Fatalf("loadRuntimeConfig failed: %v", err)
	}
	if cfg.Service.HTTP.Addr != ":19090" {
		t.Fatalf("expected env override addr :19090, got %q", cfg.Service.HTTP.Addr)
	}
}

func TestLoadRuntimeConfig_ExternalRootLayered(t *testing.T) {
	root := t.TempDir()

	must := func(err error) {
		if err != nil {
			t.Fatal(err)
		}
	}
	must(os.MkdirAll(filepath.Join(root, "configs", "content-service", "default"), 0o755))
	must(os.MkdirAll(filepath.Join(root, "configs", "content-service", "integration"), 0o755))
	must(os.MkdirAll(filepath.Join(root, "releases", "config", "content-service"), 0o755))

	must(os.WriteFile(
		filepath.Join(root, "configs", "content-service", "default", "config.yaml"),
		[]byte("service:\n  http:\n    addr: \":18080\"\nconfig:\n  version: \"v0.0.1\"\n"),
		0o644,
	))
	must(os.WriteFile(
		filepath.Join(root, "configs", "content-service", "integration", "config.yaml"),
		[]byte("service:\n  http:\n    addr: \":19090\"\n"),
		0o644,
	))
	must(os.WriteFile(
		filepath.Join(root, "releases", "config", "content-service", "v2026.02.28.0.yaml"),
		[]byte("config:\n  version: \"v2026.02.28.0\"\n"),
		0o644,
	))

	cfg, err := loadRuntimeConfig("content-service", "integration", root, "v2026.02.28.0")
	if err != nil {
		t.Fatalf("loadRuntimeConfig external root failed: %v", err)
	}
	if cfg.Service.HTTP.Addr != ":19090" {
		t.Fatalf("expected integration override addr :19090, got %q", cfg.Service.HTTP.Addr)
	}
	if cfg.Config.Version != "v2026.02.28.0" {
		t.Fatalf("expected version overlay v2026.02.28.0, got %q", cfg.Config.Version)
	}
}

func TestValidateRuntimeCompatibility(t *testing.T) {
	cfg := config{}
	cfg.Config.MinImageVersion = "1.2.0"
	cfg.Config.MaxImageVersion = "1.9.0"
	if err := validateRuntimeCompatibility(cfg, "", "1.1.9"); err == nil {
		t.Fatal("expected min version error")
	}
	if err := validateRuntimeCompatibility(cfg, "", "2.0.0"); err == nil {
		t.Fatal("expected max version error")
	}
	if err := validateRuntimeCompatibility(cfg, "", "1.5.0"); err != nil {
		t.Fatalf("expected compatible version, got err: %v", err)
	}
}

func TestPreflightConfig_ClusterRequiresAddrs(t *testing.T) {
	cfg := config{}
	cfg.Redis.Rec.Mode = "cluster"
	err := preflightConfig(cfg, "integration")
	if err == nil || !strings.Contains(err.Error(), "requires redis.rec.addrs") {
		t.Fatalf("expected cluster addrs error, got %v", err)
	}
}
