package provider

import (
	"errors"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	rerrors "quwoquan_service/runtime/errors"
)

type RatePolicy struct {
	RequestsPerSecond int
}

type fixedWindowRateGate struct {
	mu          sync.Mutex
	perSecond   int
	windowStart time.Time
	count       int
	now         func() time.Time
}

func newFixedWindowRateGate(policy RatePolicy) *fixedWindowRateGate {
	return &fixedWindowRateGate{
		perSecond: policy.RequestsPerSecond,
		now:       func() time.Time { return time.Now().UTC() },
	}
}

func (g *fixedWindowRateGate) allow() bool {
	if g == nil || g.perSecond <= 0 {
		return false
	}
	now := g.now()
	g.mu.Lock()
	defer g.mu.Unlock()
	if g.windowStart.IsZero() || now.Sub(g.windowStart) >= time.Second {
		g.windowStart = now
		g.count = 0
	}
	if g.count >= g.perSecond {
		return false
	}
	g.count++
	return true
}

var (
	publicProviderRequests = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "integration_public_provider_requests_total",
			Help: "Public Provider calls by capability, adapter and normalized outcome.",
		},
		[]string{"capability", "adapter", "outcome"},
	)
	publicProviderLatency = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "integration_public_provider_request_duration_seconds",
			Help:    "Public Provider request latency by capability and adapter.",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"capability", "adapter"},
	)
)

func init() {
	registerProviderCollector(publicProviderRequests)
	registerProviderCollector(publicProviderLatency)
}

func registerProviderCollector(collector prometheus.Collector) {
	if err := prometheus.Register(collector); err != nil {
		if _, ok := err.(prometheus.AlreadyRegisteredError); ok {
			return
		}
		panic(err)
	}
}

func observePublicProvider(
	capability string,
	adapter string,
	startedAt time.Time,
	err error,
) {
	outcome := "success"
	if err != nil {
		outcome = publicProviderOutcome(err)
	}
	publicProviderRequests.WithLabelValues(capability, adapter, outcome).Inc()
	publicProviderLatency.WithLabelValues(capability, adapter).
		Observe(time.Since(startedAt).Seconds())
}

func publicProviderOutcome(err error) string {
	var appErr *rerrors.AppError
	if !errors.As(err, &appErr) {
		return "failure"
	}
	switch appErr.SemanticReason {
	case "timeout":
		return "timeout"
	case "location_provider_rate_limited":
		return "rate_limited"
	case "location_provider_invalid_response":
		return "invalid_response"
	case "location_provider_unavailable":
		return "unavailable"
	default:
		return "failure"
	}
}
