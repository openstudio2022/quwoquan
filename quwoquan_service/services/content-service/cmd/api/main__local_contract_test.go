package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
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

func TestApplyEnvOverrides_RetiredSingleSceneEnvIgnored(t *testing.T) {
	t.Setenv("CONTENT_REDIS_ADDR", "retired-host:6379")
	t.Setenv("CONTENT_REDIS_PASSWORD", "retired-password")
	t.Setenv("CONTENT_REDIS_DB", "9")
	cfg := config{}
	applyEnvOverrides(&cfg)
	if cfg.Redis.Rec.Addr != "" || cfg.Redis.Rec.Password != "" || cfg.Redis.Rec.DB != 0 {
		t.Fatalf("retired single-scene Redis env must not affect rec config: %+v", cfg.Redis.Rec)
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

// endpoint 与密钥只允许 infrastructure adapter 读取，cmd/api 的通用 config
// 覆盖不能把供应商 Binding 细节带入组合根。
func TestApplyEnvOverrides_DoesNotReadEmbeddingBinding(t *testing.T) {
	t.Setenv("CONTENT_EMBEDDING_ENDPOINT", "https://embed.example.test/v1")
	t.Setenv("CONTENT_EMBEDDING_API_KEY", "test-key")
	t.Setenv("CONTENT_EMBEDDING_MODEL", "text-embedding-3-large")
	t.Setenv("CONTENT_EMBEDDING_ENABLED", "true")
	t.Setenv("CONTENT_EMBEDDING_VECTOR_RECALL_ENABLED", "true")
	cfg := config{}
	applyEnvOverrides(&cfg)
	if cfg.Embedding.Enabled || cfg.Embedding.VectorRecallEnabled {
		t.Fatalf("cmd/api must not read embedding Binding environment: %+v", cfg.Embedding)
	}
}

func TestApplyEnvOverrides_EmbeddingFeatureFlagsStayInConfig(t *testing.T) {
	cfg := config{}
	cfg.Embedding.Enabled = true
	cfg.Embedding.VectorRecallEnabled = true
	applyEnvOverrides(&cfg)
	if !cfg.Embedding.Enabled || !cfg.Embedding.VectorRecallEnabled {
		t.Fatalf("embedding feature flags must remain config-owned: %+v", cfg.Embedding)
	}
}

// ---------------------------------------------------------------------------
// toSceneConfig
// ---------------------------------------------------------------------------

func TestToSceneConfig_StandaloneWithAddr(t *testing.T) {
	r := redisSceneCfg{Mode: "standalone", Addr: "redis:6379", Password: "pass"}
	sc := toSceneConfig(r)
	if sc.Mode != "standalone" {
		t.Errorf("Mode: want standalone, got %q", sc.Mode)
	}
	if sc.Addr != "redis:6379" || sc.Password != "pass" {
		t.Error("Addr/Password not propagated")
	}
}

func TestToSceneConfig_StandaloneNoAddrDoesNotFallbackToMemory(t *testing.T) {
	r := redisSceneCfg{Mode: "standalone"}
	sc := toSceneConfig(r)
	if sc.Mode != "standalone" {
		t.Errorf("production composition must preserve invalid standalone config for preflight, got %q", sc.Mode)
	}
}

func TestToSceneConfig_ClusterNoAddrsDoesNotFallbackToMemory(t *testing.T) {
	r := redisSceneCfg{Mode: "cluster"}
	sc := toSceneConfig(r)
	if sc.Mode != "cluster" {
		t.Errorf("production composition must preserve invalid cluster config for preflight, got %q", sc.Mode)
	}
}

func TestToSceneConfig_PoolSizePropagated(t *testing.T) {
	r := redisSceneCfg{Mode: "standalone", Addr: "redis:6379"}
	r.Pool.Size = 50
	r.Pool.MinIdle = 10
	sc := toSceneConfig(r)
	if sc.PoolSize != 50 || sc.MinIdleConns != 10 {
		t.Errorf("PoolSize=%d MinIdleConns=%d", sc.PoolSize, sc.MinIdleConns)
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
	if err := os.MkdirAll(filepath.Join("configs", "beta"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join("configs", "default", "config.yaml"), []byte("service:\n  http:\n    addr: \":18080\"\nredis:\n  rec:\n    mode: standalone\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join("configs", "beta", "config.yaml"), []byte("service:\n  http:\n    addr: \":19090\"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	cfg, err := loadRuntimeConfig("content-service", "beta", "", "")
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
	must(os.MkdirAll(filepath.Join(root, "configs", "content-service", "beta"), 0o755))
	must(os.MkdirAll(filepath.Join(root, "releases", "config", "content-service"), 0o755))

	must(os.WriteFile(
		filepath.Join(root, "configs", "content-service", "default", "config.yaml"),
		[]byte("service:\n  http:\n    addr: \":18080\"\nconfig:\n  version: \"v0.0.1\"\n"),
		0o644,
	))
	must(os.WriteFile(
		filepath.Join(root, "configs", "content-service", "beta", "config.yaml"),
		[]byte("service:\n  http:\n    addr: \":19090\"\n"),
		0o644,
	))
	must(os.WriteFile(
		filepath.Join(root, "releases", "config", "content-service", "v2026.02.28.0.yaml"),
		[]byte("config:\n  version: \"v2026.02.28.0\"\n"),
		0o644,
	))

	cfg, err := loadRuntimeConfig("content-service", "beta", root, "v2026.02.28.0")
	if err != nil {
		t.Fatalf("loadRuntimeConfig external root failed: %v", err)
	}
	if cfg.Service.HTTP.Addr != ":19090" {
		t.Fatalf("expected beta override addr :19090, got %q", cfg.Service.HTTP.Addr)
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
	err := preflightConfig(cfg, "beta")
	if err == nil || !strings.Contains(err.Error(), "requires redis.rec.addrs") {
		t.Fatalf("expected cluster addrs error, got %v", err)
	}
}

func TestPreflightConfig_RejectsMemoryScene(t *testing.T) {
	cfg := validCommercialConfig()
	cfg.Redis.General.Mode = "memory"
	if err := preflightConfig(cfg, "gamma"); err == nil || !strings.Contains(err.Error(), "memory is forbidden") {
		t.Fatalf("expected memory scene rejection, got %v", err)
	}
}

func TestPreflightConfig_RequiresCommercialDataDependencies(t *testing.T) {
	cfg := validCommercialConfig()
	cfg.Mongo.URI = ""
	if err := preflightConfig(cfg, "gamma"); err == nil || !strings.Contains(err.Error(), "requires mongo.uri") {
		t.Fatalf("expected Mongo requirement, got %v", err)
	}

	cfg = validCommercialConfig()
	cfg.Postgres.ReportDSN = ""
	if err := preflightConfig(cfg, "gamma"); err == nil || !strings.Contains(err.Error(), "requires postgres.report_dsn") {
		t.Fatalf("expected PostgreSQL requirement, got %v", err)
	}

	cfg = validCommercialConfig()
	cfg.OSS.AccessKeySecret = ""
	if err := preflightConfig(cfg, "gamma"); err == nil || !strings.Contains(err.Error(), "CONTENT_OSS_ACCESS_KEY_SECRET") {
		t.Fatalf("expected OSS credential requirement, got %v", err)
	}
}

func TestPreflightConfig_RequiresEnabledSearchEndpoint(t *testing.T) {
	t.Setenv(
		accountClosureSubjectHMACEnv,
		"content-account-closure-test-secret-32",
	)
	cfg := validCommercialConfig()
	cfg.ES.Enabled = true
	if err := preflightConfig(cfg, "gamma"); err == nil || !strings.Contains(err.Error(), "SEARCH_ES_ENDPOINTS") {
		t.Fatalf("expected ES endpoint requirement, got %v", err)
	}
}

func TestPreflightConfig_RequiresAccountClosureSubjectHMAC(t *testing.T) {
	t.Setenv(accountClosureSubjectHMACEnv, "")
	cfg := validCommercialConfig()
	if err := preflightConfig(cfg, "gamma"); err == nil ||
		!strings.Contains(err.Error(), accountClosureSubjectHMACEnv) {
		t.Fatalf("expected account-closure HMAC requirement, got %v", err)
	}
}

func TestPreflightConfig_AcceptsCompleteCommercialComposition(t *testing.T) {
	t.Setenv(
		accountClosureSubjectHMACEnv,
		"content-account-closure-test-secret-32",
	)
	t.Setenv("CONTENT_EMBEDDING_ENDPOINT", "https://embedding.example.test/v1/embeddings")
	t.Setenv("CONTENT_EMBEDDING_API_KEY", "embedding-test-key")
	cfg := validCommercialConfig()
	cfg.Embedding.Enabled = true
	if err := preflightConfig(cfg, "gamma"); err != nil {
		t.Fatalf("expected complete commercial composition, got %v", err)
	}
}

func TestPreflightConfig_AllowsDisabledEmbeddingPipelineWithoutBinding(
	t *testing.T,
) {
	t.Setenv(
		accountClosureSubjectHMACEnv,
		"content-account-closure-test-secret-32",
	)
	t.Setenv("CONTENT_EMBEDDING_ENDPOINT", "")
	t.Setenv("CONTENT_EMBEDDING_API_KEY", "")
	cfg := validCommercialConfig()
	cfg.Embedding.Enabled = false

	if err := preflightConfig(cfg, "beta"); err != nil {
		t.Fatalf(
			"embedding-disabled content release configuration must not require binding: %v",
			err,
		)
	}
}

func TestPreflightConfig_FailsClosedWithoutEmbeddingBindingOutsideAlpha(t *testing.T) {
	t.Setenv(
		accountClosureSubjectHMACEnv,
		"content-account-closure-test-secret-32",
	)
	t.Setenv("CONTENT_EMBEDDING_ENDPOINT", "")
	t.Setenv("CONTENT_EMBEDDING_API_KEY", "embedding-secret-must-not-leak")

	cfg := validCommercialConfig()
	cfg.Embedding.Enabled = true
	err := preflightConfig(cfg, "gamma")
	if err == nil {
		t.Fatal("commercial runtime accepted a missing embedding endpoint")
	}
	if !strings.Contains(err.Error(), "embedding binding material") {
		t.Fatalf("expected embedding binding failure, got %v", err)
	}
	if strings.Contains(err.Error(), "embedding-secret-must-not-leak") {
		t.Fatalf("embedding preflight leaked secret: %v", err)
	}
}

func TestResolveAccountClosureSubjectDigestorFailsClosedOutsideAlpha(
	t *testing.T,
) {
	t.Setenv(accountClosureSubjectHMACEnv, "")
	if _, err := resolveAccountClosureSubjectDigestor(
		"gamma",
		"content-service",
	); err == nil {
		t.Fatal("commercial runtime accepted missing account-closure HMAC")
	}

	digestor, err := resolveAccountClosureSubjectDigestor(
		"alpha",
		"content-service",
	)
	if err != nil {
		t.Fatalf("alpha synthetic digestor: %v", err)
	}
	if _, err := digestor.DigestSubject("alpha-persona"); err != nil {
		t.Fatalf("alpha synthetic subject digest: %v", err)
	}
}

func TestContentOSSEndpointHonorsExplicitTransport(t *testing.T) {
	if got := contentOSSEndpoint("minio:9000", false); got != "http://minio:9000" {
		t.Fatalf("expected local MinIO HTTP endpoint, got %q", got)
	}
	if got := contentOSSEndpoint("minio:9000", true); got != "https://minio:9000" {
		t.Fatalf("expected TLS object-storage endpoint, got %q", got)
	}
	if got := contentOSSEndpoint("https://oss.example.test/", false); got != "https://oss.example.test" {
		t.Fatalf("explicit endpoint scheme must be authoritative, got %q", got)
	}
}

func validCommercialConfig() config {
	cfg := config{}
	for _, scene := range []*redisSceneCfg{&cfg.Redis.Rec, &cfg.Redis.General, &cfg.Redis.Realtime} {
		scene.Mode = "standalone"
		scene.Addr = "redis:6379"
	}
	cfg.Mongo.URI = "mongodb://mongodb:27017"
	cfg.Postgres.ReportDSN = "postgres://content:content@postgres:5432/content?sslmode=disable"
	cfg.IPLocation.Provider = "ip2region"
	cfg.IPLocation.IPv4DatabasePath = "/geo/ip2region_v4.xdb"
	cfg.IPLocation.IPv6DatabasePath = "/geo/ip2region_v6.xdb"
	cfg.IPLocation.DataVersion = time.Now().UTC().Format("2006-01-02")
	cfg.CommentRateLimit.BurstWindowSeconds = 30
	cfg.CommentRateLimit.BurstMax = 5
	cfg.CommentRateLimit.DailyWindowSeconds = 24 * 60 * 60
	cfg.CommentRateLimit.DailyMax = 200
	cfg.OSS.Endpoint = "minio:9000"
	cfg.OSS.Bucket = "quwoquan-media"
	cfg.OSS.Region = "us-east-1"
	cfg.OSS.AccessKeyID = "content-test-key"
	cfg.OSS.AccessKeySecret = "content-test-secret"
	return cfg
}
