package main

import (
	"fmt"
	"os"
	"strings"

	"gopkg.in/yaml.v3"

	configrelease "quwoquan_service/runtime/configrelease"
)

type config struct {
	Config struct {
		Version string `yaml:"version"`
	} `yaml:"config"`
	Service struct {
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`
	AccountSecurityAuthority struct {
		BaseURL   string `yaml:"baseUrl"`
		TimeoutMs int    `yaml:"timeoutMs"`
	} `yaml:"accountSecurityAuthority"`
	ContentPublicAuthority struct {
		BaseURL   string `yaml:"baseUrl"`
		TimeoutMs int    `yaml:"timeoutMs"`
	} `yaml:"contentPublicAuthority"`
	EntityPublicAuthority struct {
		BaseURL   string `yaml:"baseUrl"`
		TimeoutMs int    `yaml:"timeoutMs"`
	} `yaml:"entityPublicAuthority"`
	ChatSourceAuthority struct {
		BaseURL   string `yaml:"baseUrl"`
		TimeoutMs int    `yaml:"timeoutMs"`
	} `yaml:"chatSourceAuthority"`
	CircleSourceAuthority struct {
		BaseURL   string `yaml:"baseUrl"`
		TimeoutMs int    `yaml:"timeoutMs"`
	} `yaml:"circleSourceAuthority"`
	Mongo struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongo"`
	Redis struct {
		General redisSceneConfig `yaml:"general"`
	} `yaml:"redis"`
}

type redisSceneConfig struct {
	Mode     string   `yaml:"mode"`
	Addr     string   `yaml:"addr"`
	Addrs    []string `yaml:"addrs"`
	Password string   `yaml:"password"`
	DB       int      `yaml:"db"`
	TLS      bool     `yaml:"tls"`
	Pool     struct {
		Size           int `yaml:"size"`
		MinIdle        int `yaml:"min_idle"`
		ReadTimeoutMs  int `yaml:"read_timeout_ms"`
		WriteTimeoutMs int `yaml:"write_timeout_ms"`
		DialTimeoutMs  int `yaml:"dial_timeout_ms"`
	} `yaml:"pool"`
}

type runtimeIdentity struct {
	ServiceName   string
	AppEnv        string
	ConfigRoot    string
	ConfigVersion string
	ImageVersion  string
}

func resolveRuntimeIdentity() (runtimeIdentity, error) {
	identity := runtimeIdentity{
		ServiceName:   getenvOrDefault("SERVICE_NAME", "travel-service"),
		AppEnv:        getenvOrDefault("APP_ENV", "alpha"),
		ConfigRoot:    strings.TrimSpace(os.Getenv("CONFIG_ROOT")),
		ConfigVersion: strings.TrimSpace(os.Getenv("CONFIG_VERSION")),
		ImageVersion:  strings.TrimSpace(os.Getenv("IMAGE_VERSION")),
	}
	switch identity.AppEnv {
	case "alpha", "beta":
	case "gamma", "prod":
		if identity.ConfigVersion == "" {
			return runtimeIdentity{}, fmt.Errorf("CONFIG_VERSION is required when APP_ENV=%s", identity.AppEnv)
		}
	default:
		return runtimeIdentity{}, fmt.Errorf("APP_ENV must be alpha|beta|gamma|prod, got %q", identity.AppEnv)
	}
	return identity, nil
}

func loadRuntimeConfig(identity runtimeIdentity) (config, error) {
	path, err := configrelease.File(identity.ConfigRoot, identity.ServiceName, identity.AppEnv)
	if err != nil {
		return config{}, err
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return config{}, err
	}
	var cfg config
	if err := yaml.Unmarshal(raw, &cfg); err != nil {
		return config{}, fmt.Errorf("parse %s: %w", path, err)
	}
	if identity.ConfigVersion != "" && strings.TrimSpace(cfg.Config.Version) != "" &&
		identity.ConfigVersion != strings.TrimSpace(cfg.Config.Version) {
		return config{}, fmt.Errorf(
			"CONFIG_VERSION mismatch: env=%s file=%s",
			identity.ConfigVersion,
			cfg.Config.Version,
		)
	}
	applyEnvOverrides(&cfg)
	if err := validateConfig(cfg); err != nil {
		return config{}, err
	}
	return cfg, nil
}

func applyEnvOverrides(cfg *config) {
	if value := strings.TrimSpace(os.Getenv("TRAVEL_SERVICE_ADDR")); value != "" {
		cfg.Service.HTTP.Addr = value
	}
	if value := strings.TrimSpace(os.Getenv("TRAVEL_MONGO_URI")); value != "" {
		cfg.Mongo.URI = value
	}
	if value := strings.TrimSpace(os.Getenv("TRAVEL_MONGO_DATABASE")); value != "" {
		cfg.Mongo.Database = value
	}
	if value := strings.TrimSpace(os.Getenv("TRAVEL_REDIS_GENERAL_MODE")); value != "" {
		cfg.Redis.General.Mode = value
	}
	if value := strings.TrimSpace(os.Getenv("TRAVEL_REDIS_GENERAL_ADDR")); value != "" {
		cfg.Redis.General.Addr = value
	}
	if value := strings.TrimSpace(os.Getenv("TRAVEL_REDIS_GENERAL_ADDRS")); value != "" {
		cfg.Redis.General.Addrs = strings.Split(value, ",")
	}
	if value := strings.TrimSpace(os.Getenv("TRAVEL_REDIS_GENERAL_PASSWORD")); value != "" {
		cfg.Redis.General.Password = value
	}
	switch strings.ToLower(strings.TrimSpace(os.Getenv("TRAVEL_REDIS_GENERAL_TLS"))) {
	case "true", "1", "yes", "on":
		cfg.Redis.General.TLS = true
	}
}

func validateConfig(cfg config) error {
	switch {
	case strings.TrimSpace(cfg.Service.HTTP.Addr) == "":
		return fmt.Errorf("service.http.addr is required")
	case strings.TrimSpace(cfg.Mongo.URI) == "":
		return fmt.Errorf("mongo.uri is required")
	case strings.TrimSpace(cfg.Mongo.Database) == "":
		return fmt.Errorf("mongo.database is required")
	case strings.TrimSpace(cfg.AccountSecurityAuthority.BaseURL) == "":
		return fmt.Errorf("accountSecurityAuthority.baseUrl is required")
	case cfg.AccountSecurityAuthority.TimeoutMs <= 0:
		return fmt.Errorf("accountSecurityAuthority.timeoutMs must be positive")
	case strings.TrimSpace(cfg.ContentPublicAuthority.BaseURL) == "":
		return fmt.Errorf("contentPublicAuthority.baseUrl is required")
	case cfg.ContentPublicAuthority.TimeoutMs <= 0:
		return fmt.Errorf("contentPublicAuthority.timeoutMs must be positive")
	case strings.TrimSpace(cfg.EntityPublicAuthority.BaseURL) == "":
		return fmt.Errorf("entityPublicAuthority.baseUrl is required")
	case cfg.EntityPublicAuthority.TimeoutMs <= 0:
		return fmt.Errorf("entityPublicAuthority.timeoutMs must be positive")
	case strings.TrimSpace(cfg.ChatSourceAuthority.BaseURL) == "":
		return fmt.Errorf("chatSourceAuthority.baseUrl is required")
	case cfg.ChatSourceAuthority.TimeoutMs <= 0:
		return fmt.Errorf("chatSourceAuthority.timeoutMs must be positive")
	case strings.TrimSpace(cfg.CircleSourceAuthority.BaseURL) == "":
		return fmt.Errorf("circleSourceAuthority.baseUrl is required")
	case cfg.CircleSourceAuthority.TimeoutMs <= 0:
		return fmt.Errorf("circleSourceAuthority.timeoutMs must be positive")
	case strings.TrimSpace(cfg.Redis.General.Mode) == "":
		return fmt.Errorf("redis.general.mode is required")
	case strings.TrimSpace(cfg.Redis.General.Addr) == "" && len(cfg.Redis.General.Addrs) == 0:
		return fmt.Errorf("redis.general endpoint is required")
	default:
		return nil
	}
}

func getenvOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}
