package runtimesync

import (
	"sync/atomic"
	"time"
)

const (
	metricSyncAppendTotal      = "quwoquan_runtime_media_sync_append_total"
	metricSyncAppendBatchTotal = "quwoquan_runtime_media_sync_append_batch_total"
	metricSyncPullTotal        = "quwoquan_runtime_media_sync_pull_total"
	metricSyncPullDurationMS   = "quwoquan_runtime_media_sync_pull_duration_ms"
	metricSyncRequiresResync   = "quwoquan_runtime_media_sync_requires_resync_total"
	metricSyncStoredPatchKeys  = "quwoquan_runtime_media_sync_stored_patch_keys"
)

type MetricsCollector struct {
	appendTotal         atomic.Int64
	appendBatchTotal    atomic.Int64
	pullTotal           atomic.Int64
	pullDurationTotalNs atomic.Int64
	requiresResyncTotal atomic.Int64
	storedPatchKeys     atomic.Int64
}

func NewMetricsCollector() *MetricsCollector {
	return &MetricsCollector{}
}

func (mc *MetricsCollector) RecordAppend(storedPatches int) {
	if mc == nil {
		return
	}
	mc.appendTotal.Add(1)
	mc.storedPatchKeys.Add(int64(storedPatches))
}

func (mc *MetricsCollector) RecordAppendBatch(batchSize int, storedPatches int) {
	if mc == nil {
		return
	}
	mc.appendBatchTotal.Add(1)
	if batchSize <= 0 {
		return
	}
	mc.storedPatchKeys.Add(int64(storedPatches))
}

func (mc *MetricsCollector) RecordPull(duration time.Duration, requiresResync bool) {
	if mc == nil {
		return
	}
	mc.pullTotal.Add(1)
	mc.pullDurationTotalNs.Add(duration.Nanoseconds())
	if requiresResync {
		mc.requiresResyncTotal.Add(1)
	}
}

func (mc *MetricsCollector) Snapshot() map[string]float64 {
	if mc == nil {
		return map[string]float64{}
	}
	pullTotal := mc.pullTotal.Load()
	avgPullDurationMs := 0.0
	if pullTotal > 0 {
		avgPullDurationMs = float64(mc.pullDurationTotalNs.Load()) / float64(pullTotal) / 1e6
	}
	return map[string]float64{
		metricSyncAppendTotal:      float64(mc.appendTotal.Load()),
		metricSyncAppendBatchTotal: float64(mc.appendBatchTotal.Load()),
		metricSyncPullTotal:        float64(pullTotal),
		metricSyncPullDurationMS:   avgPullDurationMs,
		metricSyncRequiresResync:   float64(mc.requiresResyncTotal.Load()),
		metricSyncStoredPatchKeys:  float64(mc.storedPatchKeys.Load()),
	}
}
