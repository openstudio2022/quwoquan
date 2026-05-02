package telemetry

import (
	"sync"
	"time"
)

const (
	MetricFollowCommandLatencyMs         = "follow_command_latency_ms"
	MetricFollowDuplicateRequestCount    = "follow_duplicate_request_count"
	MetricFollowBlockRejectionCount      = "follow_block_rejection_count"
	MetricFollowCounterMismatchCount     = "follow_counter_mismatch_count"
	MetricFollowCurrentEdgeReadCount     = "follow_current_edge_read_count"
	MetricGraphListLatencyMs             = "graph_list_latency_ms"
	MetricGraphPageDriftCount            = "graph_page_drift_count"
	MetricGraphFilterMismatchCount       = "graph_filter_mismatch_count"
	MetricRelationshipCapabilityMismatch = "relationship_capability_mismatch_count"
	MetricGraphCurrentEdgeReadCount      = "graph_current_edge_read_count"
)

type GraphMetrics struct {
	mu                                  sync.Mutex
	followCommandLatencyMs              float64
	followDuplicateRequestCount         float64
	followBlockRejectionCount           float64
	followCounterMismatchCount          float64
	followCurrentEdgeReadCount          float64
	graphListLatencyMs                  float64
	graphPageDriftCount                 float64
	graphFilterMismatchCount            float64
	relationshipCapabilityMismatchCount float64
	graphCurrentEdgeReadCount           float64
}

var defaultGraphMetrics = &GraphMetrics{}

func Collector() *GraphMetrics {
	return defaultGraphMetrics
}

func Reset() {
	defaultGraphMetrics.Reset()
}

func (m *GraphMetrics) Reset() {
	if m == nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.followCommandLatencyMs = 0
	m.followDuplicateRequestCount = 0
	m.followBlockRejectionCount = 0
	m.followCounterMismatchCount = 0
	m.followCurrentEdgeReadCount = 0
	m.graphListLatencyMs = 0
	m.graphPageDriftCount = 0
	m.graphFilterMismatchCount = 0
	m.relationshipCapabilityMismatchCount = 0
	m.graphCurrentEdgeReadCount = 0
}

func (m *GraphMetrics) RecordFollowCommandLatency(duration time.Duration) {
	if m == nil {
		return
	}
	latencyMs := float64(duration) / float64(time.Millisecond)
	if latencyMs <= 0 {
		latencyMs = 0.001
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.followCommandLatencyMs = latencyMs
}

func (m *GraphMetrics) RecordDuplicateFollow() {
	m.increment(&m.followDuplicateRequestCount)
}

func (m *GraphMetrics) RecordBlockRejection() {
	m.increment(&m.followBlockRejectionCount)
}

func (m *GraphMetrics) RecordCounterMismatch() {
	m.increment(&m.followCounterMismatchCount)
}

func (m *GraphMetrics) RecordCurrentFollowRead() {
	m.increment(&m.followCurrentEdgeReadCount)
}

func (m *GraphMetrics) RecordGraphListLatency(duration time.Duration) {
	if m == nil {
		return
	}
	latencyMs := float64(duration) / float64(time.Millisecond)
	if latencyMs <= 0 {
		latencyMs = 0.001
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.graphListLatencyMs = latencyMs
}

func (m *GraphMetrics) RecordGraphPageDrift() {
	m.increment(&m.graphPageDriftCount)
}

func (m *GraphMetrics) RecordGraphFilterMismatch() {
	m.increment(&m.graphFilterMismatchCount)
}

func (m *GraphMetrics) RecordRelationshipCapabilityMismatch() {
	m.increment(&m.relationshipCapabilityMismatchCount)
}

func (m *GraphMetrics) RecordCurrentGraphRead() {
	m.increment(&m.graphCurrentEdgeReadCount)
}

func (m *GraphMetrics) Snapshot() map[string]float64 {
	if m == nil {
		return map[string]float64{}
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	return map[string]float64{
		MetricFollowCommandLatencyMs:         m.followCommandLatencyMs,
		MetricFollowDuplicateRequestCount:    m.followDuplicateRequestCount,
		MetricFollowBlockRejectionCount:      m.followBlockRejectionCount,
		MetricFollowCounterMismatchCount:     m.followCounterMismatchCount,
		MetricFollowCurrentEdgeReadCount:     m.followCurrentEdgeReadCount,
		MetricGraphListLatencyMs:             m.graphListLatencyMs,
		MetricGraphPageDriftCount:            m.graphPageDriftCount,
		MetricGraphFilterMismatchCount:       m.graphFilterMismatchCount,
		MetricRelationshipCapabilityMismatch: m.relationshipCapabilityMismatchCount,
		MetricGraphCurrentEdgeReadCount:      m.graphCurrentEdgeReadCount,
	}
}

func (m *GraphMetrics) increment(target *float64) {
	if m == nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	*target = *target + 1
}
