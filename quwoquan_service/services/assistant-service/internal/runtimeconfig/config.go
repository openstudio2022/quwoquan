package runtimeconfig

import (
	"fmt"
	"os"
	"path/filepath"
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

type ProviderConfig struct {
	Provider  string `yaml:"provider"`
	BaseURL   string `yaml:"base_url"`
	Model     string `yaml:"model"`
	APIKeyEnv string `yaml:"api_key_env"`
	TimeoutMs int    `yaml:"timeout_ms"`
}

type ContentSearchConfig struct {
	BaseURL   string `yaml:"base_url"`
	TimeoutMs int    `yaml:"timeout_ms"`
}

type UserProfileConfig struct {
	BaseURL   string `yaml:"base_url"`
	TimeoutMs int    `yaml:"timeout_ms"`
}

type ServiceEgressConfig struct {
	BaseURL   string `yaml:"base_url"`
	TimeoutMs int    `yaml:"timeout_ms"`
}

type Config struct {
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
	ModelProvider       ProviderConfig      `yaml:"model_provider"`
	SearchProvider      ProviderConfig      `yaml:"search_provider"`
	ContentSearch       ContentSearchConfig `yaml:"content_search"`
	UserProfile         UserProfileConfig   `yaml:"user_profile"`
	ChatService         ServiceEgressConfig `yaml:"chat_service"`
	NotificationService ServiceEgressConfig `yaml:"notification_service"`
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
	if strings.TrimSpace(configRoot) != "" {
		defaultFile := filepath.Join(configRoot, "configs", serviceName, "default", "config.yaml")
		envFile := filepath.Join(configRoot, "configs", serviceName, appEnv, "config.yaml")
		if err := MergeConfigFile(&cfg, defaultFile); err != nil {
			return Config{}, fmt.Errorf("read default config: %w", err)
		}
		if err := MergeConfigFile(&cfg, envFile); err != nil {
			return Config{}, fmt.Errorf("read env config: %w", err)
		}
		if strings.TrimSpace(configVersion) != "" {
			versionFile := filepath.Join(configRoot, "quwoquan_service", "services", serviceName, "configs", "releases", configVersion+".yaml")
			if err := MergeConfigFile(&cfg, versionFile); err != nil {
				return Config{}, fmt.Errorf("read version config: %w", err)
			}
		}
		return cfg, nil
	}
	localDefault := filepath.Join("configs", "default", "config.yaml")
	localEnv := filepath.Join("configs", appEnv, "config.yaml")
	if _, err := os.Stat(localDefault); err == nil {
		if err := MergeConfigFile(&cfg, localDefault); err != nil {
			return Config{}, fmt.Errorf("read local default config: %w", err)
		}
		if err := MergeConfigFile(&cfg, localEnv); err != nil {
			return Config{}, fmt.Errorf("read local env config: %w", err)
		}
		if strings.TrimSpace(configVersion) != "" {
			versionFile := filepath.Join("configs", "releases", configVersion+".yaml")
			if _, err := os.Stat(versionFile); err == nil {
				if err := MergeConfigFile(&cfg, versionFile); err != nil {
					return Config{}, fmt.Errorf("read local version config: %w", err)
				}
			}
		}
		return cfg, nil
	}
	current := filepath.Join("configs", "config.yaml")
	if err := MergeConfigFile(&cfg, current); err != nil {
		return Config{}, fmt.Errorf("read current config: %w", err)
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
	if v := strings.TrimSpace(os.Getenv("ASSISTANT_NOTIFICATION_BASE_URL")); v != "" {
		cfg.NotificationService.BaseURL = v
	}
	applyProviderEnvOverrides(&cfg.ModelProvider, "ASSISTANT_MODEL")
	applyProviderEnvOverrides(&cfg.SearchProvider, "ASSISTANT_SEARCH")
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

func applyProviderEnvOverrides(cfg *ProviderConfig, prefix string) {
	if v := strings.TrimSpace(os.Getenv(prefix + "_PROVIDER")); v != "" {
		cfg.Provider = v
	}
	if v := strings.TrimSpace(os.Getenv(prefix + "_BASE_URL")); v != "" {
		cfg.BaseURL = v
	}
	if v := strings.TrimSpace(os.Getenv(prefix + "_MODEL")); v != "" {
		cfg.Model = v
	}
	if v := strings.TrimSpace(os.Getenv(prefix + "_API_KEY_ENV")); v != "" {
		cfg.APIKeyEnv = v
	}
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
