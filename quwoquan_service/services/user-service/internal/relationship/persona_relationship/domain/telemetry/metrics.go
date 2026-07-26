package telemetry

import (
	"sync"
	"time"
)

const (
	MetricCommandLatencyMs       = "persona_relationship_command_latency_ms"
	MetricDuplicateCommandCount  = "persona_relationship_duplicate_command_count"
	MetricBlockRejectionCount    = "persona_relationship_block_rejection_count"
	MetricCounterMismatchCount   = "persona_relationship_counter_mismatch_count"
	MetricCounterProjectionLagMs = "persona_relationship_counter_projection_lag_ms"
	MetricListLatencyMs          = "persona_relationship_list_latency_ms"
	MetricPageDriftCount         = "persona_relationship_page_drift_count"
	MetricFilterMismatchCount    = "persona_relationship_filter_mismatch_count"
	MetricCapabilityMismatch     = "persona_relationship_capability_mismatch_count"
)

// MetricsSink 是对象级指标的生产导出端口（R-OBJ-001：对象 metric 必须可在
// /metrics 聚合）。domain 只定义端口；Prometheus 实现位于 infrastructure，
// composition root 经 SetSink 一次性装配。缺席时仅保留 in-memory snapshot
// （测试与本地断言消费）。
type MetricsSink interface {
	ObserveCommandLatency(milliseconds float64)
	ObserveListLatency(milliseconds float64)
	ObserveCounterProjectionLag(milliseconds float64)
	IncrementCounter(metricName string)
}

type Metrics struct {
	mu                      sync.Mutex
	sink                    MetricsSink
	commandLatencyMs        float64
	duplicateCommandCount   float64
	blockRejectionCount     float64
	counterMismatchCount    float64
	counterProjectionLagMs  float64
	listLatencyMs           float64
	pageDriftCount          float64
	filterMismatchCount     float64
	capabilityMismatchCount float64
}

// SetSink 装配生产导出端；进程启动时调用一次。
func (m *Metrics) SetSink(sink MetricsSink) {
	if m == nil {
		return
	}
	m.mu.Lock()
	m.sink = sink
	m.mu.Unlock()
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
	m.counterProjectionLagMs = 0
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
	sink := m.sink
	m.mu.Unlock()
	if sink != nil {
		sink.ObserveCommandLatency(value)
	}
}

func (m *Metrics) RecordDuplicateCommand() {
	m.increment(&m.duplicateCommandCount, MetricDuplicateCommandCount)
}
func (m *Metrics) RecordBlockRejection() {
	m.increment(&m.blockRejectionCount, MetricBlockRejectionCount)
}
func (m *Metrics) RecordCounterMismatch() {
	m.increment(&m.counterMismatchCount, MetricCounterMismatchCount)
}
func (m *Metrics) RecordCounterProjectionLag(duration time.Duration) {
	if m == nil {
		return
	}
	value := float64(duration) / float64(time.Millisecond)
	if value <= 0 {
		value = 0.001
	}
	m.mu.Lock()
	m.counterProjectionLagMs = value
	sink := m.sink
	m.mu.Unlock()
	if sink != nil {
		sink.ObserveCounterProjectionLag(value)
	}
}
func (m *Metrics) RecordPageDrift() {
	m.increment(&m.pageDriftCount, MetricPageDriftCount)
}
func (m *Metrics) RecordFilterMismatch() {
	m.increment(&m.filterMismatchCount, MetricFilterMismatchCount)
}
func (m *Metrics) RecordCapabilityMismatch() {
	m.increment(&m.capabilityMismatchCount, MetricCapabilityMismatch)
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
	sink := m.sink
	m.mu.Unlock()
	if sink != nil {
		sink.ObserveListLatency(value)
	}
}

func (m *Metrics) Snapshot() map[string]float64 {
	if m == nil {
		return map[string]float64{}
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	return map[string]float64{
		MetricCommandLatencyMs:       m.commandLatencyMs,
		MetricDuplicateCommandCount:  m.duplicateCommandCount,
		MetricBlockRejectionCount:    m.blockRejectionCount,
		MetricCounterMismatchCount:   m.counterMismatchCount,
		MetricCounterProjectionLagMs: m.counterProjectionLagMs,
		MetricListLatencyMs:          m.listLatencyMs,
		MetricPageDriftCount:         m.pageDriftCount,
		MetricFilterMismatchCount:    m.filterMismatchCount,
		MetricCapabilityMismatch:     m.capabilityMismatchCount,
	}
}

func (m *Metrics) increment(target *float64, metricName string) {
	if m == nil {
		return
	}
	m.mu.Lock()
	(*target)++
	sink := m.sink
	m.mu.Unlock()
	if sink != nil {
		sink.IncrementCounter(metricName)
	}
}
