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

	TelemetryElasticsearch struct {
		Endpoint               string `yaml:"endpoint" env:"ELASTICSEARCH_ENDPOINT"`
		APIKey                 string `yaml:"api_key" env:"ELASTICSEARCH_API_KEY"`
		RawIndex               string `yaml:"raw_index" env:"ELASTICSEARCH_RAW_INDEX"`
		StartupDiagnosticIndex string `yaml:"startup_diagnostic_index" env:"ELASTICSEARCH_STARTUP_DIAGNOSTIC_INDEX"`
		AggregateIndex         string `yaml:"aggregate_index" env:"ELASTICSEARCH_AGGREGATE_INDEX"`
		TimeoutMS              int    `yaml:"timeout_ms" env:"ELASTICSEARCH_TIMEOUT_MS"`
	} `yaml:"telemetry_elasticsearch" envPrefix:"TELEMETRY"`

	RuntimeLogElasticsearch struct {
		Endpoint       string `yaml:"endpoint" env:"ELASTICSEARCH_ENDPOINT"`
		APIKey         string `yaml:"api_key" env:"ELASTICSEARCH_API_KEY"`
		RawIndex       string `yaml:"raw_index" env:"ELASTICSEARCH_RAW_INDEX"`
		AggregateIndex string `yaml:"aggregate_index" env:"ELASTICSEARCH_AGGREGATE_INDEX"`
		TimeoutMS      int    `yaml:"timeout_ms" env:"ELASTICSEARCH_TIMEOUT_MS"`
	} `yaml:"runtime_log_elasticsearch" envPrefix:"RUNTIME_LOG"`

	TelemetryAlerts struct {
		PolicyPath      string `yaml:"policy_path" env:"TELEMETRY_ALERTS_POLICY_PATH"`
		AlertmanagerURL string `yaml:"alertmanager_url" env:"TELEMETRY_ALERTS_ALERTMANAGER_URL"`
		IntervalMS      int    `yaml:"interval_ms" env:"TELEMETRY_ALERTS_INTERVAL_MS"`
	} `yaml:"telemetry_alerts"`

	Redis struct {
		Rec     servicekit.RedisSceneConfig `yaml:"rec" envPrefix:"REC"`
		General servicekit.RedisSceneConfig `yaml:"general" envPrefix:"GENERAL"`
	} `yaml:"redis" envPrefix:"REDIS"`

	// Adapter ID 由两个 generated Provider Binding 分别解析，不来自快照。
	TelemetrySinkAdapterID  string `yaml:"-"`
	RuntimeLogSinkAdapterID string `yaml:"-"`
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
		"PRODUCT_OPS_ELASTICSEARCH_ENDPOINT",
		"PRODUCT_OPS_ELASTICSEARCH_API_KEY",
		"PRODUCT_OPS_ELASTICSEARCH_RAW_INDEX",
		"PRODUCT_OPS_ELASTICSEARCH_STARTUP_DIAGNOSTIC_INDEX",
		"PRODUCT_OPS_ELASTICSEARCH_RUNTIME_LOG_INDEX",
		"PRODUCT_OPS_ELASTICSEARCH_AGGREGATE_INDEX",
		"PRODUCT_OPS_ELASTICSEARCH_TIMEOUT_MS",
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

const (
	productTelemetrySinkCapability = "product.telemetry.sink"
	runtimeLogSinkCapability       = "runtime.log.sink"
)

// resolveEventStoreBindings 从当前打包环境的两个 generated Provider Binding
// 分别解析 endpoint、secret 与 timeout，任何一轨缺失都 fail-closed。
func resolveEventStoreBindings(
	cfg *config,
	configProvider runtimeconfig.RuntimeConfigProvider,
) error {
	if configProvider == nil {
		return fmt.Errorf("event store bindings have no runtime config provider")
	}
	telemetryDescriptor, found := eventrecordgenerated.CompiledBindingFor(
		productTelemetrySinkCapability,
	)
	if !found {
		return fmt.Errorf(
			"%s binding is missing for environment=%s",
			productTelemetrySinkCapability, cfg.Environment,
		)
	}
	runtimeLogDescriptor, found := eventrecordgenerated.CompiledBindingFor(
		runtimeLogSinkCapability,
	)
	if !found {
		return fmt.Errorf(
			"%s binding is missing for environment=%s",
			runtimeLogSinkCapability, cfg.Environment,
		)
	}
	if err := resolveElasticsearchBinding(
		productTelemetrySinkCapability, telemetryDescriptor, configProvider,
		&cfg.TelemetryElasticsearch.Endpoint, &cfg.TelemetryElasticsearch.APIKey,
		&cfg.TelemetryElasticsearch.TimeoutMS, &cfg.TelemetrySinkAdapterID,
	); err != nil {
		return err
	}
	return resolveElasticsearchBinding(
		runtimeLogSinkCapability, runtimeLogDescriptor, configProvider,
		&cfg.RuntimeLogElasticsearch.Endpoint, &cfg.RuntimeLogElasticsearch.APIKey,
		&cfg.RuntimeLogElasticsearch.TimeoutMS, &cfg.RuntimeLogSinkAdapterID,
	)
}

