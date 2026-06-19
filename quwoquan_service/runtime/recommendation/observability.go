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

	feedClickTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "recommendation_feed_click_total",
		Help: "Total feed item clicks (seven-state funnel: served/visible/impressed/click/dwell/interaction/negative).",
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

	// feedDuplicateExposureFiltered 度量曝光过滤拦截到的「已 served/impressed 候选」，
	// 即若不过滤就会再次曝光的数量。repeat_exposure_rate = duplicate_exposure / served。
	// reason ∈ {served, impressed}，与告警 RecommendationRepeatExposureRateHigh 同名指标对齐。
	feedDuplicateExposureFiltered = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "recommendation_feed_duplicate_exposure_total",
		Help: "Total candidates filtered because already served/impressed (would-be repeat exposure).",
	}, []string{"reason"})

	// feedEngagementTotal 按 action 维度记录正向交互（CTR 分子用 action=click），
	// 与 feedImpressedTotal 组合即 CTR = engagement{action=click} / impressed。
	feedEngagementTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "recommendation_feed_engagement_total",
		Help: "Total positive engagement events by action (click/like/comment/share/follow/...).",
	}, []string{"action"})

	// feedCompletionTotal 记录达到完成阈值的消费事件（content_depth L3+/play_progress>=90%），
	// completion_rate = completion / impressed。
	feedCompletionTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "recommendation_feed_completion_total",
		Help: "Total content consumption completion events (deep content_depth or >=90% playback).",
	})

	// opsInterventionAuditTotal 审计每次生效的运营干预（置顶/降权/屏蔽），按 action × target_type
	// 拆分；对齐 SLI ops_intervention_audit_coverage（每条干预都必须留痕）。
	opsInterventionAuditTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "recommendation_feed_ops_intervention_audit_total",
		Help: "Operational interventions applied to the ranked feed, by action and target type.",
	}, []string{"action", "target_type"})

	// offlineEvalMetricValue 暴露离线 replay 评估指标（ndcg_at_k/recall_at_k/coverage/
	// diversity_rate/repeat_exposure_rate/negative_feedback_rate/calibration_error），
	// 由 ComputeReplayReport().Emit() 单源写入；对齐 recommendation_slo.yaml 的
	// recommendation_offline_eval_metric_value{metric=...}。
	offlineEvalMetricValue = promauto.NewGaugeVec(prometheus.GaugeOpts{
		Name: "recommendation_offline_eval_metric_value",
		Help: "Latest offline replay evaluation metric value, by metric name (and optional k).",
	}, []string{"metric"})

	// abExperimentValidityTotal 记录在线 AB 实验准入校验结果（valid/invalid），按 result ×
	// experiment 拆分；对齐 SLI ab_experiment_validity = valid / (valid + invalid)。
	abExperimentValidityTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "recommendation_feed_ab_experiment_validity_total",
		Help: "AB experiment admission validation outcomes, by result and experiment id.",
	}, []string{"result", "experiment"})

	// feedPatchEmittedTotal 记录成功发射的低风险实时 patch（阶段七 §G），按 patch 类型 ×
	// 原因码拆分；端侧订阅同名 per-user 通道在安全边界合并 patch。
	feedPatchEmittedTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "recommendation_feed_patch_emitted_total",
		Help: "Realtime feed patches emitted by type and reason code (new_candidate_hint/negative_feedback_removal/refresh_suggestion).",
	}, []string{"patch_type", "reason"})

	// feedPatchEmitFailedTotal 记录 patch 发射失败（按 patch 类型 × 失败阶段：validate/marshal/publish）。
	// best-effort 发射：失败只计指标 + 日志，不阻断行为主链路；该指标应长期接近 0。
	feedPatchEmitFailedTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "recommendation_feed_patch_emit_failed_total",
		Help: "Realtime feed patch emission failures by type and stage (validate/marshal/publish). Should stay near zero.",
	}, []string{"patch_type", "stage"})
)

