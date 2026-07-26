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
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/runtimeconfig"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/runtimewiring"
)

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

func buildRedisRouter(cfg config) (*rtredis.Router, error) {
	return runtimewiring.BuildRedisRouter(cfg)
}

func isValidAppEnv(env string) bool {
	return runtimeconfig.IsValidAppEnv(env)
}

func requiresConfigVersion(env string) bool {
	return runtimeconfig.RequiresConfigVersion(env)
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
