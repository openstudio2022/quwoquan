package main

import (
	"fmt"
	"os"
	configrelease "quwoquan_service/runtime/configrelease"
	"strconv"
	"strings"

	platformredis "quwoquan_service/internal/platform/redis"
	runtimeconfig "quwoquan_service/runtime/config"
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
		Version         string `yaml:"version"`
		MinImageVersion string `yaml:"min_image_version"`
		MaxImageVersion string `yaml:"max_image_version"`
	} `yaml:"config"`
	Service struct {
		Name string `yaml:"name"`
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`
	AppRelease struct {
		PublicOrigin string `yaml:"public_origin"`
		RecoveryURL  string `yaml:"recovery_url"`
		IOS          struct {
			LatestVersion string `yaml:"latest_version"`
			LatestBuild   string `yaml:"latest_build"`
			AppStoreURL   string `yaml:"app_store_url"`
		} `yaml:"ios"`
		Android struct {
			LatestVersion               string   `yaml:"latest_version"`
			LatestBuild                 string   `yaml:"latest_build"`
			APKURL                      string   `yaml:"apk_url"`
			APKHostAllowlist            []string `yaml:"apk_host_allowlist"`
			APKPackageName              string   `yaml:"apk_package_name"`
			APKSHA256                   string   `yaml:"apk_sha256"`
			APKSizeBytes                int64    `yaml:"apk_size_bytes"`
			APKSigningCertificateSHA256 string   `yaml:"apk_signing_certificate_sha256"`
		} `yaml:"android"`
	} `yaml:"app_release"`
	AccountSecurityAuthority struct {
		BaseURL   string `yaml:"base_url"`
		TimeoutMS int    `yaml:"timeout_ms"`
	} `yaml:"account_security_authority"`
	MongoDB struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongodb"`
	Postgres struct {
		DSN string `yaml:"dsn"`
	} `yaml:"postgres"`
	Elasticsearch struct {
		Endpoint               string `yaml:"endpoint"`
		RawIndex               string `yaml:"raw_index"`
		StartupDiagnosticIndex string `yaml:"startup_diagnostic_index"`
		RuntimeLogIndex        string `yaml:"runtime_log_index"`
		AggregateIndex         string `yaml:"aggregate_index"`
		TimeoutMS              int    `yaml:"timeout_ms"`
	} `yaml:"elasticsearch"`
	SLS struct {
		Region                    string `yaml:"region"`
		Endpoint                  string `yaml:"endpoint"`
		Project                   string `yaml:"project"`
		RawLogstore               string `yaml:"raw_logstore"`
		StartupDiagnosticLogstore string `yaml:"startup_diagnostic_logstore"`
		RuntimeLogstore           string `yaml:"runtime_logstore"`
		AggregateLogstore         string `yaml:"aggregate_logstore"`
		TimeoutMS                 int    `yaml:"timeout_ms"`
	} `yaml:"sls"`
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
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_APP_RELEASE_RECOVERY_URL")); v != "" {
		cfg.AppRelease.RecoveryURL = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_IOS_LATEST_VERSION")); v != "" {
		cfg.AppRelease.IOS.LatestVersion = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_IOS_LATEST_BUILD")); v != "" {
		cfg.AppRelease.IOS.LatestBuild = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_IOS_APP_STORE_URL")); v != "" {
		cfg.AppRelease.IOS.AppStoreURL = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ANDROID_LATEST_VERSION")); v != "" {
		cfg.AppRelease.Android.LatestVersion = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ANDROID_LATEST_BUILD")); v != "" {
		cfg.AppRelease.Android.LatestBuild = v
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
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_SLS_REGION")); v != "" {
		cfg.SLS.Region = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_SLS_ENDPOINT")); v != "" {
		cfg.SLS.Endpoint = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_SLS_PROJECT")); v != "" {
		cfg.SLS.Project = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_SLS_RAW_LOGSTORE")); v != "" {
		cfg.SLS.RawLogstore = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_SLS_STARTUP_DIAGNOSTIC_LOGSTORE")); v != "" {
		cfg.SLS.StartupDiagnosticLogstore = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_SLS_RUNTIME_LOGSTORE")); v != "" {
		cfg.SLS.RuntimeLogstore = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_SLS_AGGREGATE_LOGSTORE")); v != "" {
		cfg.SLS.AggregateLogstore = v
	}
	if v := strings.TrimSpace(os.Getenv("PRODUCT_OPS_SLS_TIMEOUT_MS")); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil {
			cfg.SLS.TimeoutMS = parsed
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
	if strings.HasPrefix(strings.TrimSpace(cfg.SLS.Endpoint), "${") {
		cfg.SLS.Endpoint = ""
	}
	if strings.HasPrefix(strings.TrimSpace(cfg.SLS.Region), "${") {
		cfg.SLS.Region = ""
	}
	if strings.HasPrefix(strings.TrimSpace(cfg.SLS.Project), "${") {
		cfg.SLS.Project = ""
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
	case logsink.PostgresTelemetryLocalAdapterID:
		if descriptor.TimeoutMilliseconds <= 0 {
			return config{}, fmt.Errorf("runtime.log.sink binding has an invalid timeout")
		}
		return cfg, nil
	case logsink.ElasticsearchLocalAdapterID:
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
	case logsink.AliyunSLSAdapterID:
		var err error
		if cfg.SLS.Region, err = requiredEndpoint("region"); err != nil {
			return config{}, err
		}
		if cfg.SLS.Endpoint, err = requiredEndpoint("endpoint"); err != nil {
			return config{}, err
		}
		if cfg.SLS.Project, err = requiredEndpoint("project"); err != nil {
			return config{}, err
		}
		cfg.SLS.TimeoutMS = descriptor.TimeoutMilliseconds
		if cfg.SLS.TimeoutMS <= 0 {
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

func validateRuntimeCompatibility(cfg config, configVersion, imageVersion string) error {
	_ = configVersion
	if strings.TrimSpace(imageVersion) == "" {
		return nil
	}
	min := strings.TrimSpace(cfg.Config.MinImageVersion)
	max := strings.TrimSpace(cfg.Config.MaxImageVersion)
	if min != "" && compareSemver(imageVersion, min) < 0 {
		return fmt.Errorf("IMAGE_VERSION=%s < min_image_version=%s", imageVersion, min)
	}
	if max != "" && compareSemver(imageVersion, max) > 0 {
		return fmt.Errorf("IMAGE_VERSION=%s > max_image_version=%s", imageVersion, max)
	}
	return nil
}

func compareSemver(a, b string) int {
	ap := parseSemver(a)
	bp := parseSemver(b)
	for i := 0; i < 3; i++ {
		if ap[i] < bp[i] {
			return -1
		}
		if ap[i] > bp[i] {
			return 1
		}
	}
	return 0
}

func parseSemver(raw string) [3]int {
	trimmed := strings.TrimPrefix(strings.TrimSpace(raw), "v")
	parts := strings.Split(trimmed, ".")
	out := [3]int{}
	for i := 0; i < len(parts) && i < 3; i++ {
		out[i], _ = strconv.Atoi(parts[i])
	}
	return out
}

func validateRequiredRuntimeConfig(cfg config, appEnv ...string) error {
	if strings.TrimSpace(cfg.MongoDB.URI) == "" {
		return fmt.Errorf("mongodb.uri is required")
	}
	if strings.TrimSpace(cfg.MongoDB.Database) == "" {
		return fmt.Errorf("mongodb.database is required")
	}
	if strings.TrimSpace(cfg.Postgres.DSN) == "" {
		return fmt.Errorf("postgres.dsn is required")
	}
	environment := "prod"
	if len(appEnv) > 0 && strings.TrimSpace(appEnv[0]) != "" {
		environment = strings.TrimSpace(appEnv[0])
	}
	switch cfg.LogSinkAdapterID {
	case logsink.PostgresTelemetryLocalAdapterID:
		if postgresTelemetrySchema(environment) == "" {
			return fmt.Errorf(
				"postgres telemetry adapter is unsupported for environment=%s",
				environment,
			)
		}
	case logsink.ElasticsearchLocalAdapterID:
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
	case logsink.AliyunSLSAdapterID:
		for name, value := range map[string]string{
			"region":                      cfg.SLS.Region,
			"endpoint":                    cfg.SLS.Endpoint,
			"project":                     cfg.SLS.Project,
			"raw_logstore":                cfg.SLS.RawLogstore,
			"startup_diagnostic_logstore": cfg.SLS.StartupDiagnosticLogstore,
			"runtime_logstore":            cfg.SLS.RuntimeLogstore,
			"aggregate_logstore":          cfg.SLS.AggregateLogstore,
		} {
			if strings.TrimSpace(value) == "" {
				return fmt.Errorf("sls.%s is required", name)
			}
		}
		if cfg.SLS.TimeoutMS <= 0 || cfg.SLS.TimeoutMS > 10000 {
			return fmt.Errorf("sls.timeout_ms must be within 1..10000")
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

// postgresTelemetrySchema 返回 Alpha/Beta 本地替身的固定 schema。后端选择只由
// generated runtime.log.sink Binding 驱动，禁止通过 ad-hoc 环境变量动态切换。
func postgresTelemetrySchema(appEnv string) string {
	switch strings.ToLower(strings.TrimSpace(appEnv)) {
	case "integration", "alpha":
		return "telemetry_local_integration"
	case "beta-integration", "beta_integration", "beta":
		return "telemetry_local_beta"
	default:
		return ""
	}
}

func operatorOIDCRequired(appEnv string) bool {
	switch strings.ToLower(strings.TrimSpace(appEnv)) {
	case "alpha", "beta", "gamma":
		return false
	default:
		return true
	}
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
