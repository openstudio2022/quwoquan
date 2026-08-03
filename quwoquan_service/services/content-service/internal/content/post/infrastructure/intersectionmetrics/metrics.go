// Package intersectionmetrics holds the content-service intersection business
// SLI metrics. They are the measurement source for the intersection SLOs (see
// configs/observability/intersection_slo.yaml): repeat-exposure rate, cooldown
// write volume, freshness filter rate, display completeness and inbox visit
// (清零) volume. HTTP latency P95 / error rate / availability for the
// /content/intersections* routes are produced separately by the
// runtime/observability http_server_* middleware; this package only adds the
// business funnel signals so every SLI has a real metric source (no second
// truth, no documentation-only SLI).
package intersectionmetrics

import (
	"strings"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	intersectionapp "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
)

const (
	namespace = "intersection"
)

var (
	// feedCandidates counts intersections that entered the spotlight candidate
	// window, split by class (fact|affinity) and rank_state (fresh|seen). The
	// repeat-exposure rate SLI = seen / total.
	feedCandidates = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: namespace,
		Subsystem: "feed",
		Name:      "candidates_total",
		Help:      "Intersection feed candidates entering the spotlight window by channel, class(fact|affinity) and rank_state(fresh|seen).",
	}, []string{"channel", "class", "rank_state"})

	// feedFiltered counts intersections dropped before the candidate window.
	// reason: stale (past freshness, triggers recompute) | display_incomplete
	// (missing primaryText/avatar, blank-window governance).
	feedFiltered = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: namespace,
		Subsystem: "feed",
		Name:      "filtered_total",
		Help:      "Intersection feed candidates filtered before the window by channel and reason(stale|display_incomplete).",
	}, []string{"channel", "reason"})

	// exposureReported counts objects written into the cross-session cooldown
	// memory window (cooldown write volume / dedup pressure source).
	exposureReported = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: namespace,
		Subsystem: "cooldown",
		Name:      "exposure_reported_total",
		Help:      "Objects written into the cross-session intersection cooldown window.",
	})

	// negativeFeedbackReported counts subjects written into the negative-feedback
	// cooldown set (rec:ineg) driven by explicit intersection feedbackKinds. Paired
	// with feed filtered_total{reason="negative"} it proves the negative-feedback →
	// cooldown funnel (F: 过冷却不再重复推荐).
	negativeFeedbackReported = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: namespace,
		Subsystem: "cooldown",
		Name:      "negative_feedback_reported_total",
		Help:      "Subjects written into the intersection negative-feedback cooldown set (rec:ineg).",
	})

	// inboxVisit counts My-Intersection clears (read watermark advance) per
	// dimension (清零 volume).
	inboxVisit = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: namespace,
		Subsystem: "inbox",
		Name:      "visit_total",
		Help:      "My-intersection inbox clears (watermark advance) by dimension.",
	}, []string{"dimension"})

	// inboxFiltered counts inbox summary/list intersections filtered by
	// freshness (recompute trigger source).
	inboxFiltered = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: namespace,
		Subsystem: "inbox",
		Name:      "filtered_total",
		Help:      "My-intersection inbox intersections filtered by reason(stale).",
	}, []string{"reason"})

	// redisDegraded counts Redis-unavailable degradations: write fast-paths that
	// soft-fail without breaking the request, and watermark reads that fall back
	// to the durable store. This is the measurement source for the Redis
	// availability/degradation SLI (Redis outage must not fail the homepage and
	// must not lose read positions).
	redisDegraded = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: namespace,
		Subsystem: "redis",
		Name:      "degraded_total",
		Help:      "Intersection Redis degradations by op(exposure_write|negative_feedback_write|watermark_write|watermark_read).",
	}, []string{"op"})
)

// Recorder is the Prometheus-backed implementation of
// intersectionapp.IntersectionMetricsRecorder.
type Recorder struct{}

// New returns a Prometheus intersection metrics recorder.
func New() *Recorder { return &Recorder{} }

var _ intersectionapp.IntersectionMetricsRecorder = (*Recorder)(nil)

func norm(v, fallback string) string {
	v = strings.TrimSpace(v)
	if v == "" {
		return fallback
	}
	return v
}

// ObserveFeedCandidate implements intersectionapp.IntersectionMetricsRecorder.
func (*Recorder) ObserveFeedCandidate(channel, class, rankState string) {
	feedCandidates.WithLabelValues(norm(channel, "default"), norm(class, "fact"), norm(rankState, "fresh")).Inc()
}

// ObserveFeedFiltered implements intersectionapp.IntersectionMetricsRecorder.
func (*Recorder) ObserveFeedFiltered(channel, reason string) {
	feedFiltered.WithLabelValues(norm(channel, "default"), norm(reason, "unknown")).Inc()
}

// ObserveExposureReported implements intersectionapp.IntersectionMetricsRecorder.
func (*Recorder) ObserveExposureReported(count int) {
	if count > 0 {
		exposureReported.Add(float64(count))
	}
}

// ObserveNegativeFeedbackReported implements intersectionapp.IntersectionMetricsRecorder.
func (*Recorder) ObserveNegativeFeedbackReported(count int) {
	if count > 0 {
		negativeFeedbackReported.Add(float64(count))
	}
}

// ObserveInboxVisit implements intersectionapp.IntersectionMetricsRecorder.
func (*Recorder) ObserveInboxVisit(dimension string) {
	inboxVisit.WithLabelValues(norm(dimension, "all")).Inc()
}

// ObserveInboxFiltered implements intersectionapp.IntersectionMetricsRecorder.
func (*Recorder) ObserveInboxFiltered(reason string) {
	inboxFiltered.WithLabelValues(norm(reason, "unknown")).Inc()
}

// ObserveRedisDegraded implements intersectionapp.IntersectionMetricsRecorder.
func (*Recorder) ObserveRedisDegraded(op string) {
	redisDegraded.WithLabelValues(norm(op, "unknown")).Inc()
}
