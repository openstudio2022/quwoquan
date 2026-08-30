package main

import (
	"fmt"
	"strings"

	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/servicekit"
	eventrecordgenerated "quwoquan_service/services/product-ops-service/generated/product_ops/event_record"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/logsink"
)

// config 是 product-ops-service 的声明式配置：通用段内嵌 servicekit.BaseConfig，
// Mongo/Postgres/Redis 场景按「声明即装配」交给骨架（DEC-028）。
//
// app_release 段的 env 键由 Android/iOS 正式发布流水线注入且被 ops 侧
// local_contract 断言，因此用 envAbsolute 精确保留既有键名，不走前缀派生。
type config struct {
	servicekit.BaseConfig `yaml:",inline"`

	AppRelease struct {
		PublicOrigin string `yaml:"public_origin" envAbsolute:"PRODUCT_OPS_APP_RELEASE_PUBLIC_ORIGIN"`
		IOS          struct {
			LatestVersion           string `yaml:"latest_version" envAbsolute:"PRODUCT_OPS_IOS_LATEST_VERSION"`
			LatestBuild             string `yaml:"latest_build" envAbsolute:"PRODUCT_OPS_IOS_LATEST_BUILD"`
			MinimumSupportedVersion string `yaml:"minimum_supported_version" envAbsolute:"PRODUCT_OPS_IOS_MINIMUM_SUPPORTED_VERSION"`
			MinimumSupportedBuild   string `yaml:"minimum_supported_build" envAbsolute:"PRODUCT_OPS_IOS_MINIMUM_SUPPORTED_BUILD"`
			UpdateURL               string `yaml:"update_url" envAbsolute:"PRODUCT_OPS_IOS_UPDATE_URL"`
			RecoveryURL             string `yaml:"recovery_url" envAbsolute:"PRODUCT_OPS_IOS_RECOVERY_URL"`
		} `yaml:"ios"`
		Android struct {
			LatestVersion               string   `yaml:"latest_version" envAbsolute:"PRODUCT_OPS_ANDROID_LATEST_VERSION"`
			LatestBuild                 string   `yaml:"latest_build" envAbsolute:"PRODUCT_OPS_ANDROID_LATEST_BUILD"`
			MinimumSupportedVersion     string   `yaml:"minimum_supported_version" envAbsolute:"PRODUCT_OPS_ANDROID_MINIMUM_SUPPORTED_VERSION"`
			MinimumSupportedBuild       string   `yaml:"minimum_supported_build" envAbsolute:"PRODUCT_OPS_ANDROID_MINIMUM_SUPPORTED_BUILD"`
			UpdateURL                   string   `yaml:"update_url" envAbsolute:"PRODUCT_OPS_ANDROID_UPDATE_URL"`
			RecoveryURL                 string   `yaml:"recovery_url" envAbsolute:"PRODUCT_OPS_ANDROID_RECOVERY_URL"`
			APKURL                      string   `yaml:"apk_url" envAbsolute:"PRODUCT_OPS_ANDROID_APK_URL"`
			APKHostAllowlist            []string `yaml:"apk_host_allowlist" envAbsolute:"PRODUCT_OPS_ANDROID_APK_HOST_ALLOWLIST"`
			APKPackageName              string   `yaml:"apk_package_name" envAbsolute:"PRODUCT_OPS_ANDROID_APK_PACKAGE_NAME"`
			APKSHA256                   string   `yaml:"apk_sha256" envAbsolute:"PRODUCT_OPS_ANDROID_APK_SHA256"`
			APKSizeBytes                int64    `yaml:"apk_size_bytes" envAbsolute:"PRODUCT_OPS_ANDROID_APK_SIZE_BYTES"`
			APKSigningCertificateSHA256 string   `yaml:"apk_signing_certificate_sha256" envAbsolute:"PRODUCT_OPS_ANDROID_APK_SIGNING_CERTIFICATE_SHA256"`
			MinAndroidVersion           string   `yaml:"min_android_version" envAbsolute:"PRODUCT_OPS_ANDROID_MIN_ANDROID_VERSION"`
		} `yaml:"android"`
		Web struct {
			LatestVersion           string `yaml:"latest_version" envAbsolute:"PRODUCT_OPS_WEB_LATEST_VERSION"`
			LatestBuild             string `yaml:"latest_build" envAbsolute:"PRODUCT_OPS_WEB_LATEST_BUILD"`
			MinimumSupportedVersion string `yaml:"minimum_supported_version" envAbsolute:"PRODUCT_OPS_WEB_MINIMUM_SUPPORTED_VERSION"`
			MinimumSupportedBuild   string `yaml:"minimum_supported_build" envAbsolute:"PRODUCT_OPS_WEB_MINIMUM_SUPPORTED_BUILD"`
			UpdateURL               string `yaml:"update_url" envAbsolute:"PRODUCT_OPS_WEB_UPDATE_URL"`
			RecoveryURL             string `yaml:"recovery_url" envAbsolute:"PRODUCT_OPS_WEB_RECOVERY_URL"`
		} `yaml:"web"`
	} `yaml:"app_release"`

	AccountEnforcement struct {
		RequestTimeoutMS int `yaml:"request_timeout_ms"`
		PollIntervalMS   int `yaml:"poll_interval_ms"`
		LeaseDurationMS  int `yaml:"lease_duration_ms"`
		InitialBackoffMS int `yaml:"initial_backoff_ms"`
		MaxBackoffMS     int `yaml:"max_backoff_ms"`
		MaxPendingAgeMS  int `yaml:"max_pending_age_ms"`
		MaxAttempts      int `yaml:"max_attempts"`
		BatchSize        int `yaml:"batch_size"`
	} `yaml:"account_enforcement"`

	MongoDB  servicekit.MongoConfig    `yaml:"mongodb"`
	Postgres servicekit.PostgresConfig `yaml:"postgres"`

	Elasticsearch struct {
		Endpoint               string `yaml:"endpoint" env:"ELASTICSEARCH_ENDPOINT"`
		APIKey                 string `yaml:"api_key" env:"ELASTICSEARCH_API_KEY"`
		RawIndex               string `yaml:"raw_index" env:"ELASTICSEARCH_RAW_INDEX"`
		StartupDiagnosticIndex string `yaml:"startup_diagnostic_index" env:"ELASTICSEARCH_STARTUP_DIAGNOSTIC_INDEX"`
		RuntimeLogIndex        string `yaml:"runtime_log_index" env:"ELASTICSEARCH_RUNTIME_LOG_INDEX"`
		AggregateIndex         string `yaml:"aggregate_index" env:"ELASTICSEARCH_AGGREGATE_INDEX"`
		TimeoutMS              int    `yaml:"timeout_ms" env:"ELASTICSEARCH_TIMEOUT_MS"`
	} `yaml:"elasticsearch"`

	TelemetryAlerts struct {
		PolicyPath      string `yaml:"policy_path" env:"TELEMETRY_ALERTS_POLICY_PATH"`
		AlertmanagerURL string `yaml:"alertmanager_url" env:"TELEMETRY_ALERTS_ALERTMANAGER_URL"`
		IntervalMS      int    `yaml:"interval_ms" env:"TELEMETRY_ALERTS_INTERVAL_MS"`
	} `yaml:"telemetry_alerts"`

	Redis struct {
		Rec     servicekit.RedisSceneConfig `yaml:"rec" envPrefix:"REC"`
		General servicekit.RedisSceneConfig `yaml:"general" envPrefix:"GENERAL"`
	} `yaml:"redis" envPrefix:"REDIS"`

	// LogSinkAdapterID 由 generated runtime.log.sink Binding 解析，不来自快照。
	LogSinkAdapterID string `yaml:"-"`
}

