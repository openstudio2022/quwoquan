package bootstrap

import (
	"log"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	rtgov "quwoquan_service/runtime/governance"
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
