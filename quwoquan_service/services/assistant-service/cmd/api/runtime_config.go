package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

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
		Rec      redisSceneCfg `yaml:"rec"`
		General  redisSceneCfg `yaml:"general"`
		Realtime redisSceneCfg `yaml:"realtime"`
	} `yaml:"redis"`
	ModelProvider  providerCfg      `yaml:"model_provider"`
	SearchProvider providerCfg      `yaml:"search_provider"`
	ContentSearch  contentSearchCfg `yaml:"content_search"`
	UserProfile    userProfileCfg   `yaml:"user_profile"`
	ChatService    serviceEgressCfg `yaml:"chat_service"`
}

// userProfileCfg configures the egress to user-service's interest-profile read
// (GET /v1/users/{userId}/interest-profile) used to personalize proactive skills.
// base_url empty disables personalization (proactive output stays non-personalized);
// alpha points at the local user-service.
type userProfileCfg struct {
	BaseURL   string `yaml:"base_url"`
	TimeoutMs int    `yaml:"timeout_ms"`
}

type serviceEgressCfg struct {
	BaseURL   string `yaml:"base_url"`
	TimeoutMs int    `yaml:"timeout_ms"`
}

type providerCfg struct {
	Provider  string `yaml:"provider"`
	BaseURL   string `yaml:"base_url"`
	Model     string `yaml:"model"`
	APIKeyEnv string `yaml:"api_key_env"`
	TimeoutMs int    `yaml:"timeout_ms"`
}

// contentSearchCfg 配置 app_search 直连 content-service 站内检索（GET /v1/content/posts/search）。
// base_url 为空时回退既有 fake/外部搜索；alpha 默认指向本地 content-service。
type contentSearchCfg struct {
	BaseURL   string `yaml:"base_url"`
	TimeoutMs int    `yaml:"timeout_ms"`
}

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "assistant-service")
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
		if strings.TrimSpace(configVersion) != "" {
			versionFile := filepath.Join("configs", "releases", configVersion+".yaml")
			if _, err := os.Stat(versionFile); err == nil {
				if err := mergeConfigFile(&cfg, versionFile); err != nil {
					return config{}, fmt.Errorf("read local version config: %w", err)
				}
			}
		}
		return cfg, nil
	}
	current := filepath.Join("configs", "config.yaml")
	if err := mergeConfigFile(&cfg, current); err != nil {
		return config{}, fmt.Errorf("read current config: %w", err)
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
	if v := strings.TrimSpace(os.Getenv("MONGODB_DATABASE")); v != "" {
		cfg.MongoDB.Database = v
	}
	if v := strings.TrimSpace(os.Getenv("POSTGRES_DSN")); v != "" {
		cfg.Postgres.DSN = v
	}
	if v := strings.TrimSpace(os.Getenv("REDIS_GENERAL_ADDR")); v != "" {
		cfg.Redis.General.Addr = v
	}
	if v := strings.TrimSpace(os.Getenv("REDIS_REC_ADDR")); v != "" {
		cfg.Redis.Rec.Addr = v
	}
	if v := strings.TrimSpace(os.Getenv("ASSISTANT_CHAT_BASE_URL")); v != "" {
		cfg.ChatService.BaseURL = v
	}
	applyProviderEnvOverrides(&cfg.ModelProvider, "ASSISTANT_MODEL")
	applyProviderEnvOverrides(&cfg.SearchProvider, "ASSISTANT_SEARCH")
}

func applyProviderEnvOverrides(cfg *providerCfg, prefix string) {
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
