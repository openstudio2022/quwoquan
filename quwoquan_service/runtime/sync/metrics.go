package runtimesync

import (
	"sync/atomic"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

const (
	metricSyncAppendTotal      = "quwoquan_runtime_media_sync_append_total"
	metricSyncAppendBatchTotal = "quwoquan_runtime_media_sync_append_batch_total"
	metricSyncPullTotal        = "quwoquan_runtime_media_sync_pull_total"
	metricSyncPullDurationMS   = "quwoquan_runtime_media_sync_pull_duration_ms"
	metricSyncRequiresResync   = "quwoquan_runtime_media_sync_requires_resync_total"
	metricSyncStoredPatchKeys  = "quwoquan_runtime_media_sync_stored_patch_keys"
	metricSyncHintToPullMS     = "quwoquan_runtime_media_sync_hint_to_pull_delay_ms"
	metricSyncFanoutTotal      = "quwoquan_runtime_media_sync_patch_fanout_total"
	metricSyncFanoutFailures   = "quwoquan_runtime_media_sync_patch_fanout_failure_total"
	metricSyncFanoutFailRatio  = "quwoquan_runtime_media_sync_patch_fanout_failure_ratio"
)

var (
	promSyncAppendTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: metricSyncAppendTotal,
		Help: "Total single-user durable sync patch appends.",
	})
	promSyncAppendBatchTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: metricSyncAppendBatchTotal,
		Help: "Total durable sync patch batch appends.",
	})
	promSyncPullTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: metricSyncPullTotal,
		Help: "Total durable sync patch pulls.",
	})
	promSyncPullDurationMS = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    metricSyncPullDurationMS,
		Help:    "Durable sync pull processing duration in milliseconds.",
		Buckets: []float64{1, 2.5, 5, 10, 25, 50, 100, 250, 500, 1000},
	})
	promSyncRequiresResync = promauto.NewCounter(prometheus.CounterOpts{
		Name: metricSyncRequiresResync,
		Help: "Total sync pulls requiring a full resync because of a patch gap.",
	})
	promSyncStoredPatchKeys = promauto.NewCounter(prometheus.CounterOpts{
		Name: metricSyncStoredPatchKeys,
		Help: "Total durable sync patch keys stored.",
	})
	promSyncHintToPullMS = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    metricSyncHintToPullMS,
		Help:    "Delay from the newest returned patch occurrence to client pull in milliseconds.",
		Buckets: []float64{10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000},
	})
	promSyncFanoutTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: metricSyncFanoutTotal,
		Help: "Total realtime sync hint fanout attempts by result.",
	}, []string{"result"})
)

type MetricsCollector struct {
	appendTotal         atomic.Int64
	appendBatchTotal    atomic.Int64
	pullTotal           atomic.Int64
	pullDurationTotalNs atomic.Int64
	requiresResyncTotal atomic.Int64
	storedPatchKeys     atomic.Int64
	hintToPullTotalNs   atomic.Int64
	hintToPullCount     atomic.Int64
	fanoutTotal         atomic.Int64
	fanoutFailures      atomic.Int64
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
	promSyncAppendTotal.Inc()
	promSyncStoredPatchKeys.Add(float64(storedPatches))
}

func (mc *MetricsCollector) RecordAppendBatch(batchSize int, storedPatches int) {
	if mc == nil {
		return
	}
	mc.appendBatchTotal.Add(1)
	promSyncAppendBatchTotal.Inc()
	if batchSize <= 0 {
		return
	}
	mc.storedPatchKeys.Add(int64(storedPatches))
	promSyncStoredPatchKeys.Add(float64(storedPatches))
}

func (mc *MetricsCollector) RecordPull(duration time.Duration, requiresResync bool) {
	if mc == nil {
		return
	}
	mc.pullTotal.Add(1)
	mc.pullDurationTotalNs.Add(duration.Nanoseconds())
	promSyncPullTotal.Inc()
	promSyncPullDurationMS.Observe(float64(duration.Nanoseconds()) / 1e6)
	if requiresResync {
		mc.requiresResyncTotal.Add(1)
		promSyncRequiresResync.Inc()
	}
}

func (mc *MetricsCollector) RecordHintToPullDelay(delay time.Duration) {
	if mc == nil || delay < 0 {
		return
	}
	mc.hintToPullCount.Add(1)
	mc.hintToPullTotalNs.Add(delay.Nanoseconds())
	promSyncHintToPullMS.Observe(float64(delay.Nanoseconds()) / 1e6)
}

func (mc *MetricsCollector) RecordPatchFanout(err error) {
	if mc == nil {
		return
	}
	mc.fanoutTotal.Add(1)
	result := "success"
	if err != nil {
		result = "failure"
		mc.fanoutFailures.Add(1)
	}
	promSyncFanoutTotal.WithLabelValues(result).Inc()
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
	hintToPullCount := mc.hintToPullCount.Load()
	avgHintToPullMs := 0.0
	if hintToPullCount > 0 {
		avgHintToPullMs = float64(mc.hintToPullTotalNs.Load()) / float64(hintToPullCount) / 1e6
	}
	fanoutTotal := mc.fanoutTotal.Load()
	fanoutFailures := mc.fanoutFailures.Load()
	fanoutFailureRatio := 0.0
	if fanoutTotal > 0 {
		fanoutFailureRatio = float64(fanoutFailures) / float64(fanoutTotal)
	}
	return map[string]float64{
		metricSyncAppendTotal:      float64(mc.appendTotal.Load()),
		metricSyncAppendBatchTotal: float64(mc.appendBatchTotal.Load()),
		metricSyncPullTotal:        float64(pullTotal),
		metricSyncPullDurationMS:   avgPullDurationMs,
		metricSyncRequiresResync:   float64(mc.requiresResyncTotal.Load()),
		metricSyncStoredPatchKeys:  float64(mc.storedPatchKeys.Load()),
		metricSyncHintToPullMS:     avgHintToPullMs,
		metricSyncFanoutTotal:      float64(fanoutTotal),
		metricSyncFanoutFailures:   float64(fanoutFailures),
		metricSyncFanoutFailRatio:  fanoutFailureRatio,
	}
}
