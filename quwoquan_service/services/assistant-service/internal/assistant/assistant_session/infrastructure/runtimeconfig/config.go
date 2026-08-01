package runtimeconfig

import (
	"fmt"
	"os"
	configrelease "quwoquan_service/runtime/configrelease"
	"strconv"
	"strings"

	"gopkg.in/yaml.v3"
)

type RedisPoolConfig struct {
	Size           int `yaml:"size"`
	MinIdle        int `yaml:"min_idle"`
	ReadTimeoutMs  int `yaml:"read_timeout_ms"`
	WriteTimeoutMs int `yaml:"write_timeout_ms"`
	DialTimeoutMs  int `yaml:"dial_timeout_ms"`
}

type RedisSceneConfig struct {
	Mode     string          `yaml:"mode"`
	Addr     string          `yaml:"addr"`
	Addrs    []string        `yaml:"addrs"`
	Password string          `yaml:"password"`
	DB       int             `yaml:"db"`
	TLS      bool            `yaml:"tls"`
	Pool     RedisPoolConfig `yaml:"pool"`
}

type UserProfileConfig struct {
	BaseURL   string `yaml:"base_url"`
	TimeoutMs int    `yaml:"timeout_ms"`
}

type ServiceEgressConfig struct {
	BaseURL   string `yaml:"base_url"`
	TimeoutMs int    `yaml:"timeout_ms"`
}

// ModelTierConfig 是档位到模型标识的映射。模型标识是运营可调配置，不允许写死在
// adapter 里。
type ModelTierConfig struct {
	Fast      string `yaml:"fast"`
	Balanced  string `yaml:"balanced"`
	Reasoning string `yaml:"reasoning"`
}

type ModelConfig struct {
	NativeToolCalling bool            `yaml:"native_tool_calling"`
	Tier              ModelTierConfig `yaml:"tier"`
}

type Config struct {
	Config struct {
		Version string `yaml:"version"`
	} `yaml:"config"`
	Service struct {
		Name string `yaml:"name"`
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`
	Postgres struct {
		DSN                    string `yaml:"dsn"`
		MaxOpenConns           int    `yaml:"max_open_conns"`
		MaxIdleConns           int    `yaml:"max_idle_conns"`
		ConnMaxLifetimeMinutes int    `yaml:"conn_max_lifetime_minutes"`
	} `yaml:"postgres"`
	MongoDB struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongodb"`
	Redis struct {
		Rec      RedisSceneConfig `yaml:"rec"`
		General  RedisSceneConfig `yaml:"general"`
		Realtime RedisSceneConfig `yaml:"realtime"`
	} `yaml:"redis"`
	Model                    ModelConfig         `yaml:"model"`
	SearchService            ServiceEgressConfig `yaml:"search_service"`
	EntityService            ServiceEgressConfig `yaml:"entity_service"`
	ContentService           ServiceEgressConfig `yaml:"content_service"`
	UserProfile              UserProfileConfig   `yaml:"user_profile"`
	UserService              ServiceEgressConfig `yaml:"user_service"`
	ChatService              ServiceEgressConfig `yaml:"chat_service"`
	NotificationService      ServiceEgressConfig `yaml:"notification_service"`
	AccountSecurityAuthority ServiceEgressConfig `yaml:"account_security_authority"`
	PolicyPublication        struct {
		ReleaseArtifactRef string `yaml:"release_artifact_ref"`
		RolloutArtifactRef string `yaml:"rollout_artifact_ref"`
	} `yaml:"policy_publication"`
}

func ResolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "assistant-service")
	appEnv = getenvOrDefault("APP_ENV", "alpha")
	configRoot = os.Getenv("CONFIG_ROOT")
	configVersion = os.Getenv("CONFIG_VERSION")
	imageVersion = os.Getenv("IMAGE_VERSION")
	if !IsValidAppEnv(appEnv) {
		return "", "", "", "", "", fmt.Errorf("APP_ENV must be one of alpha|beta|gamma|prod, got %q", appEnv)
	}
	if RequiresConfigVersion(appEnv) && strings.TrimSpace(configVersion) == "" {
		return "", "", "", "", "", fmt.Errorf("CONFIG_VERSION is required when APP_ENV=%s", appEnv)
	}
	return serviceName, appEnv, configRoot, configVersion, imageVersion, nil
}

