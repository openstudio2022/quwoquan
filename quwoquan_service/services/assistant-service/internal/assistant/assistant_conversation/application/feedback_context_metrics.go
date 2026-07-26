package application

import (
	"strings"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var assistantFeedbackContextDecisionTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_feedback_context_decision_total",
		Help: "Frozen feedback-context decisions for newly created assistant runs.",
	},
	[]string{"decision"},
)

func recordFeedbackContextDecision(decision string) {
	switch strings.TrimSpace(decision) {
	case "injected",
		"policy_disabled",
		"consent_unavailable",
		"consent_missing_or_opted_out",
		"projection_unavailable",
		"insufficient_samples",
		"owner_mismatch":
	default:
		decision = "unknown"
	}
	assistantFeedbackContextDecisionTotal.WithLabelValues(decision).Inc()
}
