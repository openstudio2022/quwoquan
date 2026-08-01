package metrics

import (
	"strings"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	recentsearch "quwoquan_service/services/search-service/internal/search/recent_search_state/application"
)

var _ recentsearch.Observer = (*Recorder)(nil)

type Recorder struct{}

func NewRecorder() *Recorder { return &Recorder{} }

var (
	duration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: "search",
		Subsystem: "recent",
		Name:      "duration_seconds",
		Help:      "Recent-search operation latency in seconds.",
		Buckets:   []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5},
	}, []string{"operation", "status"})
	requests = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "search",
		Subsystem: "recent",
		Name:      "requests_total",
		Help:      "Recent-search requests by operation and bounded outcome.",
	}, []string{"operation", "status"})
)

func (*Recorder) ObserveRecentSearch(observation recentsearch.Observation) {
	operation := normalize(observation.Operation)
	status := normalize(observation.Status)
	duration.WithLabelValues(operation, status).Observe(observation.Seconds)
	requests.WithLabelValues(operation, status).Inc()
}

func normalize(value string) string {
	value = strings.ToLower(strings.TrimSpace(value))
	if value == "" {
		return "unknown"
	}
	return value
}
