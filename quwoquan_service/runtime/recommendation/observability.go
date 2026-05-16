package recommendation

import (
	"log/slog"
	"sync/atomic"
	"time"
)

// PipelineMetrics captures per-request recommendation pipeline timing.
type PipelineMetrics struct {
	UserID          string            `json:"userId"`
	SessionID       string            `json:"sessionId"`
	RecallLatency   time.Duration     `json:"recallLatencyMs"`
	ScoreLatency    time.Duration     `json:"scoreLatencyMs"`
	RerankLatency   time.Duration     `json:"rerankLatencyMs"`
	TotalLatency    time.Duration     `json:"totalLatencyMs"`
	CandidateCount  int               `json:"candidateCount"`
	FilteredCount   int               `json:"filteredCount"`
	ResultCount     int               `json:"resultCount"`
	SourceBreakdown map[string]int    `json:"sourceBreakdown,omitempty"`
	ModelUsed       string            `json:"modelUsed,omitempty"`
	ExperimentBucket string           `json:"experimentBucket,omitempty"`
}

// PipelineStats provides global pipeline statistics (thread-safe counters).
type PipelineStats struct {
	TotalRequests     atomic.Int64
	EmptyResults      atomic.Int64
	ModelTimeouts     atomic.Int64
	SlowRequests      atomic.Int64
	TotalRecallMs     atomic.Int64
	TotalScoreMs      atomic.Int64
	TotalRerankMs     atomic.Int64
}

// GlobalPipelineStats holds real-time pipeline counters.
var GlobalPipelineStats PipelineStats

// RecordMetrics updates global stats from a single pipeline execution.
func RecordMetrics(m PipelineMetrics) {
	GlobalPipelineStats.TotalRequests.Add(1)
	if m.ResultCount == 0 {
		GlobalPipelineStats.EmptyResults.Add(1)
	}
	if m.TotalLatency > 200*time.Millisecond {
		GlobalPipelineStats.SlowRequests.Add(1)
	}
	GlobalPipelineStats.TotalRecallMs.Add(m.RecallLatency.Milliseconds())
	GlobalPipelineStats.TotalScoreMs.Add(m.ScoreLatency.Milliseconds())
	GlobalPipelineStats.TotalRerankMs.Add(m.RerankLatency.Milliseconds())
}

// RecordModelTimeout increments the model timeout counter.
func RecordModelTimeout() {
	GlobalPipelineStats.ModelTimeouts.Add(1)
}

// SnapshotStats returns a point-in-time stats map (for /metrics or structured logs).
func SnapshotStats() map[string]int64 {
	total := GlobalPipelineStats.TotalRequests.Load()
	return map[string]int64{
		"total_requests":  total,
		"empty_results":   GlobalPipelineStats.EmptyResults.Load(),
		"model_timeouts":  GlobalPipelineStats.ModelTimeouts.Load(),
		"slow_requests":   GlobalPipelineStats.SlowRequests.Load(),
		"avg_recall_ms":   safeDiv(GlobalPipelineStats.TotalRecallMs.Load(), total),
		"avg_score_ms":    safeDiv(GlobalPipelineStats.TotalScoreMs.Load(), total),
		"avg_rerank_ms":   safeDiv(GlobalPipelineStats.TotalRerankMs.Load(), total),
	}
}

func safeDiv(a, b int64) int64 {
	if b == 0 {
		return 0
	}
	return a / b
}

// LogMetrics emits structured observability data for the recommendation pipeline.
func LogMetrics(logger *slog.Logger, m PipelineMetrics) {
	RecordMetrics(m)
	if logger == nil {
		return
	}
	attrs := []any{
		slog.String("userId", m.UserID),
		slog.String("sessionId", m.SessionID),
		slog.Int64("recallMs", m.RecallLatency.Milliseconds()),
		slog.Int64("scoreMs", m.ScoreLatency.Milliseconds()),
		slog.Int64("rerankMs", m.RerankLatency.Milliseconds()),
		slog.Int64("totalMs", m.TotalLatency.Milliseconds()),
		slog.Int("candidates", m.CandidateCount),
		slog.Int("filtered", m.FilteredCount),
		slog.Int("results", m.ResultCount),
	}
	if m.ModelUsed != "" {
		attrs = append(attrs, slog.String("model", m.ModelUsed))
	}
	if m.ExperimentBucket != "" {
		attrs = append(attrs, slog.String("bucket", m.ExperimentBucket))
	}

	if m.TotalLatency > 200*time.Millisecond {
		logger.Warn("rec.pipeline.slow", attrs...)
	} else {
		logger.Info("rec.pipeline.ok", attrs...)
	}
}
