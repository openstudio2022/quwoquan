package main

import (
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	rtgov "quwoquan_service/runtime/governance"
	rtredis "quwoquan_service/runtime/redis"
)

func providerAPIKey(cfg providerCfg) (string, error) {
	envKey := strings.TrimSpace(cfg.APIKeyEnv)
	if envKey == "" {
		return "", fmt.Errorf("provider api_key_env is required")
	}
	key := strings.TrimSpace(os.Getenv(envKey))
	if key == "" {
		return "", fmt.Errorf("provider api key env %s is empty", envKey)
	}
	return key, nil
}

func providerTimeout(ms int) time.Duration {
	if ms <= 0 {
		return 30 * time.Second
	}
	return time.Duration(ms) * time.Millisecond
}

func searchProviderTimeout(ms int) time.Duration {
	if ms <= 0 {
		return 8 * time.Second
	}
	timeout := time.Duration(ms) * time.Millisecond
	if timeout > 10*time.Second {
		return 10 * time.Second
	}
	return timeout
}

func searchHTTPClient(ms int) *http.Client {
	timeout := searchProviderTimeout(ms)
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.TLSHandshakeTimeout = timeout
	transport.ResponseHeaderTimeout = timeout
	return rtgov.WrapClientWithCB(
		&http.Client{Timeout: timeout, Transport: transport},
		rtgov.NewCircuitBreaker(5, 15*time.Second, slog.Default()),
	)
}

func requiresRealProvider(appEnv string) bool {
	return appEnv == "beta" || appEnv == "gamma" || appEnv == "prod"
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

func buildRedisRouter(cfg config) *rtredis.Router {
	generalScene := rtredis.SceneConfig{
		Mode:         fallbackMode(cfg.Redis.General.Mode, cfg.Redis.General.Addr, cfg.Redis.General.Addrs),
		Addr:         cfg.Redis.General.Addr,
		Addrs:        cfg.Redis.General.Addrs,
		Password:     cfg.Redis.General.Password,
		DB:           cfg.Redis.General.DB,
		TLS:          cfg.Redis.General.TLS,
		PoolSize:     cfg.Redis.General.Pool.Size,
		MinIdleConns: cfg.Redis.General.Pool.MinIdle,
	}
	return rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"rec": {
				Mode:         fallbackMode(cfg.Redis.Rec.Mode, cfg.Redis.Rec.Addr, cfg.Redis.Rec.Addrs),
				Addr:         cfg.Redis.Rec.Addr,
				Addrs:        cfg.Redis.Rec.Addrs,
				Password:     cfg.Redis.Rec.Password,
				DB:           cfg.Redis.Rec.DB,
				TLS:          cfg.Redis.Rec.TLS,
				PoolSize:     cfg.Redis.Rec.Pool.Size,
				MinIdleConns: cfg.Redis.Rec.Pool.MinIdle,
			},
			"general":  generalScene,
			"realtime": generalScene,
		},
		PrefixRoutes: rtredis.GeneratedPrefixRoutes(),
		DefaultScene: rtredis.GeneratedDefaultScene,
	})
}

func fallbackMode(mode string, addr string, addrs []string) string {
	if strings.TrimSpace(mode) != "" && (strings.TrimSpace(addr) != "" || len(addrs) > 0) {
		return mode
	}
	return "memory"
}

func scenarioSeedRefsFromEnv() []string {
	raw := strings.TrimSpace(os.Getenv("ASSISTANT_SCENARIO_SEED_REFS"))
	if raw == "" {
		return nil
	}
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part != "" {
			out = append(out, part)
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

func assistantShutdownTimeout() time.Duration {
	raw := strings.TrimSpace(os.Getenv("ASSISTANT_SHUTDOWN_TIMEOUT_SECONDS"))
	if raw == "" {
		return 10 * time.Second
	}
	seconds, err := strconv.Atoi(raw)
	if err != nil || seconds <= 0 {
		log.Printf("WARN: invalid ASSISTANT_SHUTDOWN_TIMEOUT_SECONDS=%q; using 10s", raw)
		return 10 * time.Second
	}
	return time.Duration(seconds) * time.Second
}

func assistantHTTPWriteTimeout() time.Duration {
	raw := strings.TrimSpace(os.Getenv("ASSISTANT_HTTP_WRITE_TIMEOUT_SECONDS"))
	if raw == "" {
		return 180 * time.Second
	}
	seconds, err := strconv.Atoi(raw)
	if err != nil || seconds <= 0 {
		log.Printf("WARN: invalid ASSISTANT_HTTP_WRITE_TIMEOUT_SECONDS=%q; using 180s", raw)
		return 180 * time.Second
	}
	return time.Duration(seconds) * time.Second
}

func hostname() string {
	name, err := os.Hostname()
	if err != nil || strings.TrimSpace(name) == "" {
		return "local"
	}
	return name
}
