package main

import (
	"strings"

	platformredis "quwoquan_service/internal/platform/redis"
	rtredis "quwoquan_service/runtime/redis"
)

func buildTravelRedisRouter(cfg config) (*rtredis.Router, map[string]string) {
	mode := strings.ToLower(strings.TrimSpace(cfg.Redis.General.Mode))
	general := rtredis.SceneConfig{
		Mode: mode, Addr: strings.TrimSpace(cfg.Redis.General.Addr),
		Addrs: cfg.Redis.General.Addrs, Password: cfg.Redis.General.Password,
		DB: cfg.Redis.General.DB, TLS: cfg.Redis.General.TLS,
		PoolSize: cfg.Redis.General.Pool.Size, MinIdleConns: cfg.Redis.General.Pool.MinIdle,
		ReadTimeoutMs:  cfg.Redis.General.Pool.ReadTimeoutMs,
		WriteTimeoutMs: cfg.Redis.General.Pool.WriteTimeoutMs,
		DialTimeoutMs:  cfg.Redis.General.Pool.DialTimeoutMs,
	}
	routerConfig := rtredis.DefaultRouterConfig()
	routerConfig.Scenes["general"] = general
	return platformredis.MustNewRouter(routerConfig), map[string]string{"general": mode}
}
