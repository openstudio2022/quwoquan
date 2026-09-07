package main

import (
	"context"
	"errors"
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	rthealth "quwoquan_service/runtime/health"
	"quwoquan_service/runtime/servicekit"
	eventrecordgenerated "quwoquan_service/services/product-ops-service/generated/product_ops/event_record"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/logsink"
)

// TestDeclaredEnvKeysCoverHandwrittenOverrides 锁定声明式配置派生的 env 覆盖
// 键集覆盖迁移前手写 applyEnvOverrides 的全部键。app_release 段由 Android/iOS
// 正式发布流水线注入且被 ops 侧 local_contract 断言，键名必须逐字保留。
func TestDeclaredEnvKeysCoverHandwrittenOverrides(t *testing.T) {
	keys, err := DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("declared env keys: %v", err)
	}
	declared := map[string]bool{}
	for _, key := range keys {
		declared[key] = true
	}
	for _, required := range []string{
		"PRODUCT_OPS_SERVICE_ADDR",
		"PRODUCT_OPS_APP_RELEASE_PUBLIC_ORIGIN",
		"PRODUCT_OPS_IOS_LATEST_VERSION",
		"PRODUCT_OPS_IOS_LATEST_BUILD",
		"PRODUCT_OPS_IOS_MINIMUM_SUPPORTED_VERSION",
		"PRODUCT_OPS_IOS_MINIMUM_SUPPORTED_BUILD",
		"PRODUCT_OPS_IOS_UPDATE_URL",
		"PRODUCT_OPS_IOS_RECOVERY_URL",
		"PRODUCT_OPS_ANDROID_LATEST_VERSION",
		"PRODUCT_OPS_ANDROID_LATEST_BUILD",
		"PRODUCT_OPS_ANDROID_MINIMUM_SUPPORTED_VERSION",
		"PRODUCT_OPS_ANDROID_MINIMUM_SUPPORTED_BUILD",
		"PRODUCT_OPS_ANDROID_UPDATE_URL",
		"PRODUCT_OPS_ANDROID_RECOVERY_URL",
		"PRODUCT_OPS_ANDROID_APK_URL",
		"PRODUCT_OPS_ANDROID_APK_HOST_ALLOWLIST",
		"PRODUCT_OPS_ANDROID_APK_PACKAGE_NAME",
		"PRODUCT_OPS_ANDROID_APK_SHA256",
		"PRODUCT_OPS_ANDROID_APK_SIZE_BYTES",
		"PRODUCT_OPS_ANDROID_APK_SIGNING_CERTIFICATE_SHA256",
		"PRODUCT_OPS_ANDROID_MIN_ANDROID_VERSION",
		"PRODUCT_OPS_WEB_LATEST_VERSION",
		"PRODUCT_OPS_WEB_LATEST_BUILD",
		"PRODUCT_OPS_WEB_MINIMUM_SUPPORTED_VERSION",
		"PRODUCT_OPS_WEB_MINIMUM_SUPPORTED_BUILD",
		"PRODUCT_OPS_WEB_UPDATE_URL",
		"PRODUCT_OPS_WEB_RECOVERY_URL",
		"PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_ENDPOINT",
		"PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_API_KEY",
		"PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_RAW_INDEX",
		"PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_STARTUP_DIAGNOSTIC_INDEX",
		"PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_AGGREGATE_INDEX",
		"PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_TIMEOUT_MS",
		"PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_ENDPOINT",
		"PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_API_KEY",
		"PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_RAW_INDEX",
		"PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_AGGREGATE_INDEX",
		"PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_TIMEOUT_MS",
		"PRODUCT_OPS_TELEMETRY_ALERTS_POLICY_PATH",
		"PRODUCT_OPS_TELEMETRY_ALERTS_ALERTMANAGER_URL",
		"PRODUCT_OPS_TELEMETRY_ALERTS_INTERVAL_MS",
		"PRODUCT_OPS_REDIS_REC_ADDR",
		"PRODUCT_OPS_REDIS_REC_PASSWORD",
		"PRODUCT_OPS_REDIS_GENERAL_ADDR",
		"PRODUCT_OPS_REDIS_GENERAL_PASSWORD",
		"PRODUCT_OPS_MONGO_URI",
		"PRODUCT_OPS_MONGO_DATABASE",
		"PRODUCT_OPS_POSTGRES_DSN",
	} {
		if !declared[required] {
			t.Fatalf("declared env keys missing %s", required)
		}
	}
	// 无前缀键要么属于别的服务（REDIS_*_ADDR 是 assistant 的注入键），要么
	// 与本服务的标准键重复；它们必须彻底退役而不是并存双读。
	for _, retired := range retiredEnvKeys() {
		if declared[retired] {
			t.Fatalf("retired env key %s is still declared", retired)
		}
	}
}

