// Package observability 提供 PersonaRelationship 对象级指标的 Prometheus 导出
// （R-OBJ-001：关注/拉黑黄金指标必须在 /metrics 可聚合、可告警）。
package observability

import (
	"github.com/prometheus/client_golang/prometheus"

	reltelemetry "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/telemetry"
)

var (
	relationshipCommandLatency = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "quwoquan_persona_relationship_command_latency_ms",
		Help:    "Follow/unfollow/block/unblock command latency in milliseconds.",
		Buckets: prometheus.ExponentialBuckets(1, 2, 12),
	})

	relationshipListLatency = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "quwoquan_persona_relationship_list_latency_ms",
		Help:    "Following/followers/blocked list query latency in milliseconds.",
		Buckets: prometheus.ExponentialBuckets(1, 2, 12),
	})

	relationshipCounterProjectionLag = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "quwoquan_persona_relationship_counter_projection_lag_ms",
		Help:    "Lag from committed relationship event to derived profile counter projection.",
		Buckets: prometheus.ExponentialBuckets(10, 2, 12),
	})

	relationshipEvents = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "quwoquan_persona_relationship_events_total",
		Help: "PersonaRelationship object events by metric name (duplicate command, block rejection, counter mismatch, page drift, filter mismatch, capability mismatch).",
	}, []string{"metric"})
)

func init() {
	prometheus.MustRegister(
		relationshipCommandLatency,
		relationshipListLatency,
		relationshipCounterProjectionLag,
		relationshipEvents,
	)
}

// PrometheusSink 实现 domain telemetry.MetricsSink。
type PrometheusSink struct{}

var _ reltelemetry.MetricsSink = PrometheusSink{}

func (PrometheusSink) ObserveCommandLatency(milliseconds float64) {
	relationshipCommandLatency.Observe(milliseconds)
}

func (PrometheusSink) ObserveListLatency(milliseconds float64) {
	relationshipListLatency.Observe(milliseconds)
}

func (PrometheusSink) ObserveCounterProjectionLag(milliseconds float64) {
	relationshipCounterProjectionLag.Observe(milliseconds)
}

func (PrometheusSink) IncrementCounter(metricName string) {
	relationshipEvents.WithLabelValues(metricName).Inc()
}
