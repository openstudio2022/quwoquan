// Package searchmetrics holds the search-service SLI metrics. They are the
// measurement source for the search SLOs (see configs/observability/search_slo.yaml):
// retrieve latency P50/P99, availability/error rate, zero-result rate and
// degradation rate. Latency is a histogram (never an arithmetic mean) so true
// quantiles can be computed in Prometheus. Counters are labeled by mode and AB
// bucket so every SLI segments by experiment arm for attribution.
package searchmetrics

import (
	"strings"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	recentsearch "quwoquan_service/services/search-service/internal/search/recent_search_state/application"
	"quwoquan_service/services/search-service/internal/search/search_query/application"
)

const (
	namespace = "search"
	subsystem = "retrieve"
)

var (
	_ application.SearchRequestObserver      = (*Recorder)(nil)
	_ application.SearchLoadObserver         = (*Recorder)(nil)
	_ recentsearch.Observer                  = (*Recorder)(nil)
	_ application.RelatedTermsCacheObserver  = (*Recorder)(nil)
	_ application.IntersectionAttachObserver = (*Recorder)(nil)
)

// Recorder 通过 Prometheus collectors 实现应用层观测端口。
type Recorder struct{}

func NewRecorder() *Recorder {
	return &Recorder{}
}

var (
	// duration is the retrieve latency histogram (seconds). Buckets are tuned for
	// the search path: sub-10ms suggest hits up to multi-second degraded tails.
	duration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: namespace,
		Subsystem: subsystem,
		Name:      "duration_seconds",
		Help:      "Search retrieve latency in seconds (P50/P99 SLI source).",
		Buckets:   []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5},
	}, []string{"mode", "bucket", "status"})

	// requests is the request counter (availability + error-rate SLI source).
	requests = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: namespace,
		Subsystem: subsystem,
		Name:      "requests_total",
		Help:      "Search requests by mode, AB bucket and status (ok|error).",
	}, []string{"mode", "bucket", "status"})

	// zeroResults counts successful searches that returned no hits (zero-result
	// rate SLI numerator; denominator is requests with status=ok).
	zeroResults = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: namespace,
		Subsystem: subsystem,
		Name:      "zero_results_total",
		Help:      "Successful searches that returned zero hits, by mode and bucket.",
	}, []string{"mode", "bucket"})

	// degraded counts searches whose response carried a controlled dependency
	// degradation signal. Production recall never switches to a second backend.
	degraded = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: namespace,
		Subsystem: subsystem,
		Name:      "degraded_total",
		Help:      "Searches that returned degrade signals, by mode and bucket.",
	}, []string{"mode", "bucket"})

	// termHeatApplied counts searches where the search-term heat boost actually
	// re-ranked hits, so the AB term_heat arm's reach is observable.
	termHeatApplied = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: namespace,
		Subsystem: subsystem,
		Name:      "term_heat_applied_total",
		Help:      "Searches where search-term heat re-ranked hits, by bucket.",
	}, []string{"bucket"})

	// feedback counts feedback intake by event type (impression/click/dwell/…),
	// the closed-loop signal volume that feeds heat mining.
	feedback = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: namespace,
		Subsystem: "feedback",
		Name:      "events_total",
		Help:      "Search feedback events received, by event type.",
	}, []string{"event_type"})

	// loadShed counts requests rejected by the backpressure boundary before they
	// reached the handler (inflight concurrency cap). It is the load-shed SLI: a
	// controlled 503 degrade that protects the instance from pile-up collapse.
	loadShed = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: namespace,
		Subsystem: subsystem,
		Name:      "load_shed_total",
		Help:      "Requests shed by the backpressure boundary, by reason.",
	}, []string{"reason"})

	// inflight is the current in-flight search concurrency gauge (queue-depth /
	// saturation SLI source; compare against load_model.max_concurrency_per_instance).
	inflight = promauto.NewGauge(prometheus.GaugeOpts{
		Namespace: namespace,
		Subsystem: subsystem,
		Name:      "inflight",
		Help:      "Current in-flight search requests held by the backpressure limiter.",
	})

	// relatedTermsCache counts hot-query related-terms cache outcomes so the
	// Mongo offload (cache hit ratio) is observable under concurrency.
	relatedTermsCache = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: namespace,
		Subsystem: subsystem,
		Name:      "related_terms_cache_total",
		Help:      "Related-terms hot-query cache outcomes (hit|miss).",
	}, []string{"result"})

	recentDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: namespace,
		Subsystem: "recent",
		Name:      "duration_seconds",
		Help:      "Recent-search operation latency in seconds.",
		Buckets:   []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5},
	}, []string{"operation", "status"})

	recentRequests = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: namespace,
		Subsystem: "recent",
		Name:      "requests_total",
		Help:      "Recent-search requests by operation and bounded outcome.",
	}, []string{"operation", "status"})

	intersectionAttachDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: namespace,
		Subsystem: "intersection_attach",
		Name:      "duration_seconds",
		Help:      "Top-hit intersection attachment latency in seconds.",
		Buckets:   []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5},
	}, []string{"status"})

	intersectionAttachHits = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: namespace,
		Subsystem: "intersection_attach",
		Name:      "hits_total",
		Help:      "Search hits requested or enriched by the intersection attachment stage.",
	}, []string{"result"})

	feedbackSignalRelay = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: namespace,
		Subsystem: "feedback_signal_relay",
		Name:      "outcomes_total",
		Help:      "Durable feedback signal relay outcomes.",
	}, []string{"outcome"})

	feedbackSignalPendingAge = promauto.NewGauge(prometheus.GaugeOpts{
		Namespace: namespace,
		Subsystem: "feedback_signal_relay",
		Name:      "oldest_pending_age_seconds",
		Help:      "Age in seconds of the oldest click awaiting durable signal publication.",
	})
)

