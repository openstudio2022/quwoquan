package telemetry

import (
	"sync"
	"time"
)

const (
	MetricProfileSubjectPublicReadLatencyMs     = "profile_subject_public_read_latency_ms"
	MetricProfileSubjectVisibilityNotFoundCount = "profile_subject_visibility_not_found_count"
	MetricProfileSubjectSyncScopeSubmitCount    = "profile_subject_sync_scope_submit_count"
)

type ProfileSubjectMetricsSink interface {
	ObserveProfileSubjectPublicReadLatency(milliseconds float64)
	IncrementProfileSubjectCounter(metricName string)
}

type ProfileSubjectMetrics struct {
	mu                      sync.Mutex
	sink                    ProfileSubjectMetricsSink
	publicReadLatencyMs     float64
	visibilityNotFoundCount float64
	syncScopeSubmitCount    float64
}

var defaultProfileSubjectMetrics = &ProfileSubjectMetrics{}

func Collector() *ProfileSubjectMetrics {
	return defaultProfileSubjectMetrics
}

func Reset() {
	defaultProfileSubjectMetrics.Reset()
}

func (m *ProfileSubjectMetrics) SetSink(sink ProfileSubjectMetricsSink) {
	if m == nil {
		return
	}
	m.mu.Lock()
	m.sink = sink
	m.mu.Unlock()
}

func (m *ProfileSubjectMetrics) Reset() {
	if m == nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.publicReadLatencyMs = 0
	m.visibilityNotFoundCount = 0
	m.syncScopeSubmitCount = 0
}

func (m *ProfileSubjectMetrics) RecordPublicRead(duration time.Duration) {
	if m == nil {
		return
	}
	latencyMs := float64(duration) / float64(time.Millisecond)
	if latencyMs <= 0 {
		latencyMs = 0.001
	}
	m.mu.Lock()
	m.publicReadLatencyMs = latencyMs
	sink := m.sink
	m.mu.Unlock()
	if sink != nil {
		sink.ObserveProfileSubjectPublicReadLatency(latencyMs)
	}
}

func (m *ProfileSubjectMetrics) RecordVisibilityNotFound() {
	m.increment(
		&m.visibilityNotFoundCount,
		MetricProfileSubjectVisibilityNotFoundCount,
	)
}

func (m *ProfileSubjectMetrics) RecordSyncScopeSubmit() {
	m.increment(
		&m.syncScopeSubmitCount,
		MetricProfileSubjectSyncScopeSubmitCount,
	)
}

func (m *ProfileSubjectMetrics) increment(target *float64, metricName string) {
	if m == nil {
		return
	}
	m.mu.Lock()
	(*target)++
	sink := m.sink
	m.mu.Unlock()
	if sink != nil {
		sink.IncrementProfileSubjectCounter(metricName)
	}
}

func (m *ProfileSubjectMetrics) Snapshot() map[string]float64 {
	if m == nil {
		return map[string]float64{}
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	return map[string]float64{
		MetricProfileSubjectPublicReadLatencyMs:     m.publicReadLatencyMs,
		MetricProfileSubjectVisibilityNotFoundCount: m.visibilityNotFoundCount,
		MetricProfileSubjectSyncScopeSubmitCount:    m.syncScopeSubmitCount,
	}
}
