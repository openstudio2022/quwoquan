package bootstrap

import (
	"strings"

	platformredis "quwoquan_service/internal/platform/redis"
	rtredis "quwoquan_service/runtime/redis"
)

// buildRedisRouter creates the production redis.Router from YAML/env config.
// preflightConfig rejects missing endpoints and memory mode before this point;
// alpha fixtures use their physically separate runner instead of this root.
func buildRedisRouter(cfg config) *rtredis.Router {
	routerCfg := rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"rec":      toSceneConfig(cfg.Redis.Rec),
			"general":  toSceneConfig(cfg.Redis.General),
			"realtime": toSceneConfig(cfg.Redis.Realtime),
		},
		PrefixRoutes: rtredis.GeneratedPrefixRoutes(),
		DefaultScene: rtredis.GeneratedDefaultScene,
	}
	return platformredis.MustNewRouter(routerCfg)
}

// toSceneConfig converts the YAML redisSceneCfg to rtredis.SceneConfig.
func toSceneConfig(r redisSceneCfg) rtredis.SceneConfig {
	mode := strings.ToLower(strings.TrimSpace(r.Mode))
	if mode == "" {
		mode = "standalone"
	}
	return rtredis.SceneConfig{
		Mode:         mode,
		Addr:         r.Addr,
		Addrs:        r.Addrs,
		Password:     r.Password,
		DB:           r.DB,
		TLS:          r.TLS,
		PoolSize:     r.Pool.Size,
		MinIdleConns: r.Pool.MinIdle,
	}
}
