package observability

import (
	"time"

	"github.com/prometheus/client_golang/prometheus"

	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/application"
)

type Metrics struct {
	decisions *prometheus.CounterVec
	duration  *prometheus.HistogramVec
}

var _ application.Observer = (*Metrics)(nil)

func NewMetrics(registerer prometheus.Registerer) *Metrics {
	if registerer == nil {
		registerer = prometheus.DefaultRegisterer
	}
	metrics := &Metrics{
		decisions: prometheus.NewCounterVec(
			prometheus.CounterOpts{
				Name: "api_edge_admission_decisions_total",
				Help: "Canonical edge admission decisions; labels are bounded ContractGraph/config enums.",
			},
			[]string{"environment", "operation", "outcome", "failure_policy"},
		),
		duration: prometheus.NewHistogramVec(
			prometheus.HistogramOpts{
				Name:    "api_edge_admission_duration_seconds",
				Help:    "Redis-backed edge admission latency by bounded outcome.",
				Buckets: []float64{0.001, 0.003, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25},
			},
			[]string{"environment", "outcome"},
		),
	}
	registerer.MustRegister(metrics.decisions, metrics.duration)
	return metrics
}

func (metrics *Metrics) RecordDecision(
	environment string,
	operation string,
	outcome string,
	failurePolicy string,
	elapsed time.Duration,
) {
	metrics.decisions.WithLabelValues(
		environment,
		operation,
		outcome,
		failurePolicy,
	).Inc()
	metrics.duration.WithLabelValues(environment, outcome).Observe(elapsed.Seconds())
}
