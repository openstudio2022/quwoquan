package tool

import (
	"errors"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
)

var publicWebToolTotal = promauto.NewCounterVec(prometheus.CounterOpts{
	Name: "assistant_public_web_tool_total",
	Help: "Assistant public web tool executions by stable tool name and outcome.",
}, []string{"tool", "outcome"})

var publicWebToolDurationSeconds = promauto.NewHistogramVec(prometheus.HistogramOpts{
	Name:    "assistant_public_web_tool_duration_seconds",
	Help:    "Assistant public web tool execution latency without URL or account labels.",
	Buckets: prometheus.DefBuckets,
}, []string{"tool", "outcome"})

var publicWebPolicyBoundaryTotal = promauto.NewCounterVec(prometheus.CounterOpts{
	Name: "assistant_public_web_policy_boundary_total",
	Help: "Assistant public web safety, budget and evidence boundary decisions.",
}, []string{"reason"})

func observePublicWebTool(toolName string, started time.Time, err error) {
	outcome := "succeeded"
	if err != nil {
		outcome = "failed"
		var canonical toolpkg.CanonicalFailure
		if errors.As(err, &canonical) {
			switch canonical.Reason {
			case "web_target_rejected":
				outcome = "target_rejected"
			case "web_budget_exhausted":
				outcome = "budget_exhausted"
			case "web_evidence_unavailable":
				outcome = "evidence_unavailable"
			case "web_budget_unavailable":
				outcome = "budget_unavailable"
			case "web_fetch_unavailable":
				outcome = "fetch_unavailable"
			}
			publicWebPolicyBoundaryTotal.WithLabelValues(canonical.Reason).Inc()
		}
	}
	publicWebToolTotal.WithLabelValues(toolName, outcome).Inc()
	publicWebToolDurationSeconds.WithLabelValues(toolName, outcome).
		Observe(time.Since(started).Seconds())
}
