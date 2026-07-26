package application

import (
	"strings"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var assistantLearningFactAppendTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_learning_fact_append_total",
		Help: "Assistant learning fact append outcomes by trusted source and fact type.",
	},
	[]string{"source", "fact_type", "outcome"},
)

func recordLearningFactAppend(source string, factType string, outcome string) {
	source = strings.TrimSpace(source)
	if source != "user" && source != "service" {
		source = "unknown"
	}
	switch strings.TrimSpace(factType) {
	case "user_feedback", "interaction_outcome", "service_scorecard":
	default:
		factType = "invalid"
	}
	switch strings.TrimSpace(outcome) {
	case "accepted", "deduplicated", "rejected", "store_failed":
	default:
		outcome = "unknown"
	}
	assistantLearningFactAppendTotal.WithLabelValues(
		source,
		factType,
		outcome,
	).Inc()
}
