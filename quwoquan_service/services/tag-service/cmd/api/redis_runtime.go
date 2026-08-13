package bootstrap

import (
	"os"
	"strings"

	platformredis "quwoquan_service/internal/platform/redis"
	rtredis "quwoquan_service/runtime/redis"
)

type redisSceneCfg struct {
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

func applyTagRedisEnvOverrides(cfg *redisSceneCfg) {
	if value := strings.TrimSpace(os.Getenv("TAG_REDIS_GENERAL_MODE")); value != "" {
		cfg.Mode = value
	}
	if value := strings.TrimSpace(os.Getenv("TAG_REDIS_GENERAL_ADDR")); value != "" {
		cfg.Addr = value
	}
	if value := strings.TrimSpace(os.Getenv("TAG_REDIS_GENERAL_ADDRS")); value != "" {
		cfg.Addrs = strings.Split(value, ",")
	}
	if value := strings.TrimSpace(os.Getenv("TAG_REDIS_GENERAL_PASSWORD")); value != "" {
		cfg.Password = value
	}
	switch strings.ToLower(
		strings.TrimSpace(os.Getenv("TAG_REDIS_GENERAL_TLS")),
	) {
	case "true", "1", "yes", "on":
		cfg.TLS = true
	}
}

func buildTagRedisRouter(cfg config) (*rtredis.Router, map[string]string) {
	base := rtredis.DefaultRouterConfig()
	general := rtredis.SceneConfig{
		Mode:           cfg.Redis.General.Mode,
		Addr:           cfg.Redis.General.Addr,
		Addrs:          cfg.Redis.General.Addrs,
		Password:       cfg.Redis.General.Password,
		DB:             cfg.Redis.General.DB,
		TLS:            cfg.Redis.General.TLS,
		PoolSize:       cfg.Redis.General.Pool.Size,
		MinIdleConns:   cfg.Redis.General.Pool.MinIdle,
		ReadTimeoutMs:  cfg.Redis.General.Pool.ReadTimeoutMs,
		WriteTimeoutMs: cfg.Redis.General.Pool.WriteTimeoutMs,
		DialTimeoutMs:  cfg.Redis.General.Pool.DialTimeoutMs,
	}
	base.Scenes["general"] = general
	return platformredis.MustNewRouter(base), map[string]string{
		"general": general.Mode,
	}
}