// retiredEnvKeys 是迁移到声明式装配时退役的手写覆盖键。
// MONGODB_* 与无前缀 REDIS_*_ADDR 都不由本服务的部署面注入——后者是
// assistant-service 的注入键，同机共享环境时会把本服务连到别人的实例。
func retiredEnvKeys() []string {
	return []string{
		"MONGODB_URI",
		"MONGODB_DATABASE",
		"MONGO_URI",
		"POSTGRES_DSN",
		"REDIS_GENERAL_ADDR",
		"REDIS_REC_ADDR",
	}
}

// resolveRedisScenes 把两份声明装配成三个 codegen scene：realtime 复用
// general 的物理实例（product-ops 只读实时事件流，不独立分库）。
func resolveRedisScenes(cfg *config) map[string]servicekit.RedisSceneConfig {
	return map[string]servicekit.RedisSceneConfig{
		"rec":      cfg.Redis.Rec,
		"general":  cfg.Redis.General,
		"realtime": cfg.Redis.General,
	}
}

// resolveLogSinkBinding 从 generated runtime.log.sink Binding 解析事件仓库
// adapter 与其端点/超时；缺 secret 或端点即 fail-closed。
func resolveLogSinkBinding(
	cfg *config,
	configProvider runtimeconfig.RuntimeConfigProvider,
) error {
	if configProvider == nil {
		return fmt.Errorf("runtime.log.sink binding has no runtime config provider")
	}
	descriptor, found := eventrecordgenerated.CompiledBindingFor("runtime.log.sink")
	if !found {
		return fmt.Errorf(
			"runtime.log.sink binding is missing for environment=%s", cfg.Environment,
		)
	}
	cfg.LogSinkAdapterID = descriptor.AdapterID
	if descriptor.State != "enabled" {
		// Prod 可以在厂商 secret 注入前保持 blocked。
		return nil
	}
	for _, environmentKey := range descriptor.SecretEnvironmentKeys {
		if _, ok := configProvider.GetString(environmentKey); !ok {
			return fmt.Errorf(
				"runtime.log.sink secret material is unavailable for environment=%s",
				cfg.Environment,
			)
		}
	}
	switch descriptor.AdapterID {
	case logsink.ElasticsearchAdapterID:
		environmentKey, exists := descriptor.EndpointEnvironmentKeys["endpoint"]
		if !exists {
			return fmt.Errorf("runtime.log.sink endpoint role=endpoint is not declared")
		}
		value, ok := configProvider.GetString(environmentKey)
		if !ok || strings.TrimSpace(value) == "" {
			return fmt.Errorf(
				"runtime.log.sink endpoint material is unavailable for role=endpoint",
			)
		}
		cfg.Elasticsearch.Endpoint = strings.TrimSpace(value)
		cfg.Elasticsearch.TimeoutMS = descriptor.TimeoutMilliseconds
		if cfg.Elasticsearch.TimeoutMS <= 0 {
			return fmt.Errorf("runtime.log.sink binding has an invalid timeout")
		}
		return nil
	default:
		return fmt.Errorf(
			"runtime.log.sink selects unsupported adapter=%s", descriptor.AdapterID,
		)
	}
}

