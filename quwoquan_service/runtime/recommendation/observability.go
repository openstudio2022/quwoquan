package recommendation

import (
	"log/slog"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// PipelineMetrics captures per-request recommendation pipeline timing.
type PipelineMetrics struct {
	UserID             string         `json:"userId"`
	SessionID          string         `json:"sessionId"`
	RecallLatency      time.Duration  `json:"recallLatencyMs"`
	ScoreLatency       time.Duration  `json:"scoreLatencyMs"`
	RerankLatency      time.Duration  `json:"rerankLatencyMs"`
	TotalLatency       time.Duration  `json:"totalLatencyMs"`
	CandidateCount     int            `json:"candidateCount"`
	FilteredCount      int            `json:"filteredCount"`
	ResultCount        int            `json:"resultCount"`
	SourceBreakdown    map[string]int `json:"sourceBreakdown,omitempty"`
	ModelUsed          string         `json:"modelUsed,omitempty"`
	ExperimentBucket   string         `json:"experimentBucket,omitempty"`
	TopicEntropy       float64        `json:"topicEntropy,omitempty"`
	AuthorRepeatRate   float64        `json:"authorRepeatRate,omitempty"`
	AuthorHHI          float64        `json:"authorHhi,omitempty"`
	GeoCoverage        float64        `json:"geoCoverage,omitempty"`
	DistinctAuthors    int            `json:"distinctAuthors,omitempty"`
	DistinctTopics     int            `json:"distinctTopics,omitempty"`
	DistinctGeoBuckets int            `json:"distinctGeoBuckets,omitempty"`
}

var (
	pipelineRequestsTotal = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "rec",
		Subsystem: "pipeline",
		Name:      "requests_total",
		Help:      "Total recommendation pipeline requests.",
	})

	pipelineModelHitsTotal = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "rec",
		Subsystem: "pipeline",
		Name:      "model_hits_total",
		Help:      "Pipeline requests served by the model path.",
	})

	pipelineRuleHitsTotal = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "rec",
		Subsystem: "pipeline",
		Name:      "rule_hits_total",
		Help:      "Pipeline requests served by the rule fallback path.",
	})

	pipelineEmptyResultsTotal = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "rec",
		Subsystem: "pipeline",
		Name:      "empty_results_total",
		Help:      "Requests returning zero results.",
	})

	pipelineModelTimeoutsTotal = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "rec",
		Subsystem: "pipeline",
		Name:      "model_timeouts_total",
		Help:      "Model scoring timeouts.",
	})

	pipelineSlowRequestsTotal = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "rec",
		Subsystem: "pipeline",
		Name:      "slow_requests_total",
		Help:      "Requests exceeding 200ms SLO.",
	})

	pipelineStageLatency = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: "rec",
		Subsystem: "pipeline",
		Name:      "stage_latency_seconds",
		Help:      "Latency per pipeline stage.",
		Buckets:   []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0},
	}, []string{"stage"})

	pipelineTotalLatency = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: "rec",
		Subsystem: "pipeline",
		Name:      "total_latency_seconds",
		Help:      "End-to-end pipeline latency.",
		Buckets:   []float64{0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0},
	}, []string{"experiment"})

	pipelineCandidates = promauto.NewHistogram(prometheus.HistogramOpts{
		Namespace: "rec",
		Subsystem: "pipeline",
		Name:      "candidate_count",
		Help:      "Number of candidates per request.",
		Buckets:   []float64{0, 10, 50, 100, 200, 500, 1000},
	})

	pipelineResults = promauto.NewHistogram(prometheus.HistogramOpts{
		Namespace: "rec",
		Subsystem: "pipeline",
		Name:      "result_count",
		Help:      "Number of results returned per request.",
		Buckets:   []float64{0, 5, 10, 20, 30, 50, 100},
	})
)

// RecordMetrics observes Prometheus metrics from a single pipeline execution.
func RecordMetrics(m PipelineMetrics) {
	pipelineRequestsTotal.Inc()
	modelUsed := strings.ToLower(strings.TrimSpace(m.ModelUsed))
	if modelUsed == "" {
		modelUsed = strings.ToLower(strings.TrimSpace(m.ExperimentBucket))
	}
	switch modelUsed {
	case "rule", "":
		pipelineRuleHitsTotal.Inc()
	default:
		pipelineModelHitsTotal.Inc()
	}
	if m.ResultCount == 0 {
		pipelineEmptyResultsTotal.Inc()
	}
	if m.TotalLatency > 200*time.Millisecond {
		pipelineSlowRequestsTotal.Inc()
	}

	pipelineStageLatency.WithLabelValues("recall").Observe(m.RecallLatency.Seconds())
	pipelineStageLatency.WithLabelValues("score").Observe(m.ScoreLatency.Seconds())
	pipelineStageLatency.WithLabelValues("rerank").Observe(m.RerankLatency.Seconds())

	bucket := m.ExperimentBucket
	if bucket == "" {
		bucket = "default"
	}
	pipelineTotalLatency.WithLabelValues(bucket).Observe(m.TotalLatency.Seconds())
	pipelineCandidates.Observe(float64(m.CandidateCount))
	pipelineResults.Observe(float64(m.ResultCount))
}

// RecordModelTimeout increments the model timeout counter.
func RecordModelTimeout() {
	pipelineModelTimeoutsTotal.Inc()
}

// LogMetrics emits structured observability data and updates Prometheus.
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
	if m.TopicEntropy > 0 {
		attrs = append(attrs, slog.Float64("topicEntropy", m.TopicEntropy))
	}
	if m.AuthorRepeatRate > 0 {
		attrs = append(attrs, slog.Float64("authorRepeatRate", m.AuthorRepeatRate))
	}
	if m.AuthorHHI > 0 {
		attrs = append(attrs, slog.Float64("authorHhi", m.AuthorHHI))
	}
	if m.GeoCoverage > 0 {
		attrs = append(attrs, slog.Float64("geoCoverage", m.GeoCoverage))
	}
	if m.DistinctAuthors > 0 {
		attrs = append(attrs, slog.Int("distinctAuthors", m.DistinctAuthors))
	}
	if m.DistinctTopics > 0 {
		attrs = append(attrs, slog.Int("distinctTopics", m.DistinctTopics))
	}
	if m.DistinctGeoBuckets > 0 {
		attrs = append(attrs, slog.Int("distinctGeoBuckets", m.DistinctGeoBuckets))
	}

	if m.TotalLatency > 200*time.Millisecond {
		logger.Warn("rec.pipeline.slow", attrs...)
	} else {
		logger.Info("rec.pipeline.ok", attrs...)
	}
}
