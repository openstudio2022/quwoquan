package recommendation

import (
	"log/slog"
	"time"
)

// PipelineMetrics captures per-request recommendation pipeline timing.
type PipelineMetrics struct {
	UserID         string        `json:"userId"`
	SessionID      string        `json:"sessionId"`
	RecallLatency  time.Duration `json:"recallLatencyMs"`
	ScoreLatency   time.Duration `json:"scoreLatencyMs"`
	RerankLatency  time.Duration `json:"rerankLatencyMs"`
	TotalLatency   time.Duration `json:"totalLatencyMs"`
	CandidateCount int           `json:"candidateCount"`
	FilteredCount  int           `json:"filteredCount"`
	ResultCount    int           `json:"resultCount"`
	SourceBreakdown map[string]int `json:"sourceBreakdown,omitempty"`
}

// LogMetrics emits structured observability data for the recommendation pipeline.
func LogMetrics(logger *slog.Logger, m PipelineMetrics) {
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

	if m.TotalLatency > 200*time.Millisecond {
		logger.Warn("rec.pipeline.slow", attrs...)
	} else {
		logger.Info("rec.pipeline.ok", attrs...)
	}
}
