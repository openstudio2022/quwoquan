package messaging

import (
	"time"

	"github.com/prometheus/client_golang/prometheus"
)

var (
	circleGroupConversationBindingConsumerTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "circle_group_conversation_binding_consumer_total",
			Help: "CircleGroupConversationProvisioned consumer outcomes.",
		},
		[]string{"result"},
	)
	circleGroupConversationBindingDuration = prometheus.NewHistogram(
		prometheus.HistogramOpts{
			Name:    "circle_group_conversation_binding_apply_seconds",
			Help:    "CircleGroup conversation binding projection transaction duration.",
			Buckets: []float64{0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30},
		},
	)
)

func init() {
	prometheus.MustRegister(
		circleGroupConversationBindingConsumerTotal,
		circleGroupConversationBindingDuration,
	)
}

func recordCircleGroupConversationBindingOutcome(result string) {
	circleGroupConversationBindingConsumerTotal.WithLabelValues(result).Inc()
}

func observeCircleGroupConversationBindingDuration(duration time.Duration) {
	circleGroupConversationBindingDuration.Observe(duration.Seconds())
}
