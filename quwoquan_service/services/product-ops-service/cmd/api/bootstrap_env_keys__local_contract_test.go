package main

import (
	"testing"

	"quwoquan_service/runtime/servicekit"
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
		"PRODUCT_OPS_ELASTICSEARCH_ENDPOINT",
		"PRODUCT_OPS_ELASTICSEARCH_API_KEY",
		"PRODUCT_OPS_ELASTICSEARCH_RAW_INDEX",
		"PRODUCT_OPS_ELASTICSEARCH_STARTUP_DIAGNOSTIC_INDEX",
		"PRODUCT_OPS_ELASTICSEARCH_RUNTIME_LOG_INDEX",
		"PRODUCT_OPS_ELASTICSEARCH_AGGREGATE_INDEX",
		"PRODUCT_OPS_ELASTICSEARCH_TIMEOUT_MS",
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
	cfg.Elasticsearch.Endpoint = "http://elasticsearch:9200"
	if err := rejectUnrenderedPlaceholders(cfg); err != nil {
		t.Fatalf("rendered endpoints must pass: %v", err)
	}
}

// TestValidateProductOpsConfigRequiresRealRedisScenes 锁定 fail-closed：
// rec/general 落到 memory 会让实验分流与事件批次账本变成单实例内存态。声明了
// standalone 却缺地址是注入缺陷，判否而不是静默降级。
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