// TestValidateProductOpsConfigRejectsUnrenderedPlaceholders 锁定未渲染
// ${VAR} 占位符被当成缺口拒收，而不是拿去当端点连接。
func TestValidateProductOpsConfigRejectsUnrenderedPlaceholders(t *testing.T) {
	cfg := &config{}
	cfg.Environment = "gamma"
	cfg.MongoDB.URI = "${QWQ_MONGO_URI}"
	if err := rejectUnrenderedPlaceholders(cfg); err == nil {
		t.Fatal("expected unrendered mongodb.uri rejection")
	}
	cfg.MongoDB.URI = "mongodb://mongodb:27017"
	cfg.Postgres.DSN = "${QWQ_POSTGRES_DSN}"
	if err := rejectUnrenderedPlaceholders(cfg); err == nil {
		t.Fatal("expected unrendered postgres.dsn rejection")
	}
	cfg.Postgres.DSN = "postgres://user:pass@postgres:5432/db"
	cfg.TelemetryElasticsearch.Endpoint = "http://telemetry-elasticsearch:9200"
	cfg.RuntimeLogElasticsearch.Endpoint = "http://runtime-log-elasticsearch:9200"
	if err := rejectUnrenderedPlaceholders(cfg); err != nil {
		t.Fatalf("rendered endpoints must pass: %v", err)
	}
}

// TestValidateProductOpsConfigRequiresRealRedisScenes 锁定 fail-closed：
// rec/general 落到 memory 会让实验分流与事件批次账本变成单实例内存态。声明了
// standalone 却缺地址是注入缺陷，判否而不是静默降级。
type elasticsearchReadinessFunc func(context.Context) error

func (f elasticsearchReadinessFunc) Ping(ctx context.Context) error {
	return f(ctx)
}

func TestElasticsearchReadinessChecksAreIndependent(t *testing.T) {
	assembly := &servicekit.Assembly{Health: rthealth.NewChecker()}
	registerElasticsearchReadiness(
		assembly,
		elasticsearchReadinessFunc(func(context.Context) error { return nil }),
		elasticsearchReadinessFunc(func(context.Context) error {
			return errors.New("runtime unavailable")
		}),
	)
	result := assembly.Health.Check(context.Background())
	if result.Checks["telemetry-elasticsearch"] != "ok" {
		t.Fatalf("telemetry readiness = %q", result.Checks["telemetry-elasticsearch"])
	}
	if result.Checks["runtime-log-elasticsearch"] != "runtime unavailable" {
		t.Fatalf("runtime readiness = %q", result.Checks["runtime-log-elasticsearch"])
	}
	if len(result.FailedChecks) != 1 || result.FailedChecks[0] != "runtime-log-elasticsearch" {
		t.Fatalf("failed readiness checks = %v", result.FailedChecks)
	}
}

