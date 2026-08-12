package main

import (
	"fmt"
	"os"
	configrelease "quwoquan_service/runtime/configrelease"
	"strconv"
	"strings"

	platformredis "quwoquan_service/internal/platform/redis"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rtredis "quwoquan_service/runtime/redis"
	eventrecordgenerated "quwoquan_service/services/product-ops-service/generated/product_ops/event_record"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/logsink"

	"gopkg.in/yaml.v3"
)

type redisPoolCfg struct {
	Size           int `yaml:"size"`
	MinIdle        int `yaml:"min_idle"`
	ReadTimeoutMs  int `yaml:"read_timeout_ms"`
	WriteTimeoutMs int `yaml:"write_timeout_ms"`
	DialTimeoutMs  int `yaml:"dial_timeout_ms"`
}

type redisSceneCfg struct {
	Mode     string       `yaml:"mode"`
	Addr     string       `yaml:"addr"`
	Addrs    []string     `yaml:"addrs"`
	Password string       `yaml:"password"`
	DB       int          `yaml:"db"`
	TLS      bool         `yaml:"tls"`
	Pool     redisPoolCfg `yaml:"pool"`
}

type config struct {
	Config struct {
		Version string `yaml:"version"`
	} `yaml:"config"`
	Service struct {
		Name string `yaml:"name"`
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`
	AppRelease struct {
		PublicOrigin string `yaml:"public_origin"`
		IOS          struct {
			LatestVersion           string `yaml:"latest_version"`
			LatestBuild             string `yaml:"latest_build"`
			MinimumSupportedVersion string `yaml:"minimum_supported_version"`
			MinimumSupportedBuild   string `yaml:"minimum_supported_build"`
			UpdateURL               string `yaml:"update_url"`
			RecoveryURL             string `yaml:"recovery_url"`
		} `yaml:"ios"`
		Android struct {
			LatestVersion               string   `yaml:"latest_version"`
			LatestBuild                 string   `yaml:"latest_build"`
			MinimumSupportedVersion     string   `yaml:"minimum_supported_version"`
			MinimumSupportedBuild       string   `yaml:"minimum_supported_build"`
			UpdateURL                   string   `yaml:"update_url"`
			RecoveryURL                 string   `yaml:"recovery_url"`
			APKURL                      string   `yaml:"apk_url"`
			APKHostAllowlist            []string `yaml:"apk_host_allowlist"`
			APKPackageName              string   `yaml:"apk_package_name"`
			APKSHA256                   string   `yaml:"apk_sha256"`
			APKSizeBytes                int64    `yaml:"apk_size_bytes"`
			APKSigningCertificateSHA256 string   `yaml:"apk_signing_certificate_sha256"`
			MinAndroidVersion           string   `yaml:"min_android_version"`
		} `yaml:"android"`
		Web struct {
			LatestVersion           string `yaml:"latest_version"`
			LatestBuild             string `yaml:"latest_build"`
			MinimumSupportedVersion string `yaml:"minimum_supported_version"`
			MinimumSupportedBuild   string `yaml:"minimum_supported_build"`
			UpdateURL               string `yaml:"update_url"`
			RecoveryURL             string `yaml:"recovery_url"`
		} `yaml:"web"`
	} `yaml:"app_release"`
	AccountSecurityAuthority struct {
		BaseURL   string `yaml:"base_url"`
		TimeoutMS int    `yaml:"timeout_ms"`
	} `yaml:"account_security_authority"`
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
	MongoDB struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongodb"`
	Postgres struct {
		DSN string `yaml:"dsn"`
	} `yaml:"postgres"`
	Elasticsearch struct {
		Endpoint               string `yaml:"endpoint"`
		APIKey                 string `yaml:"api_key"`
		RawIndex               string `yaml:"raw_index"`
		StartupDiagnosticIndex string `yaml:"startup_diagnostic_index"`
		RuntimeLogIndex        string `yaml:"runtime_log_index"`
		AggregateIndex         string `yaml:"aggregate_index"`
		TimeoutMS              int    `yaml:"timeout_ms"`
	} `yaml:"elasticsearch"`
	Redis struct {
		Rec     redisSceneCfg `yaml:"rec"`
		General redisSceneCfg `yaml:"general"`
	} `yaml:"redis"`
	// LogSinkAdapterID is resolved from the generated runtime.log.sink Binding.
	LogSinkAdapterID string `yaml:"-"`
}

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "product-ops-service")
	appEnv = getenvOrDefault("APP_ENV", "alpha")
	configRoot = os.Getenv("CONFIG_ROOT")
	configVersion = os.Getenv("CONFIG_VERSION")
	imageVersion = os.Getenv("IMAGE_VERSION")
	if !isValidAppEnv(appEnv) {
		return "", "", "", "", "", fmt.Errorf("APP_ENV must be one of alpha|beta|gamma|prod, got %q", appEnv)
	}
	if requiresConfigVersion(appEnv) && strings.TrimSpace(configVersion) == "" {
		return "", "", "", "", "", fmt.Errorf("CONFIG_VERSION is required when APP_ENV=%s", appEnv)
	}
	return serviceName, appEnv, configRoot, configVersion, imageVersion, nil
}

func loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion string) (config, error) {
	cfg := config{}
	path, err := configrelease.File(configRoot, serviceName, appEnv)
	if err != nil {
		return config{}, err
	}
	if err := mergeConfigFile(&cfg, path); err != nil {
		return config{}, fmt.Errorf("read generated runtime config: %w", err)
	}
	return cfg, nil
}

func mergeConfigFile(cfg *config, path string) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return yaml.Unmarshal(raw, cfg)
}

func applyEnvOverrides(cfg *config) {
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_APP_RELEASE_PUBLIC_ORIGIN")); v != "" {
		cfg.AppRelease.PublicOrigin = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_IOS_LATEST_VERSION")); v != "" {
		cfg.AppRelease.IOS.LatestVersion = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_IOS_LATEST_BUILD")); v != "" {
		cfg.AppRelease.IOS.LatestBuild = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_IOS_MINIMUM_SUPPORTED_VERSION")); v != "" {
		cfg.AppRelease.IOS.MinimumSupportedVersion = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_IOS_MINIMUM_SUPPORTED_BUILD")); v != "" {
		cfg.AppRelease.IOS.MinimumSupportedBuild = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_IOS_UPDATE_URL")); v != "" {
		cfg.AppRelease.IOS.UpdateURL = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_IOS_RECOVERY_URL")); v != "" {
		cfg.AppRelease.IOS.RecoveryURL = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ANDROID_LATEST_VERSION")); v != "" {
		cfg.AppRelease.Android.LatestVersion = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ANDROID_LATEST_BUILD")); v != "" {
		cfg.AppRelease.Android.LatestBuild = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ANDROID_MINIMUM_SUPPORTED_VERSION")); v != "" {
		cfg.AppRelease.Android.MinimumSupportedVersion = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ANDROID_MINIMUM_SUPPORTED_BUILD")); v != "" {
		cfg.AppRelease.Android.MinimumSupportedBuild = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ANDROID_UPDATE_URL")); v != "" {
		cfg.AppRelease.Android.UpdateURL = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ANDROID_RECOVERY_URL")); v != "" {
		cfg.AppRelease.Android.RecoveryURL = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ANDROID_APK_URL")); v != "" {
		cfg.AppRelease.Android.APKURL = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ANDROID_APK_HOST_ALLOWLIST")); v != "" {
		cfg.AppRelease.Android.APKHostAllowlist = strings.Split(v, ",")
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ANDROID_APK_PACKAGE_NAME")); v != "" {
		cfg.AppRelease.Android.APKPackageName = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ANDROID_APK_SHA256")); v != "" {
		cfg.AppRelease.Android.APKSHA256 = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ANDROID_APK_SIZE_BYTES")); v != "" {
		if parsed, err := strconv.ParseInt(v, 10, 64); err == nil {
			cfg.AppRelease.Android.APKSizeBytes = parsed
		}
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ANDROID_APK_SIGNING_CERTIFICATE_SHA256")); v != "" {
		cfg.AppRelease.Android.APKSigningCertificateSHA256 = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ANDROID_MIN_ANDROID_VERSION")); v != "" {
		cfg.AppRelease.Android.MinAndroidVersion = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_WEB_LATEST_VERSION")); v != "" {
		cfg.AppRelease.Web.LatestVersion = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_WEB_LATEST_BUILD")); v != "" {
		cfg.AppRelease.Web.LatestBuild = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_WEB_MINIMUM_SUPPORTED_VERSION")); v != "" {
		cfg.AppRelease.Web.MinimumSupportedVersion = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_WEB_MINIMUM_SUPPORTED_BUILD")); v != "" {
		cfg.AppRelease.Web.MinimumSupportedBuild = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_WEB_UPDATE_URL")); v != "" {
		cfg.AppRelease.Web.UpdateURL = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_WEB_RECOVERY_URL")); v != "" {
		cfg.AppRelease.Web.RecoveryURL = v
	}
	if v := strings.TrimSpace(os.Getenv("MONGODB_URI")); v != "" {
		cfg.MongoDB.URI = v
	}
	if v := strings.TrimSpace(os.Getenv("MONGO_URI")); v != "" {
		cfg.MongoDB.URI = v
	}
	if v := strings.TrimSpace(os.Getenv("MONGODB_DATABASE")); v != "" {
		cfg.MongoDB.Database = v
	}
	if v := strings.TrimSpace(os.Getenv("POSTGRES_DSN")); v != "" {
		cfg.Postgres.DSN = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ELASTICSEARCH_ENDPOINT")); v != "" {
		cfg.Elasticsearch.Endpoint = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ELASTICSEARCH_API_KEY")); v != "" {
		cfg.Elasticsearch.APIKey = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ELASTICSEARCH_RAW_INDEX")); v != "" {
		cfg.Elasticsearch.RawIndex = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ELASTICSEARCH_STARTUP_DIAGNOSTIC_INDEX")); v != "" {
		cfg.Elasticsearch.StartupDiagnosticIndex = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ELASTICSEARCH_RUNTIME_LOG_INDEX")); v != "" {
		cfg.Elasticsearch.RuntimeLogIndex = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ELASTICSEARCH_AGGREGATE_INDEX")); v != "" {
		cfg.Elasticsearch.AggregateIndex = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ELASTICSEARCH_TIMEOUT_MS")); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil {
			cfg.Elasticsearch.TimeoutMS = parsed
		}
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_REDIS_GENERAL_ADDR")); v != "" {
		cfg.Redis.General.Addr = v
	}
	if v := strings.TrimSpace(os.Getenv("REDIS_GENERAL_ADDR")); v != "" {
		cfg.Redis.General.Addr = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_REDIS_REC_ADDR")); v != "" {
		cfg.Redis.Rec.Addr = v
	}
	if v := strings.TrimSpace(os.Getenv("REDIS_REC_ADDR")); v != "" {
		cfg.Redis.Rec.Addr = v
	}
	if v := os.Getenv("PRODUCT_OPS_REDIS_GENERAL_PASSWORD"); v != "" {
		cfg.Redis.General.Password = v
	}
	if v := os.Getenv("PRODUCT_OPS_REDIS_REC_PASSWORD"); v != "" {
		cfg.Redis.Rec.Password = v
	}
	if strings.HasPrefix(strings.TrimSpace(cfg.MongoDB.URI), "${") {
		cfg.MongoDB.URI = ""
	}
	if strings.HasPrefix(strings.TrimSpace(cfg.Postgres.DSN), "${") {
		cfg.Postgres.DSN = ""
	}
	if strings.HasPrefix(strings.TrimSpace(cfg.Elasticsearch.Endpoint), "${") {
		cfg.Elasticsearch.Endpoint = ""
	}
}

