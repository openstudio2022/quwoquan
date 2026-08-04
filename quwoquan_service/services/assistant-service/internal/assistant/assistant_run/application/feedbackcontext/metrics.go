package feedbackcontext

import (
	"strings"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

var decisionTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_feedback_context_decision_total",
		Help: "Frozen feedback-context decisions for newly created assistant runs.",
	},
	[]string{"decision"},
)

func recordDecision(decision string) {
	if !assistantmodel.IsKnownAssistantFeedbackContextDecision(decision) {
		decision = "unknown"
	}
	decisionTotal.WithLabelValues(strings.TrimSpace(decision)).Inc()
}

// NoInjection records a platform-owned exclusion decision, such as a shared
// surface privacy boundary, without exposing the metric implementation to the
// AssistantRun command service.
func NoInjection(
	decision string,
	policy assistantmodel.AssistantFrozenLearningContextPolicy,
) assistantmodel.AssistantFeedbackContextSnapshot {
	recordDecision(decision)
	return assistantmodel.AssistantFeedbackContextSnapshot{
		Decision:                 strings.TrimSpace(decision),
		WindowDays:               policy.WindowDays,
		SnapshotTrainingEligible: false,
	}
}