func TestResolveElasticsearchBindingsKeepsCredentialsIndependent(t *testing.T) {
	cfg := &config{}
	cfg.Environment = "prod"
	provider := runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{
		"PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_ENDPOINT":   "https://telemetry.example.test",
		"PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_API_KEY":    "telemetry-key",
		"PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_ENDPOINT": "https://runtime.example.test",
		"PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_API_KEY":  "runtime-key",
	}}
	telemetry, ok := eventrecordgenerated.ExternalProviderBindingFor("prod", productTelemetrySinkCapability)
	if !ok {
		t.Fatal("prod telemetry binding is missing")
	}
	runtimeLog, ok := eventrecordgenerated.ExternalProviderBindingFor("prod", runtimeLogSinkCapability)
	if !ok {
		t.Fatal("prod runtime-log binding is missing")
	}
	if err := resolveElasticsearchBinding(
		productTelemetrySinkCapability, telemetry, provider,
		&cfg.TelemetryElasticsearch.Endpoint, &cfg.TelemetryElasticsearch.APIKey,
		&cfg.TelemetryElasticsearch.TimeoutMS, &cfg.TelemetrySinkAdapterID,
	); err != nil {
		t.Fatal(err)
	}
	if err := resolveElasticsearchBinding(
		runtimeLogSinkCapability, runtimeLog, provider,
		&cfg.RuntimeLogElasticsearch.Endpoint, &cfg.RuntimeLogElasticsearch.APIKey,
		&cfg.RuntimeLogElasticsearch.TimeoutMS, &cfg.RuntimeLogSinkAdapterID,
	); err != nil {
		t.Fatal(err)
	}
	if cfg.TelemetryElasticsearch.APIKey != "telemetry-key" ||
		cfg.RuntimeLogElasticsearch.APIKey != "runtime-key" {
		t.Fatalf("credentials crossed logical stores: telemetry=%q runtime=%q",
			cfg.TelemetryElasticsearch.APIKey, cfg.RuntimeLogElasticsearch.APIKey)
	}
}

func TestEventRepositoryConfigFailsClosedPerLogicalStore(t *testing.T) {
	cfg := &config{}
	cfg.TelemetrySinkAdapterID = logsink.ElasticsearchAdapterID
	cfg.RuntimeLogSinkAdapterID = logsink.ElasticsearchAdapterID
	cfg.TelemetryElasticsearch.Endpoint = "http://telemetry:9200"
	cfg.TelemetryElasticsearch.RawIndex = "app-product-telemetry-raw"
	cfg.TelemetryElasticsearch.StartupDiagnosticIndex = "app-startup-diagnostic-raw"
	cfg.TelemetryElasticsearch.AggregateIndex = "app-product-telemetry-hourly"
	cfg.TelemetryElasticsearch.TimeoutMS = 5000
	cfg.RuntimeLogElasticsearch.Endpoint = "http://runtime:9200"
	cfg.RuntimeLogElasticsearch.RawIndex = "runtime-diagnostics-raw"
	cfg.RuntimeLogElasticsearch.AggregateIndex = "runtime-diagnostics-hourly"
	cfg.RuntimeLogElasticsearch.TimeoutMS = 5000
	if err := validateEventRepositoryBounds(cfg); err != nil {
		t.Fatalf("valid split config rejected: %v", err)
	}
	cfg.RuntimeLogElasticsearch.AggregateIndex = cfg.TelemetryElasticsearch.AggregateIndex
	if err := validateEventRepositoryBounds(cfg); err == nil {
		t.Fatal("overlapping aggregate index must be rejected")
	}
	cfg.RuntimeLogElasticsearch.AggregateIndex = "runtime-diagnostics-hourly"
	cfg.RuntimeLogElasticsearch.Endpoint = ""
	if err := validateEventRepositoryBounds(cfg); err == nil ||
		!strings.Contains(err.Error(), "runtime_log_elasticsearch.endpoint") {
		t.Fatalf("missing runtime endpoint must fail closed: %v", err)
	}
}

func TestValidateProductOpsConfigRequiresRealRedisScenes(t *testing.T) {
	cfg := &config{}
	cfg.Redis.Rec.Mode = servicekit.RedisModeStandalone
	cfg.Redis.Rec.Addr = "redis:6379"
	if _, err := resolveRedisScenes(cfg)["general"].DeclaredMode(); err == nil {
		t.Fatal("general scene without a mode declaration must be rejected")
	}
	mode, err := resolveRedisScenes(cfg)["rec"].DeclaredMode()
	if err != nil {
		t.Fatalf("declared rec scene must resolve: %v", err)
	}
	if mode != servicekit.RedisModeStandalone {
		t.Fatalf("declared rec scene must resolve standalone, got %s", mode)
	}
	// realtime 复用 general 的物理实例，不独立分库。
	cfg.Redis.General.Mode = servicekit.RedisModeStandalone
	cfg.Redis.General.Addr = "redis-general:6379"
	scenes := resolveRedisScenes(cfg)
	if scenes["realtime"].Addr != scenes["general"].Addr {
		t.Fatalf(
			"realtime scene must reuse the general declaration: realtime=%s general=%s",
			scenes["realtime"].Addr, scenes["general"].Addr,
		)
	}
}