func resolveLogSinkBinding(
	cfg config,
	appEnv string,
	configProvider runtimeconfig.RuntimeConfigProvider,
) (config, error) {
	if configProvider == nil {
		return config{}, fmt.Errorf("runtime.log.sink binding has no runtime config provider")
	}
	descriptor, found := eventrecordgenerated.ExternalProviderBindingFor(
		appEnv,
		"runtime.log.sink",
	)
	if !found {
		return config{}, fmt.Errorf(
			"runtime.log.sink binding is missing for environment=%s",
			appEnv,
		)
	}
	cfg.LogSinkAdapterID = descriptor.AdapterID
	if descriptor.State != "enabled" {
		// Prod may stay blocked until vendor secrets are injected.
		return cfg, nil
	}
	for _, environmentKey := range descriptor.SecretEnvironmentKeys {
		if _, ok := configProvider.GetString(environmentKey); !ok {
			return config{}, fmt.Errorf(
				"runtime.log.sink secret material is unavailable for environment=%s",
				appEnv,
			)
		}
	}
	requiredEndpoint := func(role string) (string, error) {
		environmentKey, exists := descriptor.EndpointEnvironmentKeys[role]
		if !exists {
			return "", fmt.Errorf(
				"runtime.log.sink endpoint role=%s is not declared",
				role,
			)
		}
		value, ok := configProvider.GetString(environmentKey)
		if !ok || strings.TrimSpace(value) == "" {
			return "", fmt.Errorf(
				"runtime.log.sink endpoint material is unavailable for role=%s",
				role,
			)
		}
		return strings.TrimSpace(value), nil
	}
	switch descriptor.AdapterID {
	case logsink.ElasticsearchAdapterID:
		endpoint, err := requiredEndpoint("endpoint")
		if err != nil {
			return config{}, err
		}
		cfg.Elasticsearch.Endpoint = endpoint
		cfg.Elasticsearch.TimeoutMS = descriptor.TimeoutMilliseconds
		if cfg.Elasticsearch.TimeoutMS <= 0 {
			return config{}, fmt.Errorf("runtime.log.sink binding has an invalid timeout")
		}
		return cfg, nil
	default:
		return config{}, fmt.Errorf(
			"runtime.log.sink selects unsupported adapter=%s",
			descriptor.AdapterID,
		)
	}
}

