package telemetry

import (
	"sync"
	"time"
)

const (
	MetricProfileSubjectPublicReadLatencyMs      = "profile_subject_public_read_latency_ms"
	MetricProfileSubjectVisibilityNotFoundCount  = "profile_subject_visibility_not_found_count"
	MetricRetiredSubjectAttributionFallbackCount = "retired_subject_attribution_fallback_count"
	MetricProfileSubjectSyncScopeSubmitCount     = "profile_subject_sync_scope_submit_count"
)

type ProfileSubjectMetrics struct {
	mu                              sync.Mutex
	publicReadLatencyMs             float64
	visibilityNotFoundCount         float64
	retiredAttributionFallbackCount float64
	syncScopeSubmitCount            float64
}

var defaultProfileSubjectMetrics = &ProfileSubjectMetrics{}

func Collector() *ProfileSubjectMetrics {
	return defaultProfileSubjectMetrics
}

func Reset() {
	defaultProfileSubjectMetrics.Reset()
}

func (m *ProfileSubjectMetrics) Reset() {
	if m == nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.publicReadLatencyMs = 0
	m.visibilityNotFoundCount = 0
	m.retiredAttributionFallbackCount = 0
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
	defer m.mu.Unlock()
	m.publicReadLatencyMs = latencyMs
}

func (m *ProfileSubjectMetrics) RecordVisibilityNotFound() {
	if m == nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.visibilityNotFoundCount++
}

func (m *ProfileSubjectMetrics) RecordRetiredAttributionFallback() {
	if m == nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.retiredAttributionFallbackCount++
}

func (m *ProfileSubjectMetrics) RecordSyncScopeSubmit() {
	if m == nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.syncScopeSubmitCount++
}

func (m *ProfileSubjectMetrics) Snapshot() map[string]float64 {
	if m == nil {
		return map[string]float64{}
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	return map[string]float64{
		MetricProfileSubjectPublicReadLatencyMs:      m.publicReadLatencyMs,
		MetricProfileSubjectVisibilityNotFoundCount:  m.visibilityNotFoundCount,
		MetricRetiredSubjectAttributionFallbackCount: m.retiredAttributionFallbackCount,
		MetricProfileSubjectSyncScopeSubmitCount:     m.syncScopeSubmitCount,
	}
}
