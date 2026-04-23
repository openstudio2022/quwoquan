package application

import (
	"sync/atomic"
	"time"
)

const (
	metricGroupAvatarRecomputeTotal      = "quwoquan_runtime_media_group_avatar_recompute_total"
	metricGroupAvatarRecomputeDurationMS = "quwoquan_runtime_media_group_avatar_recompute_duration_ms"
	metricGroupAvatarPatchFanoutTotal    = "quwoquan_runtime_media_patch_fanout_total"
	metricGroupAvatarPatchFanoutBatch    = "quwoquan_runtime_media_patch_fanout_batch_total"
	metricGroupAvatarPatchRecipientTotal = "quwoquan_runtime_media_patch_fanout_recipient_total"
	metricGroupAvatarTaskTerminalFailed  = "quwoquan_runtime_media_group_avatar_task_terminal_failed_total"
	metricGroupAvatarTaskRetryableFailed = "quwoquan_runtime_media_group_avatar_task_retryable_failed_total"
	metricGroupAvatarTaskQueueDepth      = "quwoquan_runtime_media_group_avatar_task_queue_depth"
)

type groupAvatarSchedulerMetrics struct {
	recomputeTotal         atomic.Int64
	recomputeDurationTotal atomic.Int64
	patchFanoutTotal       atomic.Int64
	patchFanoutBatchTotal  atomic.Int64
	patchRecipientTotal    atomic.Int64
	taskTerminalFailed     atomic.Int64
	taskRetryableFailed    atomic.Int64
}

func newGroupAvatarSchedulerMetrics() *groupAvatarSchedulerMetrics {
	return &groupAvatarSchedulerMetrics{}
}

func (m *groupAvatarSchedulerMetrics) recordTask(kind string, duration time.Duration) {
	if m == nil {
		return
	}
	if kind == groupAvatarTaskKindRecompute {
		m.recomputeTotal.Add(1)
		m.recomputeDurationTotal.Add(duration.Microseconds())
		return
	}
	if kind == groupAvatarTaskKindPatch {
		m.patchFanoutTotal.Add(1)
	}
}

func (m *groupAvatarSchedulerMetrics) recordPatchBatch(recipientCount int) {
	if m == nil {
		return
	}
	m.patchFanoutBatchTotal.Add(1)
	m.patchRecipientTotal.Add(int64(recipientCount))
}

func (m *groupAvatarSchedulerMetrics) recordRetryableFailure() {
	if m == nil {
		return
	}
	m.taskRetryableFailed.Add(1)
}

func (m *groupAvatarSchedulerMetrics) recordTerminalFailure() {
	if m == nil {
		return
	}
	m.taskTerminalFailed.Add(1)
}

func (m *groupAvatarSchedulerMetrics) snapshot(queueDepth int64) map[string]float64 {
	if m == nil {
		return map[string]float64{
			metricGroupAvatarTaskQueueDepth: float64(queueDepth),
		}
	}
	recomputeTotal := m.recomputeTotal.Load()
	avgDurationMs := 0.0
	if recomputeTotal > 0 {
		avgDurationMs = float64(m.recomputeDurationTotal.Load()) / float64(recomputeTotal) / 1000
	}
	return map[string]float64{
		metricGroupAvatarRecomputeTotal:      float64(recomputeTotal),
		metricGroupAvatarRecomputeDurationMS: avgDurationMs,
		metricGroupAvatarPatchFanoutTotal:    float64(m.patchFanoutTotal.Load()),
		metricGroupAvatarPatchFanoutBatch:    float64(m.patchFanoutBatchTotal.Load()),
		metricGroupAvatarPatchRecipientTotal: float64(m.patchRecipientTotal.Load()),
		metricGroupAvatarTaskTerminalFailed:  float64(m.taskTerminalFailed.Load()),
		metricGroupAvatarTaskRetryableFailed: float64(m.taskRetryableFailed.Load()),
		metricGroupAvatarTaskQueueDepth:      float64(queueDepth),
	}
}