func validateRuntimeConfigurationIdentity(cfg config, configVersion, imageVersion string) error {
	fileVersion := strings.TrimSpace(cfg.Config.Version)
	environmentVersion := strings.TrimSpace(configVersion)
	if environmentVersion != "" && fileVersion != "" && fileVersion != environmentVersion {
		return fmt.Errorf(
			"CONFIG_VERSION mismatch: env=%s file=%s",
			environmentVersion,
			fileVersion,
		)
	}
	return controlplane.ValidateImageIdentity(imageVersion)
}

func validateRequiredRuntimeConfig(cfg config, _ ...string) error {
	if strings.TrimSpace(cfg.AccountSecurityAuthority.BaseURL) == "" {
		return fmt.Errorf("account_security_authority.base_url is required")
	}
	if cfg.AccountSecurityAuthority.TimeoutMS <= 0 ||
		cfg.AccountSecurityAuthority.TimeoutMS > 5000 {
		return fmt.Errorf("account_security_authority.timeout_ms must be within 1..5000")
	}
	if cfg.AccountEnforcement.RequestTimeoutMS <= 0 ||
		cfg.AccountEnforcement.RequestTimeoutMS > 10000 {
		return fmt.Errorf("account_enforcement.request_timeout_ms must be within 1..10000")
	}
	if cfg.AccountEnforcement.PollIntervalMS <= 0 ||
		cfg.AccountEnforcement.PollIntervalMS > 60000 {
		return fmt.Errorf("account_enforcement.poll_interval_ms must be within 1..60000")
	}
	if cfg.AccountEnforcement.LeaseDurationMS < cfg.AccountEnforcement.RequestTimeoutMS ||
		cfg.AccountEnforcement.LeaseDurationMS > 120000 {
		return fmt.Errorf("account_enforcement.lease_duration_ms must cover request timeout and stay within 120000")
	}
	if cfg.AccountEnforcement.InitialBackoffMS <= 0 ||
		cfg.AccountEnforcement.MaxBackoffMS < cfg.AccountEnforcement.InitialBackoffMS ||
		cfg.AccountEnforcement.MaxBackoffMS > 300000 {
		return fmt.Errorf("account_enforcement backoff bounds are invalid")
	}
	if cfg.AccountEnforcement.MaxPendingAgeMS < cfg.AccountEnforcement.RequestTimeoutMS ||
		cfg.AccountEnforcement.MaxPendingAgeMS > 3600000 {
		return fmt.Errorf("account_enforcement.max_pending_age_ms is invalid")
	}
	if cfg.AccountEnforcement.MaxAttempts < 1 || cfg.AccountEnforcement.MaxAttempts > 20 {
		return fmt.Errorf("account_enforcement.max_attempts must be within 1..20")
	}
	if cfg.AccountEnforcement.BatchSize < 1 || cfg.AccountEnforcement.BatchSize > 100 {
		return fmt.Errorf("account_enforcement.batch_size must be within 1..100")
	}
	if strings.TrimSpace(cfg.MongoDB.URI) == "" {
		return fmt.Errorf("mongodb.uri is required")
	}
	if strings.TrimSpace(cfg.MongoDB.Database) == "" {
		return fmt.Errorf("mongodb.database is required")
	}
	if strings.TrimSpace(cfg.Postgres.DSN) == "" {
		return fmt.Errorf("postgres.dsn is required")
	}
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
		if cfg.Elasticsearch.TimeoutMS <= 0 ||
			cfg.Elasticsearch.TimeoutMS > 10000 {
			return fmt.Errorf(
				"elasticsearch.timeout_ms must be within 1..10000",
			)
		}
	default:
		return fmt.Errorf(
			"runtime.log.sink selects unsupported adapter=%s",
			cfg.LogSinkAdapterID,
		)
	}
	if _, err := buildRedisSceneConfig("rec", cfg.Redis.Rec); err != nil {
		return err
	}
	if _, err := buildRedisSceneConfig("general", cfg.Redis.General); err != nil {
		return err
	}
	return nil
}

