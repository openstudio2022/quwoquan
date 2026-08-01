package metrics

import (
	"strings"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	"quwoquan_service/services/search-service/internal/search/search_feedback_fact/application"
)

var _ application.Observer = (*Recorder)(nil)

type Recorder struct{}

func NewRecorder() *Recorder { return &Recorder{} }

var (
	feedback = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "search",
		Subsystem: "feedback",
		Name:      "events_total",
		Help:      "Search feedback events received, by event type.",
	}, []string{"event_type"})
	relay = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "search",
		Subsystem: "feedback_signal_relay",
		Name:      "outcomes_total",
		Help:      "Durable feedback signal relay outcomes.",
	}, []string{"outcome"})
	pendingAge = promauto.NewGauge(prometheus.GaugeOpts{
		Namespace: "search",
		Subsystem: "feedback_signal_relay",
		Name:      "oldest_pending_age_seconds",
		Help:      "Age in seconds of the oldest click awaiting durable signal publication.",
	})
)

func (*Recorder) ObserveFeedback(eventType string) {
	feedback.WithLabelValues(normalize(eventType)).Inc()
}

func (*Recorder) ObserveFeedbackSignalRelay(outcome string) {
	relay.WithLabelValues(normalize(outcome)).Inc()
}

func (*Recorder) SetFeedbackSignalPendingAge(seconds float64) {
	if seconds < 0 {
		seconds = 0
	}
	pendingAge.Set(seconds)
}

func normalize(value string) string {
	value = strings.ToLower(strings.TrimSpace(value))
	if value == "" {
		return "unknown"
	}
	return value
}
