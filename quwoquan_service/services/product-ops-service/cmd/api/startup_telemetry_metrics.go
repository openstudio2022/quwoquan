package main

import (
	"sync"

	"github.com/prometheus/client_golang/prometheus"
	eventrecordhttp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/adapters/inbound/http"
)

var (
	startupTelemetryMetricsOnce sync.Once
	startupPhaseTotal           *prometheus.CounterVec
	startupPhaseDuration        *prometheus.HistogramVec
)

func registerStartupTelemetryMetrics() {
	startupTelemetryMetricsOnce.Do(func() {
		startupPhaseTotal = prometheus.NewCounterVec(
			prometheus.CounterOpts{
				Name: "ops_startup_phase_total",
				Help: "Accepted restricted startup telemetry phases.",
			},
			[]string{"phase", "outcome", "platform", "runtime_env", "recovery_surface"},
		)
		startupPhaseDuration = prometheus.NewHistogramVec(
			prometheus.HistogramOpts{
				Name:    "ops_startup_phase_duration_seconds",
				Help:    "Accepted startup phase durations in seconds.",
				Buckets: []float64{0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 3, 6, 10, 30},
			},
			[]string{"phase", "outcome", "platform", "runtime_env", "recovery_surface"},
		)
		if err := prometheus.Register(startupPhaseTotal); err != nil {
			if registered, ok := err.(prometheus.AlreadyRegisteredError); ok {
				startupPhaseTotal, _ = registered.ExistingCollector.(*prometheus.CounterVec)
			}
		}
		if err := prometheus.Register(startupPhaseDuration); err != nil {
			if registered, ok := err.(prometheus.AlreadyRegisteredError); ok {
				startupPhaseDuration, _ = registered.ExistingCollector.(*prometheus.HistogramVec)
			}
		}
	})
}

func recordStartupTelemetryMetrics(event eventrecordhttp.StartupTelemetryEventInput) {
	registerStartupTelemetryMetrics()
	labels := prometheus.Labels{
		"phase":            event.Phase,
		"outcome":          event.Outcome,
		"platform":         event.Platform,
		"runtime_env":      event.RuntimeEnv,
		"recovery_surface": event.RecoverySurface,
	}
	startupPhaseTotal.With(labels).Inc()
	startupPhaseDuration.With(labels).Observe(float64(event.PhaseDurationMs) / 1000)
}
