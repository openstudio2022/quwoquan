package main

import (
	"context"
	"log/slog"
	"strings"
	"time"

	platformredis "quwoquan_service/internal/platform/redis"
	rtredis "quwoquan_service/runtime/redis"
	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
)

// 每日 affinity 衰减调度 + Redis Router 构建，自 main.go 拆出
// （同 main 包，R03 行数预算，行为不变）。

func startDailyAffinityDecay(ctx context.Context, agg *recinfra.InterestProfileAggregator, lock rtredis.Client, logger *slog.Logger) {
	if agg == nil {
		return
	}
	go func() {
		ticker := time.NewTicker(dailyAffinityDecayCheckInterval)
		defer ticker.Stop()
		runDailyAffinityDecayOnce(ctx, agg, lock, logger)
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				runDailyAffinityDecayOnce(ctx, agg, lock, logger)
			}
		}
	}()
}

// runDailyAffinityDecayOnce acquires the per-day single-flight lock and, if won,
// decays one day's worth of half-life from every user's affinity counters.
func runDailyAffinityDecayOnce(ctx context.Context, agg *recinfra.InterestProfileAggregator, lock rtredis.Client, logger *slog.Logger) {
	if lock != nil {
		key := "rec:affinity-decay:lock:" + time.Now().UTC().Format("2006-01-02")
		// TTL > 24h so the daily key survives until the next day's key takes
		// over; the date in the key, not the TTL, scopes one run per day.
		won, err := lock.SetNX(ctx, key, "1", 26*time.Hour)
		if err != nil {
			logger.Warn("affinity decay lock acquire failed; skipping tick", "err", err)
			return
		}
		if !won {
			return // another replica already ran (or is running) today
		}
	}
	if err := agg.DecayAll(ctx, 1); err != nil {
		logger.Warn("affinity decay failed", "err", err)
	}
}

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
