package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	platformredis "quwoquan_service/internal/platform/redis"
	rtredis "quwoquan_service/runtime/redis"

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
	MongoDB struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongodb"`
	Postgres struct {
		DSN string `yaml:"dsn"`
	} `yaml:"postgres"`
	SLS struct {
		Region                    string `yaml:"region"`
		Endpoint                  string `yaml:"endpoint"`
		Project                   string `yaml:"project"`
		RawLogstore               string `yaml:"raw_logstore"`
		StartupDiagnosticLogstore string `yaml:"startup_diagnostic_logstore"`
		AggregateLogstore         string `yaml:"aggregate_logstore"`
		TimeoutMS                 int    `yaml:"timeout_ms"`
	} `yaml:"sls"`
	Redis struct {
		Rec     redisSceneCfg `yaml:"rec"`
		General redisSceneCfg `yaml:"general"`
	} `yaml:"redis"`
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
	if strings.TrimSpace(configRoot) != "" {
		defaultFile := filepath.Join(configRoot, "configs", serviceName, "default", "config.yaml")
		envFile := filepath.Join(configRoot, "configs", serviceName, appEnv, "config.yaml")
		if err := mergeConfigFile(&cfg, defaultFile); err != nil {
			return config{}, fmt.Errorf("read default config: %w", err)
		}
		if err := mergeConfigFile(&cfg, envFile); err != nil {
			return config{}, fmt.Errorf("read env config: %w", err)
		}
		if strings.TrimSpace(configVersion) != "" {
			versionFile := filepath.Join(configRoot, "quwoquan_service", "services", serviceName, "configs", "releases", configVersion+".yaml")
			if err := mergeConfigFile(&cfg, versionFile); err != nil {
				return config{}, fmt.Errorf("read version config: %w", err)
			}
		}
		return cfg, nil
	}
	localDefault := filepath.Join("configs", "default", "config.yaml")
	localEnv := filepath.Join("configs", appEnv, "config.yaml")
	if _, err := os.Stat(localDefault); err == nil {
		if err := mergeConfigFile(&cfg, localDefault); err != nil {
			return config{}, fmt.Errorf("read local default config: %w", err)
		}
		if err := mergeConfigFile(&cfg, localEnv); err != nil {
			return config{}, fmt.Errorf("read local env config: %w", err)
		}
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
	if strings.HasPrefix(strings.TrimSpace(cfg.MongoDB.URI), "${") {
		cfg.MongoDB.URI = ""
	}
	if strings.HasPrefix(strings.TrimSpace(cfg.Postgres.DSN), "${") {
		cfg.Postgres.DSN = ""
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

func validateRequiredRuntimeConfig(cfg config) error {
	if strings.TrimSpace(cfg.MongoDB.URI) == "" {
		return fmt.Errorf("mongodb.uri is required")
	}
	if strings.TrimSpace(cfg.MongoDB.Database) == "" {
		return fmt.Errorf("mongodb.database is required")
	}
	if strings.TrimSpace(cfg.Postgres.DSN) == "" {
		return fmt.Errorf("postgres.dsn is required")
	}
	for name, value := range map[string]string{
		"region":                      cfg.SLS.Region,
		"endpoint":                    cfg.SLS.Endpoint,
		"project":                     cfg.SLS.Project,
		"raw_logstore":                cfg.SLS.RawLogstore,
		"startup_diagnostic_logstore": cfg.SLS.StartupDiagnosticLogstore,
		"aggregate_logstore":          cfg.SLS.AggregateLogstore,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("sls.%s is required", name)
		}
	}
	if cfg.SLS.TimeoutMS <= 0 || cfg.SLS.TimeoutMS > 10000 {
		return fmt.Errorf("sls.timeout_ms must be within 1..10000")
	}
	if _, err := buildRedisSceneConfig("rec", cfg.Redis.Rec); err != nil {
		return err
	}
	if _, err := buildRedisSceneConfig("general", cfg.Redis.General); err != nil {
		return err
	}
	return nil
}

func buildRedisRouter(cfg config) (*rtredis.Router, error) {
	recScene, err := buildRedisSceneConfig("rec", cfg.Redis.Rec)
	if err != nil {
		return nil, err
	}
	generalScene, err := buildRedisSceneConfig("general", cfg.Redis.General)
	if err != nil {
		return nil, err
	}
	return platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"rec":      recScene,
			"general":  generalScene,
			"realtime": generalScene,
		},
		PrefixRoutes: rtredis.GeneratedPrefixRoutes(),
		DefaultScene: rtredis.GeneratedDefaultScene,
	})
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