// ObserveSearch records latency + request + zero-result/degrade/term-heat SLIs
// for one search in a single call so the labels stay consistent.
func (*Recorder) ObserveSearch(o application.SearchObservation) {
	mode := normMode(o.Mode)
	bucket := normLabel(o.Bucket)
	status := "ok"
	if o.Err {
		status = "error"
	}
	duration.WithLabelValues(mode, bucket, status).Observe(o.Seconds)
	requests.WithLabelValues(mode, bucket, status).Inc()
	if o.Err {
		return
	}
	if o.ResultCount == 0 {
		zeroResults.WithLabelValues(mode, bucket).Inc()
	}
	if o.Degraded {
		degraded.WithLabelValues(mode, bucket).Inc()
	}
	if o.TermHeatApplied {
		termHeatApplied.WithLabelValues(bucket).Inc()
	}
}

// ObserveFeedback records one feedback intake event.
func (*Recorder) ObserveFeedback(eventType string) {
	feedback.WithLabelValues(normLabel(eventType)).Inc()
}

func (*Recorder) ObserveFeedbackSignalRelay(outcome string) {
	feedbackSignalRelay.WithLabelValues(normLabel(outcome)).Inc()
}

func (*Recorder) SetFeedbackSignalPendingAge(seconds float64) {
	if seconds < 0 {
		seconds = 0
	}
	feedbackSignalPendingAge.Set(seconds)
}

// ObserveLoadShed records a request shed by the backpressure boundary.
func (*Recorder) ObserveLoadShed(reason string) {
	loadShed.WithLabelValues(normLabel(reason)).Inc()
}

// SetInflight publishes the current in-flight concurrency for the saturation gauge.
func (*Recorder) SetInflight(n int) {
	inflight.Set(float64(n))
}

// ObserveRelatedTermsCache records one related-terms cache lookup outcome.
func (*Recorder) ObserveRelatedTermsCache(hit bool) {
	result := "miss"
	if hit {
		result = "hit"
	}
	relatedTermsCache.WithLabelValues(result).Inc()
}

// ObserveRecentSearch records one RecentSearchState operation. The handler only
// emits list|upsert|delete|clear and ok|unauthorized|invalid|error.
func (*Recorder) ObserveRecentSearch(o recentsearch.Observation) {
	operation := normLabel(o.Operation)
	status := normLabel(o.Status)
	recentDuration.WithLabelValues(operation, status).Observe(o.Seconds)
	recentRequests.WithLabelValues(operation, status).Inc()
}

func (*Recorder) ObserveIntersectionAttach(
	observation application.IntersectionAttachObservation,
) {
	intersectionAttachDuration.
		WithLabelValues(normLabel(observation.Status)).
		Observe(observation.Seconds)
	intersectionAttachHits.
		WithLabelValues("requested").
		Add(float64(observation.RequestedHits))
	intersectionAttachHits.
		WithLabelValues("attached").
		Add(float64(observation.AttachedHits))
}

func normMode(mode string) string {
	mode = strings.ToLower(strings.TrimSpace(mode))
	if mode == "" {
		return "result"
	}
	return mode
}

func normLabel(v string) string {
	v = strings.ToLower(strings.TrimSpace(v))
	if v == "" {
		return "unknown"
	}
	return v
}