func resolveElasticsearchBinding(
	capability string,
	descriptor eventrecordgenerated.ExternalProviderBinding,
	configProvider runtimeconfig.RuntimeConfigProvider,
	endpoint *string,
	apiKey *string,
	timeoutMS *int,
	adapterID *string,
) error {
	*adapterID = descriptor.AdapterID
	if descriptor.State != "enabled" {
		// 打包前源码描述符不固化环境；若 capability 已存在于多环境投影，
		// 仅将 endpoint/timeout 交给 config schema 与 env 覆盖解析。
		return nil
	}
	if len(descriptor.SecretEnvironmentKeys) > 1 {
		return fmt.Errorf("%s declares multiple API key secrets", capability)
	}
	for _, environmentKey := range descriptor.SecretEnvironmentKeys {
		value, ok := configProvider.GetString(environmentKey)
		if !ok {
			return fmt.Errorf(
				"%s secret material is unavailable for environment key=%s",
				capability, environmentKey,
			)
		}
		*apiKey = strings.TrimSpace(value)
	}
	if descriptor.AdapterID != logsink.ElasticsearchAdapterID {
		return fmt.Errorf(
			"%s selects unsupported adapter=%s", capability, descriptor.AdapterID,
		)
	}
	environmentKey, exists := descriptor.EndpointEnvironmentKeys["endpoint"]
	if !exists {
		return fmt.Errorf("%s endpoint role=endpoint is not declared", capability)
	}
	value, ok := configProvider.GetString(environmentKey)
	if !ok || strings.TrimSpace(value) == "" {
		return fmt.Errorf(
			"%s endpoint material is unavailable for role=endpoint", capability,
		)
	}
	*endpoint = strings.TrimSpace(value)
	*timeoutMS = descriptor.TimeoutMilliseconds
	if *timeoutMS <= 0 {
		return fmt.Errorf("%s binding has an invalid timeout", capability)
	}
	return nil
}

// validateProductOpsConfig 施加领域配置下界。它在 required 校验之后、任何
// 外部连接之前执行，因此非法配置不会产生副作用。
func validateProductOpsConfig(cfg *config) error {
	if err := resolveEventStoreBindings(cfg, runtimeconfig.EnvRuntimeConfigProvider{}); err != nil {
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
		"mongodb.uri":                        cfg.MongoDB.URI,
		"postgres.dsn":                       cfg.Postgres.DSN,
		"telemetry_elasticsearch.endpoint":   cfg.TelemetryElasticsearch.Endpoint,
		"runtime_log_elasticsearch.endpoint": cfg.RuntimeLogElasticsearch.Endpoint,
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
	if cfg.TelemetrySinkAdapterID != logsink.ElasticsearchAdapterID {
		return fmt.Errorf(
			"%s selects unsupported adapter=%s",
			productTelemetrySinkCapability, cfg.TelemetrySinkAdapterID,
		)
	}
	if cfg.RuntimeLogSinkAdapterID != logsink.ElasticsearchAdapterID {
		return fmt.Errorf(
			"%s selects unsupported adapter=%s",
			runtimeLogSinkCapability, cfg.RuntimeLogSinkAdapterID,
		)
	}
	for name, value := range map[string]string{
		"telemetry_elasticsearch.endpoint":                 cfg.TelemetryElasticsearch.Endpoint,
		"telemetry_elasticsearch.raw_index":                cfg.TelemetryElasticsearch.RawIndex,
		"telemetry_elasticsearch.startup_diagnostic_index": cfg.TelemetryElasticsearch.StartupDiagnosticIndex,
		"telemetry_elasticsearch.aggregate_index":          cfg.TelemetryElasticsearch.AggregateIndex,
		"runtime_log_elasticsearch.endpoint":               cfg.RuntimeLogElasticsearch.Endpoint,
		"runtime_log_elasticsearch.raw_index":              cfg.RuntimeLogElasticsearch.RawIndex,
		"runtime_log_elasticsearch.aggregate_index":        cfg.RuntimeLogElasticsearch.AggregateIndex,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("%s is required", name)
		}
	}
	for name, timeoutMS := range map[string]int{
		"telemetry_elasticsearch.timeout_ms":   cfg.TelemetryElasticsearch.TimeoutMS,
		"runtime_log_elasticsearch.timeout_ms": cfg.RuntimeLogElasticsearch.TimeoutMS,
	} {
		if timeoutMS <= 0 || timeoutMS > 10000 {
			return fmt.Errorf("%s must be within 1..10000", name)
		}
	}
	if cfg.Environment == "prod" || cfg.Environment == "release" {
		if cfg.TelemetryElasticsearch.APIKey == "" || cfg.RuntimeLogElasticsearch.APIKey == "" {
			return fmt.Errorf("prod telemetry and runtime-log Elasticsearch API keys are required")
		}
		if cfg.TelemetryElasticsearch.APIKey == cfg.RuntimeLogElasticsearch.APIKey {
			return fmt.Errorf("prod telemetry and runtime-log Elasticsearch API keys must be distinct")
		}
	}
	for telemetryRole, telemetryIndex := range map[string]string{
		"raw_index":                cfg.TelemetryElasticsearch.RawIndex,
		"startup_diagnostic_index": cfg.TelemetryElasticsearch.StartupDiagnosticIndex,
		"aggregate_index":          cfg.TelemetryElasticsearch.AggregateIndex,
	} {
		for runtimeRole, runtimeIndex := range map[string]string{
			"raw_index":       cfg.RuntimeLogElasticsearch.RawIndex,
			"aggregate_index": cfg.RuntimeLogElasticsearch.AggregateIndex,
		} {
			if telemetryIndex == runtimeIndex {
				return fmt.Errorf(
					"telemetry_elasticsearch.%s and runtime_log_elasticsearch.%s must not overlap",
					telemetryRole, runtimeRole,
				)
			}
		}
	}
	return nil
}