func LoadRuntimeConfig(serviceName, appEnv, configRoot, configVersion string) (Config, error) {
	cfg := Config{}
	path, err := configrelease.File(configRoot, serviceName, appEnv)
	if err != nil {
		return Config{}, err
	}
	if err := MergeConfigFile(&cfg, path); err != nil {
		return Config{}, fmt.Errorf("read generated runtime config: %w", err)
	}
	return cfg, nil
}

func MergeConfigFile(cfg *Config, path string) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return yaml.Unmarshal(raw, cfg)
}

func ApplyEnvOverrides(cfg *Config) error {
	if v := strings.TrimSpace(os.Getenv("MONGODB_URI")); v != "" {
		cfg.MongoDB.URI = v
	}
	if v := strings.TrimSpace(os.Getenv("MONGODB_DATABASE")); v != "" {
		cfg.MongoDB.Database = v
	}
	if v := strings.TrimSpace(os.Getenv("POSTGRES_DSN")); v != "" {
		cfg.Postgres.DSN = v
	}
	if err := applyRedisSceneEnvOverrides("REDIS_GENERAL", &cfg.Redis.General); err != nil {
		return err
	}
	if err := applyRedisSceneEnvOverrides("REDIS_REC", &cfg.Redis.Rec); err != nil {
		return err
	}
	if v := strings.TrimSpace(os.Getenv("ASSISTANT_CHAT_BASE_URL")); v != "" {
		cfg.ChatService.BaseURL = v
	}
	if v := strings.TrimSpace(os.Getenv("ASSISTANT_USER_SERVICE_BASE_URL")); v != "" {
		cfg.UserService.BaseURL = v
	}
	if v := strings.TrimSpace(os.Getenv("ASSISTANT_NOTIFICATION_BASE_URL")); v != "" {
		cfg.NotificationService.BaseURL = v
	}
	if v := strings.TrimSpace(os.Getenv("ASSISTANT_SEARCH_SERVICE_BASE_URL")); v != "" {
		cfg.SearchService.BaseURL = v
	}
	if v := strings.TrimSpace(os.Getenv("ASSISTANT_ENTITY_SERVICE_BASE_URL")); v != "" {
		cfg.EntityService.BaseURL = v
	}
	if v := strings.TrimSpace(os.Getenv("ASSISTANT_CONTENT_SERVICE_BASE_URL")); v != "" {
		cfg.ContentService.BaseURL = v
	}
	return nil
}

func IsValidAppEnv(env string) bool {
	switch env {
	case "alpha", "beta", "gamma", "prod":
		return true
	default:
		return false
	}
}

func RequiresConfigVersion(env string) bool {
	switch env {
	case "gamma", "prod":
		return true
	default:
		return false
	}
}

func applyRedisSceneEnvOverrides(prefix string, cfg *RedisSceneConfig) error {
	if v := strings.TrimSpace(os.Getenv(prefix + "_MODE")); v != "" {
		cfg.Mode = v
	}
	if v := strings.TrimSpace(os.Getenv(prefix + "_ADDR")); v != "" {
		cfg.Addr = v
	}
	if v := strings.TrimSpace(os.Getenv(prefix + "_ADDRS")); v != "" {
		cfg.Addrs = nonEmptyStrings(strings.Split(v, ","))
	}
	if v := os.Getenv(prefix + "_PASSWORD"); v != "" {
		cfg.Password = v
	}
	if v := strings.TrimSpace(os.Getenv(prefix + "_TLS")); v != "" {
		enabled, err := strconv.ParseBool(v)
		if err != nil {
			return fmt.Errorf("%s_TLS must be a boolean: %w", prefix, err)
		}
		cfg.TLS = enabled
	}
	if v := strings.TrimSpace(os.Getenv(prefix + "_DB")); v != "" {
		db, err := strconv.Atoi(v)
		if err != nil || db < 0 {
			return fmt.Errorf("%s_DB must be a non-negative integer", prefix)
		}
		cfg.DB = db
	}
	return nil
}

func getenvOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func nonEmptyStrings(values []string) []string {
	out := make([]string, 0, len(values))
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return out
}
