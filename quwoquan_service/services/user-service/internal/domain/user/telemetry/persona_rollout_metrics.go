package telemetry

import (
	"sync"
	"time"
)

const (
	MetricPersonaSwitchLatencyMs          = "persona_switch_latency_ms"
	MetricPersonaAttributionMismatchCount = "persona_attribution_mismatch_count"
	MetricPersonaPublicLeakageCount       = "persona_public_leakage_count"
	MetricPersonaMigrationFailedCount     = "persona_migration_failed_count"
)

type PersonaRolloutMetricsSink interface {
	ObservePersonaSwitchLatency(milliseconds float64)
	IncrementPersonaRolloutCounter(metricName string)
}

type PersonaRolloutMetrics struct {
	mu                       sync.Mutex
	sink                     PersonaRolloutMetricsSink
	switchLatencyMs          float64
	attributionMismatchCount float64
	publicLeakageCount       float64
	migrationFailedCount     float64
}

var defaultPersonaRolloutMetrics = &PersonaRolloutMetrics{}

func RolloutCollector() *PersonaRolloutMetrics {
	return defaultPersonaRolloutMetrics
}

func ResetRollout() {
	defaultPersonaRolloutMetrics.Reset()
}

func (m *PersonaRolloutMetrics) SetSink(sink PersonaRolloutMetricsSink) {
	if m == nil {
		return
	}
	m.mu.Lock()
	m.sink = sink
	m.mu.Unlock()
}

func (m *PersonaRolloutMetrics) Reset() {
	if m == nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.switchLatencyMs = 0
	m.attributionMismatchCount = 0
	m.publicLeakageCount = 0
	m.migrationFailedCount = 0
}

func (m *PersonaRolloutMetrics) RecordSwitchLatency(duration time.Duration) {
	if m == nil {
		return
	}
	latencyMs := float64(duration) / float64(time.Millisecond)
	if latencyMs <= 0 {
		latencyMs = 0.001
	}
	m.mu.Lock()
	m.switchLatencyMs = latencyMs
	sink := m.sink
	m.mu.Unlock()
	if sink != nil {
		sink.ObservePersonaSwitchLatency(latencyMs)
	}
}

func (m *PersonaRolloutMetrics) RecordAttributionMismatch() {
	m.increment(
		&m.attributionMismatchCount,
		MetricPersonaAttributionMismatchCount,
	)
}

func (m *PersonaRolloutMetrics) RecordPublicLeakage() {
	m.increment(&m.publicLeakageCount, MetricPersonaPublicLeakageCount)
}

func (m *PersonaRolloutMetrics) RecordMigrationFailure() {
	m.increment(&m.migrationFailedCount, MetricPersonaMigrationFailedCount)
}

func (m *PersonaRolloutMetrics) Snapshot() map[string]float64 {
	if m == nil {
		return map[string]float64{}
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	return map[string]float64{
		MetricPersonaSwitchLatencyMs:          m.switchLatencyMs,
		MetricPersonaAttributionMismatchCount: m.attributionMismatchCount,
		MetricPersonaPublicLeakageCount:       m.publicLeakageCount,
		MetricPersonaMigrationFailedCount:     m.migrationFailedCount,
	}
}

func (m *PersonaRolloutMetrics) increment(target *float64, metricName string) {
	if m == nil {
		return
	}
	m.mu.Lock()
	*target = *target + 1
	sink := m.sink
	m.mu.Unlock()
	if sink != nil {
		sink.IncrementPersonaRolloutCounter(metricName)
	}
}
