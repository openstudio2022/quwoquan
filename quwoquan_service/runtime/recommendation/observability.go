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
	PolicyVersion      string         `json:"policyVersion,omitempty"`
	ScoringPreset      string         `json:"scoringPreset,omitempty"`
	Segment            string         `json:"segment,omitempty"`
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

	// pipelinePolicyAttribution attributes every served request to its
	// resolved policy version, scoring preset, and population segment so the
	// large-loop feedback dashboard can compare KPI by policy×preset×segment.
	// All label values are bounded (policyVersion ∈ released versions, preset ∈
	// weightPresets, segment ∈ segments.yaml ∪ {"none"}).
	pipelinePolicyAttribution = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "rec",
		Subsystem: "pipeline",
		Name:      "requests_by_policy_total",
		Help:      "Requests attributed by resolved policy version, scoring preset, and segment.",
	}, []string{"policy_version", "preset", "segment"})

	feedStateTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "recommendation_feed_state_total",
		Help: "Recommendation feedback state events by closed-state semantics.",
	}, []string{"state", "action"})

	feedServedTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "recommendation_feed_served_total",
		Help: "Total content items served by recommendation feed.",
	})

	feedImpressedTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "recommendation_feed_impressed_total",
		Help: "Total content items reaching true client-side impression threshold.",
	})

	feedVisibleTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "recommendation_feed_visible_total",
		Help: "Total content items reported visible by clients.",
	})

	feedDwellTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "recommendation_feed_dwell_total",
		Help: "Total dwell feedback events reported by clients.",
	})

	feedInteractionTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "recommendation_feed_interaction_total",
		Help: "Total positive interaction feedback events reported by clients.",
	})

	feedNegativeFeedbackTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "recommendation_feed_negative_feedback_total",
		Help: "Total explicit negative feedback events reported by clients.",
	})

	behaviorIngestTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "recommendation_behavior_ingest_total",
		Help: "Total behavior events accepted by FeedbackIngestor.",
	})

	behaviorIngestDroppedTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "recommendation_behavior_ingest_dropped_total",
		Help: "Total behavior events dropped by FeedbackIngestor.",
	}, []string{"reason"})

	hotPathDroppedTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "rec_hotpath_dropped_total",
		Help: "Total behavior signals dropped by BufferedHotPath due to backpressure.",
	})

	exposureFilterSMembersFallbackTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "recommendation_exposure_filter_smembers_fallback_total",
		Help: "Total exposure filter fallbacks to SMembers. Should stay zero on commercial path.",
	})

	dynamicBudgetSelectedTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "recommendation_dynamic_budget_selected_total",
		Help: "Total recommendation items selected after dynamic exposure budget by pool.",
	}, []string{"pool", "bucket"})

	frequencyCapFilterTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "recommendation_frequency_cap_filter_total",
		Help: "Total candidates delayed by dimension frequency caps.",
	}, []string{"dimension"})

	nearDupFilterTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "recommendation_near_dup_filter_total",
		Help: "Total candidates delayed by near-duplicate filtering.",
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

	policyVersion := strings.TrimSpace(m.PolicyVersion)
	if policyVersion == "" {
		policyVersion = "unknown"
	}
	preset := strings.TrimSpace(m.ScoringPreset)
	if preset == "" {
		preset = "default"
	}
	segment := strings.TrimSpace(m.Segment)
	if segment == "" {
		segment = "none"
	}
	pipelinePolicyAttribution.WithLabelValues(policyVersion, preset, segment).Inc()
}

// RecordModelTimeout increments the model timeout counter.
func RecordModelTimeout() {
	pipelineModelTimeoutsTotal.Inc()
}

func RecordServedItems(count int) {
	if count > 0 {
		feedServedTotal.Add(float64(count))
		feedStateTotal.WithLabelValues("served", "served").Add(float64(count))
	}
}

func RecordBehaviorIngest(signal BehaviorSignal) {
	state := normalizeFeedbackState(signal)
	if state == "" {
		state = "unknown"
	}
	action := strings.TrimSpace(signal.Action)
	if action == "" {
		action = "unknown"
	}
	behaviorIngestTotal.Inc()
	feedStateTotal.WithLabelValues(state, action).Inc()
	switch state {
	case "visible":
		feedVisibleTotal.Inc()
	case "impressed":
		feedImpressedTotal.Inc()
	case "dwell":
		feedDwellTotal.Inc()
	case "interaction":
		feedInteractionTotal.Inc()
	case "negative":
		feedNegativeFeedbackTotal.Inc()
	}
}

func RecordBehaviorIngestDropped(reason string) {
	if reason == "" {
		reason = "unknown"
	}
	behaviorIngestDroppedTotal.WithLabelValues(reason).Inc()
}

func RecordHotPathDrop() {
	hotPathDroppedTotal.Inc()
}

func RecordExposureSMembersFallback() {
	exposureFilterSMembersFallbackTotal.Inc()
}

func RecordDynamicBudgetSelection(pool string, bucket string, count int) {
	if count <= 0 {
		return
	}
	pool = strings.TrimSpace(pool)
	if pool == "" {
		pool = "unknown"
	}
	bucket = strings.TrimSpace(bucket)
	if bucket == "" {
		bucket = "default"
	}
	dynamicBudgetSelectedTotal.WithLabelValues(pool, bucket).Add(float64(count))
}

func RecordFrequencyCapFilter(dimension string, count int) {
	if count <= 0 {
		return
	}
	dimension = strings.TrimSpace(dimension)
	if dimension == "" {
		dimension = "unknown"
	}
	frequencyCapFilterTotal.WithLabelValues(dimension).Add(float64(count))
}

func RecordNearDupFilter(count int) {
	if count > 0 {
		nearDupFilterTotal.Add(float64(count))
	}
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
	if m.PolicyVersion != "" {
		attrs = append(attrs, slog.String("policyVersion", m.PolicyVersion))
	}
	if m.ScoringPreset != "" {
		attrs = append(attrs, slog.String("preset", m.ScoringPreset))
	}
	if m.Segment != "" {
		attrs = append(attrs, slog.String("segment", m.Segment))
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