// validateProductOpsConfig 施加领域配置下界。它在 required 校验之后、任何
// 外部连接之前执行，因此非法配置不会产生副作用。
func validateProductOpsConfig(cfg *config) error {
	if err := resolveLogSinkBinding(cfg, runtimeconfig.EnvRuntimeConfigProvider{}); err != nil {
		return err
	}
	if err := rejectUnrenderedPlaceholders(cfg); err != nil {
		return err
	}
	if cfg.UserAccountSecurityAuthority.TimeoutMs <= 0 ||
		cfg.UserAccountSecurityAuthority.TimeoutMs > 5000 {
		return fmt.Errorf("user_account_security_authority.timeout_ms must be within 1..5000")
	}
	if err := validateAccountEnforcementBounds(cfg); err != nil {
		return err
	}
	if err := validateEventRepositoryBounds(cfg); err != nil {
		return err
	}
	// 运营台的 rec/general 两个 scene 都必须落到真实实例：memory 会让实验分流
	// 与事件批次账本变成单实例内存态，跨实例读写立刻不一致。
	for name, scene := range map[string]servicekit.RedisSceneConfig{
		"rec":     cfg.Redis.Rec,
		"general": cfg.Redis.General,
	} {
		mode, err := scene.DeclaredMode()
		if err != nil {
			return fmt.Errorf("redis.%s %w", name, err)
		}
		if mode == servicekit.RedisModeMemory {
			return fmt.Errorf(
				"redis.%s must declare a real topology: experiment "+
					"assignment and event batch ledgers require "+
					"cross-instance visibility", name,
			)
		}
	}
	return nil
}

