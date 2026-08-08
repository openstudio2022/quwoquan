package main

import (
	"strings"

	platformredis "quwoquan_service/internal/platform/redis"
	rtredis "quwoquan_service/runtime/redis"
)

func buildRedisRouter(cfg config) *rtredis.Router {
	rc := cfg.Redis.General
	rt := cfg.Redis.Realtime
	if strings.TrimSpace(rt.Mode) == "" {
		rt.Mode = rc.Mode
	}
	if strings.TrimSpace(rt.Addr) == "" && len(rt.Addrs) == 0 {
		rt.Addr = rc.Addr
		rt.Addrs = append([]string(nil), rc.Addrs...)
	}
	if strings.TrimSpace(rt.Password) == "" {
		rt.Password = rc.Password
	}
	if rt.DB == 0 {
		rt.DB = rc.DB
	}
	if !rt.TLS {
		rt.TLS = rc.TLS
	}
	if rt.Pool.Size == 0 {
		rt.Pool.Size = rc.Pool.Size
	}
	if rt.Pool.MinIdle == 0 {
		rt.Pool.MinIdle = rc.Pool.MinIdle
	}
	if rt.Pool.ReadTimeoutMs == 0 {
		rt.Pool.ReadTimeoutMs = rc.Pool.ReadTimeoutMs
	}
	if rt.Pool.WriteTimeoutMs == 0 {
		rt.Pool.WriteTimeoutMs = rc.Pool.WriteTimeoutMs
	}
	if rt.Pool.DialTimeoutMs == 0 {
		rt.Pool.DialTimeoutMs = rc.Pool.DialTimeoutMs
	}
	mode := rc.Mode
	if mode == "" {
		mode = "memory"
	}
	rtMode := rt.Mode
	if rtMode == "" {
		rtMode = mode
	}
	generalScene := rtredis.SceneConfig{
		Mode:         mode,
		Addr:         rc.Addr,
		Addrs:        rc.Addrs,
		Password:     rc.Password,
		DB:           rc.DB,
		TLS:          rc.TLS,
		PoolSize:     rc.Pool.Size,
		MinIdleConns: rc.Pool.MinIdle,
	}
	realtimeScene := rtredis.SceneConfig{
		Mode:         rtMode,
		Addr:         rt.Addr,
		Addrs:        rt.Addrs,
		Password:     rt.Password,
		DB:           rt.DB,
		TLS:          rt.TLS,
		PoolSize:     rt.Pool.Size,
		MinIdleConns: rt.Pool.MinIdle,
	}
	return platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  generalScene,
			"realtime": realtimeScene,
			"rec":      generalScene,
		},
		PrefixRoutes: rtredis.GeneratedPrefixRoutes(),
		DefaultScene: rtredis.GeneratedDefaultScene,
	})
}
