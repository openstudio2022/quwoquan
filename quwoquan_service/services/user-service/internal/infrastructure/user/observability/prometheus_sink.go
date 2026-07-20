// Package observability 提供 ProfileSubject 与 Persona rollout 对象指标的
// Prometheus 导出。domain 仅持有端口，具体 collector 只在 infrastructure 注册。
package observability

import (
	"github.com/prometheus/client_golang/prometheus"

	usertelemetry "quwoquan_service/services/user-service/internal/domain/user/telemetry"
)

var (
	profileSubjectPublicReadLatency = prometheus.NewHistogram(
		prometheus.HistogramOpts{
			Name:    "quwoquan_profile_subject_public_read_latency_ms",
			Help:    "Public profile subject read latency in milliseconds.",
			Buckets: prometheus.ExponentialBuckets(1, 2, 12),
		},
	)
	profileSubjectEvents = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "quwoquan_profile_subject_events_total",
			Help: "Profile subject visibility, attribution and sync-scope events.",
		},
		[]string{"metric"},
	)
	personaSwitchLatency = prometheus.NewHistogram(
		prometheus.HistogramOpts{
			Name:    "quwoquan_persona_switch_latency_ms",
			Help:    "Active persona switch latency in milliseconds.",
			Buckets: prometheus.ExponentialBuckets(1, 2, 12),
		},
	)
	personaRolloutEvents = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "quwoquan_persona_rollout_events_total",
			Help: "Persona attribution, public leakage and migration failure events.",
		},
		[]string{"metric"},
	)
)

func init() {
	prometheus.MustRegister(
		profileSubjectPublicReadLatency,
		profileSubjectEvents,
		personaSwitchLatency,
		personaRolloutEvents,
	)
}

type PrometheusSink struct{}

var (
	_ usertelemetry.ProfileSubjectMetricsSink = PrometheusSink{}
	_ usertelemetry.PersonaRolloutMetricsSink = PrometheusSink{}
)

func (PrometheusSink) ObserveProfileSubjectPublicReadLatency(
	milliseconds float64,
) {
	profileSubjectPublicReadLatency.Observe(milliseconds)
}

func (PrometheusSink) IncrementProfileSubjectCounter(metricName string) {
	switch metricName {
	case usertelemetry.MetricProfileSubjectVisibilityNotFoundCount,
		usertelemetry.MetricProfileSubjectSyncScopeSubmitCount:
		profileSubjectEvents.WithLabelValues(metricName).Inc()
	}
}

func (PrometheusSink) ObservePersonaSwitchLatency(milliseconds float64) {
	personaSwitchLatency.Observe(milliseconds)
}

func (PrometheusSink) IncrementPersonaRolloutCounter(metricName string) {
	switch metricName {
	case usertelemetry.MetricPersonaAttributionMismatchCount,
		usertelemetry.MetricPersonaPublicLeakageCount,
		usertelemetry.MetricPersonaMigrationFailedCount:
		personaRolloutEvents.WithLabelValues(metricName).Inc()
	}
}