// rejectUnrenderedPlaceholders 拒收未被环境装配替换的 ${VAR} 占位符：
// 它既不是有效端点也不是缺席，直接连接会把注入缺口伪装成连接错误。
func rejectUnrenderedPlaceholders(cfg *config) error {
	for field, value := range map[string]string{
		"mongodb.uri":            cfg.MongoDB.URI,
		"postgres.dsn":           cfg.Postgres.DSN,
		"elasticsearch.endpoint": cfg.Elasticsearch.Endpoint,
	} {
		if strings.HasPrefix(strings.TrimSpace(value), "${") {
			return fmt.Errorf("%s still holds an unrendered placeholder: %s", field, value)
		}
	}
	return nil
}

func validateAccountEnforcementBounds(cfg *config) error {
	enforcement := cfg.AccountEnforcement
	if enforcement.RequestTimeoutMS <= 0 || enforcement.RequestTimeoutMS > 10000 {
		return fmt.Errorf("account_enforcement.request_timeout_ms must be within 1..10000")
	}
	if enforcement.PollIntervalMS <= 0 || enforcement.PollIntervalMS > 60000 {
		return fmt.Errorf("account_enforcement.poll_interval_ms must be within 1..60000")
	}
	if enforcement.LeaseDurationMS < enforcement.RequestTimeoutMS ||
		enforcement.LeaseDurationMS > 120000 {
		return fmt.Errorf(
			"account_enforcement.lease_duration_ms must cover request timeout and stay within 120000",
		)
	}
	if enforcement.InitialBackoffMS <= 0 ||
		enforcement.MaxBackoffMS < enforcement.InitialBackoffMS ||
		enforcement.MaxBackoffMS > 300000 {
		return fmt.Errorf("account_enforcement backoff bounds are invalid")
	}
	if enforcement.MaxPendingAgeMS < enforcement.RequestTimeoutMS ||
		enforcement.MaxPendingAgeMS > 3600000 {
		return fmt.Errorf("account_enforcement.max_pending_age_ms is invalid")
	}
	if enforcement.MaxAttempts < 1 || enforcement.MaxAttempts > 20 {
		return fmt.Errorf("account_enforcement.max_attempts must be within 1..20")
	}
	if enforcement.BatchSize < 1 || enforcement.BatchSize > 100 {
		return fmt.Errorf("account_enforcement.batch_size must be within 1..100")
	}
	return nil
}

func validateEventRepositoryBounds(cfg *config) error {
	switch cfg.LogSinkAdapterID {
	case logsink.ElasticsearchAdapterID:
		for name, value := range map[string]string{
			"endpoint":                 cfg.Elasticsearch.Endpoint,
			"raw_index":                cfg.Elasticsearch.RawIndex,
			"startup_diagnostic_index": cfg.Elasticsearch.StartupDiagnosticIndex,
			"runtime_log_index":        cfg.Elasticsearch.RuntimeLogIndex,
			"aggregate_index":          cfg.Elasticsearch.AggregateIndex,
		} {
			if strings.TrimSpace(value) == "" {
				return fmt.Errorf("elasticsearch.%s is required", name)
			}
		}
		if cfg.Elasticsearch.TimeoutMS <= 0 || cfg.Elasticsearch.TimeoutMS > 10000 {
			return fmt.Errorf("elasticsearch.timeout_ms must be within 1..10000")
		}
		return nil
	default:
		return fmt.Errorf(
			"runtime.log.sink selects unsupported adapter=%s", cfg.LogSinkAdapterID,
		)
	}
}
