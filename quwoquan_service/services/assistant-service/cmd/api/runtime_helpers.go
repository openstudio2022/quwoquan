package bootstrap

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
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/runtimeconfig"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/runtimewiring"
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

func validateRuntimeConfigurationIdentity(cfg config, configVersion string) error {
	fileVersion := strings.TrimSpace(cfg.Config.Version)
	environmentVersion := strings.TrimSpace(configVersion)
	if environmentVersion != "" && fileVersion != "" && fileVersion != environmentVersion {
		return fmt.Errorf(
			"CONFIG_VERSION mismatch: env=%s file=%s",
			environmentVersion,
			fileVersion,
		)
	}
	return nil
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

func hostname() string {
	name, err := os.Hostname()
	if err != nil || strings.TrimSpace(name) == "" {
		return "local"
	}
	return name
}
