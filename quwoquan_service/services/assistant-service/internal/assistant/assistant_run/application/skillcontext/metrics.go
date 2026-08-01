package skillcontext

import (
	"strings"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var assistantContextResolutionTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_context_resolution_total",
		Help: "Skill context requirement outcomes without user or context values.",
	},
	[]string{"outcome", "visibility"},
)

var assistantContextPrivacyRejectionTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_context_privacy_rejection_total",
		Help: "Context denied by consent or delivery privacy boundaries.",
	},
	[]string{"reason", "visibility"},
)

func observeContextResolution(outcome string, visibility DeliveryVisibility) {
	switch outcome {
	case "resolved", "consent_rejected", "resolver_unavailable",
		"dependency_unavailable", "policy_rejected":
	default:
		outcome = "other"
	}
	assistantContextResolutionTotal.WithLabelValues(
		outcome,
		boundedVisibility(visibility),
	).Inc()
}

func observeContextPrivacyRejection(
	reason string,
	visibility DeliveryVisibility,
) {
	switch {
	case strings.Contains(reason, "consent unavailable"):
		reason = "consent_unavailable"
	case strings.Contains(reason, "consent required"):
		reason = "consent_required"
	default:
		reason = "delivery_policy"
	}
	assistantContextPrivacyRejectionTotal.WithLabelValues(
		reason,
		boundedVisibility(visibility),
	).Inc()
}

func boundedVisibility(visibility DeliveryVisibility) string {
	switch visibility {
	case DeliveryPersonal, DeliveryShared, DeliveryPublic:
		return string(visibility)
	default:
		return "other"
	}
}
