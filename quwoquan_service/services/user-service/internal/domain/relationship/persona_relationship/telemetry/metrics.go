package telemetry

import (
	"sync"
	"time"
)

const (
	MetricCommandLatencyMs      = "persona_relationship_command_latency_ms"
	MetricDuplicateCommandCount = "persona_relationship_duplicate_command_count"
	MetricBlockRejectionCount   = "persona_relationship_block_rejection_count"
	MetricCounterMismatchCount  = "persona_relationship_counter_mismatch_count"
	MetricListLatencyMs         = "persona_relationship_list_latency_ms"
	MetricPageDriftCount        = "persona_relationship_page_drift_count"
	MetricFilterMismatchCount   = "persona_relationship_filter_mismatch_count"
	MetricCapabilityMismatch    = "persona_relationship_capability_mismatch_count"
)

type Metrics struct {
	mu                      sync.Mutex
	commandLatencyMs        float64
	duplicateCommandCount   float64
	blockRejectionCount     float64
	counterMismatchCount    float64
	listLatencyMs           float64
	pageDriftCount          float64
	filterMismatchCount     float64
	capabilityMismatchCount float64
}

var defaultMetrics = &Metrics{}

func Collector() *Metrics { return defaultMetrics }
func Reset()              { defaultMetrics.Reset() }

func (m *Metrics) Reset() {
	if m == nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.commandLatencyMs = 0
	m.duplicateCommandCount = 0
	m.blockRejectionCount = 0
	m.counterMismatchCount = 0
	m.listLatencyMs = 0
	m.pageDriftCount = 0
	m.filterMismatchCount = 0
	m.capabilityMismatchCount = 0
}

func (m *Metrics) RecordCommandLatency(duration time.Duration) {
	if m == nil {
		return
	}
	value := float64(duration) / float64(time.Millisecond)
	if value <= 0 {
		value = 0.001
	}
	m.mu.Lock()
	m.commandLatencyMs = value
	m.mu.Unlock()
}

func (m *Metrics) RecordDuplicateCommand() { m.increment(&m.duplicateCommandCount) }
func (m *Metrics) RecordBlockRejection()   { m.increment(&m.blockRejectionCount) }
func (m *Metrics) RecordCounterMismatch()  { m.increment(&m.counterMismatchCount) }
func (m *Metrics) RecordPageDrift()        { m.increment(&m.pageDriftCount) }
func (m *Metrics) RecordFilterMismatch()   { m.increment(&m.filterMismatchCount) }
func (m *Metrics) RecordCapabilityMismatch() {
	m.increment(&m.capabilityMismatchCount)
}
func (m *Metrics) RecordListLatency(duration time.Duration) {
	if m == nil {
		return
	}
	value := float64(duration) / float64(time.Millisecond)
	if value <= 0 {
		value = 0.001
	}
	m.mu.Lock()
	m.listLatencyMs = value
	m.mu.Unlock()
}

func (m *Metrics) Snapshot() map[string]float64 {
	if m == nil {
		return map[string]float64{}
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	return map[string]float64{
		MetricCommandLatencyMs:      m.commandLatencyMs,
		MetricDuplicateCommandCount: m.duplicateCommandCount,
		MetricBlockRejectionCount:   m.blockRejectionCount,
		MetricCounterMismatchCount:  m.counterMismatchCount,
		MetricListLatencyMs:         m.listLatencyMs,
		MetricPageDriftCount:        m.pageDriftCount,
		MetricFilterMismatchCount:   m.filterMismatchCount,
		MetricCapabilityMismatch:    m.capabilityMismatchCount,
	}
}

func (m *Metrics) increment(target *float64) {
	if m == nil {
		return
	}
	m.mu.Lock()
	(*target)++
	m.mu.Unlock()
}