// RecordFeedPatchEmitted 记录一次成功发射的实时 patch（patch 类型 + 原因码）。
func RecordFeedPatchEmitted(patchType, reason string) {
	patchType = strings.TrimSpace(patchType)
	if patchType == "" {
		patchType = "unknown"
	}
	reason = strings.TrimSpace(reason)
	if reason == "" {
		reason = "unknown"
	}
	feedPatchEmittedTotal.WithLabelValues(patchType, reason).Inc()
}

// RecordFeedPatchEmitFailed 记录一次 patch 发射失败（patch 类型 + 失败阶段）。
func RecordFeedPatchEmitFailed(patchType, stage string) {
	patchType = strings.TrimSpace(patchType)
	if patchType == "" {
		patchType = "unknown"
	}
	stage = strings.TrimSpace(stage)
	if stage == "" {
		stage = "unknown"
	}
	feedPatchEmitFailedTotal.WithLabelValues(patchType, stage).Inc()
}

// RecordOfflineEvalMetric 写入一条离线 replay 评估指标（gauge，最新值覆盖）。
func RecordOfflineEvalMetric(metric string, value float64) {
	offlineEvalMetricValue.WithLabelValues(metric).Set(value)
}

// RecordABExperimentValidity 记录一次 AB 实验准入校验结果（valid=true 计入 valid 否则 invalid）。
func RecordABExperimentValidity(experimentID string, valid bool) {
	result := "invalid"
	if valid {
		result = "valid"
	}
	abExperimentValidityTotal.WithLabelValues(result, experimentID).Inc()
}

// RecordOpsInterventionApplied 记录一次生效的运营干预，喂运营干预审计指标。
func RecordOpsInterventionApplied(action, targetType string) {
	opsInterventionAuditTotal.WithLabelValues(action, targetType).Inc()
}

// completionDepthThreshold 是判定「完成」的归一化消费深度下限（L3 = 深度消费）。
const completionDepthThreshold = 3

// completionPlaybackRatio 是判定「完成」的播放比例下限（90%）。
const completionPlaybackRatio = 0.9

// isCompletionSignal 判定一个行为信号是否构成「内容消费完成」。
// content_depth 达到 L3+（深度消费）或 play_progress 播放比例 >= 90% 即视为完成，
// 用于喂 recommendation_feed_completion_total（完成率 SLO 分子）。
func isCompletionSignal(signal BehaviorSignal) bool {
	switch signal.Action {
	case "content_depth":
		return signal.EngagementDepth >= completionDepthThreshold
	case "play_progress":
		return signal.ConsumedRatio >= completionPlaybackRatio
	default:
		return false
	}
}

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
	case "click":
		// 七态独立 click：既计独立 click 态，又作为 CTR 分子进 engagement{action=click}。
		feedClickTotal.Inc()
		feedEngagementTotal.WithLabelValues(action).Inc()
	case "dwell":
		feedDwellTotal.Inc()
	case "interaction":
		feedInteractionTotal.Inc()
		feedEngagementTotal.WithLabelValues(action).Inc()
	case "negative":
		feedNegativeFeedbackTotal.Inc()
	}
	// 完成事件单独累计（与状态正交）：深度消费 / 播放完成喂完成率 SLO 分子。
	if isCompletionSignal(signal) {
		feedCompletionTotal.Inc()
	}
}

// RecordDuplicateExposureFiltered 记录曝光过滤拦截到的重复曝光候选数（按 served/impressed 拆分）。
// reason 为空或 n<=0 时忽略。喂 recommendation_feed_duplicate_exposure_total（重复曝光率 SLO 分子）。
func RecordDuplicateExposureFiltered(reason string, n int) {
	if n <= 0 {
		return
	}
	reason = strings.TrimSpace(reason)
	if reason == "" {
		reason = "unknown"
	}
	feedDuplicateExposureFiltered.WithLabelValues(reason).Add(float64(n))
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
