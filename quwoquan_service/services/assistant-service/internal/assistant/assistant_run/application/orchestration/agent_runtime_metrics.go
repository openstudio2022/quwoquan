package orchestration

import (
	"strings"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var assistantAgentStopTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_agent_stop_total",
		Help: "AgentLoop stop decisions by bounded reason.",
	},
	[]string{"reason"},
)

var assistantAgentReplanTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_agent_replan_total",
		Help: "AgentLoop evidence replans by bounded reason.",
	},
	[]string{"reason"},
)

var assistantAgentBudgetBoundaryTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_agent_budget_boundary_total",
		Help: "AgentLoop budget boundaries that prevent unbounded execution.",
	},
	[]string{"boundary"},
)

func recordReactOutcome(result ReactResult) {
	stopReason := boundedReactMetricReason(result.StopReason)
	assistantAgentStopTotal.WithLabelValues(stopReason).Inc()
	if stopReason == "replan_budget_exhausted" ||
		stopReason == "decision_rejected_budget_exhausted" {
		assistantAgentBudgetBoundaryTotal.WithLabelValues("replan").Inc()
	}
	for _, step := range result.Steps {
		if !step.Replan {
			continue
		}
		assistantAgentReplanTotal.WithLabelValues(
			boundedReactMetricReason(step.ReplanReason),
		).Inc()
	}
}

func boundedReactMetricReason(reason string) string {
	reason = strings.TrimSpace(reason)
	switch reason {
	case "ask_user_clarification",
		"planner_aborted",
		"model_answered_without_tools",
		"tool_skipped",
		"tool_failed",
		"tool_failed_degraded_answer",
		"waiting_tool_approval",
		"replan_budget_exhausted",
		"decision_rejected",
		"decision_rejected_replanning",
		"decision_rejected_budget_exhausted",
		"observation_sufficient",
		"evidence_insufficient",
		"evidence_conflict",
		"source_required":
		return reason
	default:
		return "other"
	}
}
