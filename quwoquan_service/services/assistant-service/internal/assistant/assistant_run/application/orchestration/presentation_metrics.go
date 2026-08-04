package orchestration

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var adaptivePresentationSelectionTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_adaptive_presentation_selection_total",
		Help: "Adaptive Presentation selections by bounded outcome.",
	},
	[]string{"outcome"},
)

func observeAdaptivePresentationSelection(outcome string) {
	switch outcome {
	case "single_candidate", "model_selected", "safe_fallback", "typed_confirmation":
	default:
		outcome = "unknown"
	}
	adaptivePresentationSelectionTotal.WithLabelValues(outcome).Inc()
}
