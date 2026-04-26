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

type PersonaRolloutMetrics struct {
	mu                       sync.Mutex
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
	defer m.mu.Unlock()
	m.switchLatencyMs = latencyMs
}

func (m *PersonaRolloutMetrics) RecordAttributionMismatch() {
	m.increment(&m.attributionMismatchCount)
}

func (m *PersonaRolloutMetrics) RecordPublicLeakage() {
	m.increment(&m.publicLeakageCount)
}

func (m *PersonaRolloutMetrics) RecordMigrationFailure() {
	m.increment(&m.migrationFailedCount)
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

func (m *PersonaRolloutMetrics) increment(target *float64) {
	if m == nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	*target = *target + 1
}