func buildRedisRouter(cfg config) (*rtredis.Router, map[string]string, error) {
	recScene, err := buildRedisSceneConfig("rec", cfg.Redis.Rec)
	if err != nil {
		return nil, nil, err
	}
	generalScene, err := buildRedisSceneConfig("general", cfg.Redis.General)
	if err != nil {
		return nil, nil, err
	}
	router, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"rec":      recScene,
			"general":  generalScene,
			"realtime": generalScene,
		},
		PrefixRoutes: rtredis.GeneratedPrefixRoutes(),
		DefaultScene: rtredis.GeneratedDefaultScene,
	})
	if err != nil {
		return nil, nil, err
	}
	return router, map[string]string{
		"general": generalScene.Mode,
	}, nil
}

func buildRedisSceneConfig(name string, cfg redisSceneCfg) (rtredis.SceneConfig, error) {
	mode := strings.ToLower(strings.TrimSpace(cfg.Mode))
	addr := strings.TrimSpace(cfg.Addr)
	addrs := normalizedRedisAddrs(cfg.Addrs)
	if len(addrs) == 0 && addr != "" {
		addrs = normalizedRedisAddrs(strings.Split(addr, ","))
	}
	if mode == "" {
		switch {
		case len(addrs) > 1:
			mode = "cluster"
		case addr != "" || len(addrs) == 1:
			mode = "standalone"
		default:
			return rtredis.SceneConfig{}, fmt.Errorf("redis.%s endpoint is required", name)
		}
	}
	switch mode {
	case "standalone":
		if addr == "" && len(addrs) == 1 {
			addr = addrs[0]
		}
		if addr == "" || strings.Contains(addr, ",") {
			return rtredis.SceneConfig{}, fmt.Errorf("redis.%s standalone addr is required", name)
		}
		addrs = nil
	case "cluster":
		if len(addrs) == 0 {
			return rtredis.SceneConfig{}, fmt.Errorf("redis.%s cluster addrs are required", name)
		}
		addr = ""
	default:
		return rtredis.SceneConfig{}, fmt.Errorf("redis.%s mode %q is not supported in service wiring", name, mode)
	}
	return rtredis.SceneConfig{
		Mode:           mode,
		Addr:           addr,
		Addrs:          addrs,
		Password:       cfg.Password,
		DB:             cfg.DB,
		TLS:            cfg.TLS,
		PoolSize:       cfg.Pool.Size,
		MinIdleConns:   cfg.Pool.MinIdle,
		ReadTimeoutMs:  cfg.Pool.ReadTimeoutMs,
		WriteTimeoutMs: cfg.Pool.WriteTimeoutMs,
		DialTimeoutMs:  cfg.Pool.DialTimeoutMs,
	}, nil
}

func normalizedRedisAddrs(values []string) []string {
	out := make([]string, 0, len(values))
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return out
}

func isValidAppEnv(env string) bool {
	switch env {
	case "alpha", "beta", "gamma", "prod":
		return true
	default:
		return false
	}
}

func requiresConfigVersion(env string) bool {
	switch env {
	case "gamma", "prod":
		return true
	default:
		return false
	}
}

func getenvOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}
