package observability

import (
	"fmt"

	"github.com/prometheus/client_golang/prometheus"
)

var startupTelemetryMetricLabels = []string{
	"phase",
	"outcome",
	"platform",
	"runtime_env",
	"recovery_surface",
	"recovery_lifecycle",
	"recovery_mount",
}

// StartupTelemetryObservation contains only the bounded dimensions admitted to
// the startup metrics projection. Recovery phase and action deliberately stay
// out of Prometheus labels and remain available only in the diagnostic store.
type StartupTelemetryObservation struct {
	Phase             string
	Outcome           string
	Platform          string
	RuntimeEnv        string
	RecoverySurface   string
	RecoveryLifecycle string
	RecoveryMount     string
	PhaseDurationMS   int
}

// StartupTelemetryMetrics owns the event_record Prometheus projection. A
// caller-supplied registerer keeps object tests isolated from process globals.
type StartupTelemetryMetrics struct {
	phaseTotal    *prometheus.CounterVec
	phaseDuration *prometheus.HistogramVec
}

func NewStartupTelemetryMetrics(registerer prometheus.Registerer) (*StartupTelemetryMetrics, error) {
	if registerer == nil {
		return nil, fmt.Errorf("startup telemetry metrics registerer is required")
	}

	phaseTotal, err := registerCounterVec(
		registerer,
		prometheus.NewCounterVec(
			prometheus.CounterOpts{
				Name: "ops_startup_phase_total",
				Help: "Accepted restricted startup telemetry phases.",
			},
			startupTelemetryMetricLabels,
		),
	)
	if err != nil {
		return nil, err
	}
	phaseDuration, err := registerHistogramVec(
		registerer,
		prometheus.NewHistogramVec(
			prometheus.HistogramOpts{
				Name:    "ops_startup_phase_duration_seconds",
				Help:    "Accepted startup phase durations in seconds.",
				Buckets: []float64{0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 3, 6, 10, 30},
			},
			startupTelemetryMetricLabels,
		),
	)
	if err != nil {
		return nil, err
	}
	return &StartupTelemetryMetrics{
		phaseTotal:    phaseTotal,
		phaseDuration: phaseDuration,
	}, nil
}

func (metrics *StartupTelemetryMetrics) Observe(observation StartupTelemetryObservation) {
	labels := prometheus.Labels{
		"phase":              observation.Phase,
		"outcome":            observation.Outcome,
		"platform":           observation.Platform,
		"runtime_env":        observation.RuntimeEnv,
		"recovery_surface":   observation.RecoverySurface,
		"recovery_lifecycle": observation.RecoveryLifecycle,
		"recovery_mount":     observation.RecoveryMount,
	}
	metrics.phaseTotal.With(labels).Inc()
	metrics.phaseDuration.With(labels).Observe(float64(observation.PhaseDurationMS) / 1000)
}

func registerCounterVec(
	registerer prometheus.Registerer,
	candidate *prometheus.CounterVec,
) (*prometheus.CounterVec, error) {
	if err := registerer.Register(candidate); err != nil {
		registered, ok := err.(prometheus.AlreadyRegisteredError)
		if !ok {
			return nil, fmt.Errorf("register startup phase counter: %w", err)
		}
		existing, ok := registered.ExistingCollector.(*prometheus.CounterVec)
		if !ok {
			return nil, fmt.Errorf("registered startup phase counter has unexpected type %T", registered.ExistingCollector)
		}
		return existing, nil
	}
	return candidate, nil
}

func registerHistogramVec(
	registerer prometheus.Registerer,
	candidate *prometheus.HistogramVec,
) (*prometheus.HistogramVec, error) {
	if err := registerer.Register(candidate); err != nil {
		registered, ok := err.(prometheus.AlreadyRegisteredError)
		if !ok {
			return nil, fmt.Errorf("register startup phase duration: %w", err)
		}
		existing, ok := registered.ExistingCollector.(*prometheus.HistogramVec)
		if !ok {
			return nil, fmt.Errorf("registered startup phase duration has unexpected type %T", registered.ExistingCollector)
		}
		return existing, nil
	}
	return candidate, nil
}
