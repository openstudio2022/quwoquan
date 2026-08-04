package runruntime

import (
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var assistantRunWorkerClaims = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_run_worker_claim_total",
		Help: "Durable AssistantRun worker claims by bounded outcome.",
	},
	[]string{"outcome"},
)

var assistantRunWorkerDuration = promauto.NewHistogramVec(
	prometheus.HistogramOpts{
		Name:    "assistant_run_worker_execution_seconds",
		Help:    "Time spent processing one durable AssistantRun claim.",
		Buckets: prometheus.DefBuckets,
	},
	[]string{"outcome"},
)

var assistantRunCheckpointAge = promauto.NewHistogram(
	prometheus.HistogramOpts{
		Name: "assistant_run_checkpoint_age_seconds",
		Help: "Age of the checkpoint used to recover an AssistantRun.",
		Buckets: []float64{
			1, 5, 10, 30, 60, 300, 900, 3600, 21600, 86400,
		},
	},
)

var assistantRunCancelDuration = promauto.NewHistogramVec(
	prometheus.HistogramOpts{
		Name:    "assistant_run_cancel_duration_seconds",
		Help:    "Time for an AssistantRun cancel command to stop children and commit.",
		Buckets: []float64{0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 15},
	},
	[]string{"outcome"},
)

var assistantRunStateTransitions = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_run_state_transition_total",
		Help: "Canonical AssistantRun state transitions.",
	},
	[]string{"from", "to"},
)

var assistantRunTerminalOutcomes = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_run_terminal_outcome_total",
		Help: "AssistantRun terminal outcomes after durable commit.",
	},
	[]string{"outcome"},
)

var assistantRunItemClosures = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_run_item_closure_total",
		Help: "Durable RunItem closures by bounded kind and status.",
	},
	[]string{"kind", "status"},
)

var assistantRunLeaseContentions = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_run_lease_contention_total",
		Help: "Worker lease or fencing conflicts by bounded phase.",
	},
	[]string{"phase"},
)

var assistantRunCompletionRejected = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_run_completion_rejected_total",
		Help: "Verifier completion rejections by bounded reason.",
	},
	[]string{"reason"},
)

var assistantPresentationProjectionTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_presentation_projection_total",
		Help: "Persisted presentation projection phases and outcomes.",
	},
	[]string{"phase", "outcome"},
)

var assistantRunHookInvocationTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_run_hook_invocation_total",
		Help: "AssistantRun lifecycle hook invocations by bounded phase, decision and outcome.",
	},
	[]string{"phase", "decision", "outcome"},
)

var assistantRunHookDuration = promauto.NewHistogramVec(
	prometheus.HistogramOpts{
		Name:    "assistant_run_hook_duration_seconds",
		Help:    "Time spent applying one AssistantRun lifecycle hook phase.",
		Buckets: prometheus.DefBuckets,
	},
	[]string{"phase", "outcome"},
)

func observeWorkerClaim(claim WorkClaim, startedAt time.Time, err error) {
	outcome := "succeeded"
	if err != nil {
		outcome = "failed"
	} else if claim.FencingToken > 1 {
		outcome = "recovered"
	}
	assistantRunWorkerClaims.WithLabelValues(outcome).Inc()
	assistantRunWorkerDuration.WithLabelValues(outcome).Observe(
		time.Since(startedAt).Seconds(),
	)
}

func observeCheckpointAge(checkpoint *Checkpoint, now time.Time) {
	if checkpoint == nil || checkpoint.CreatedAt.IsZero() {
		return
	}
	age := now.Sub(checkpoint.CreatedAt)
	if age >= 0 {
		assistantRunCheckpointAge.Observe(age.Seconds())
	}
}

func observeCancelDuration(startedAt time.Time, err error) {
	outcome := "succeeded"
	if err != nil {
		outcome = "failed"
	}
	assistantRunCancelDuration.WithLabelValues(outcome).Observe(
		time.Since(startedAt).Seconds(),
	)
}

func observeRunTransition(from string, to string) {
	assistantRunStateTransitions.WithLabelValues(from, to).Inc()
	switch to {
	case "completed", "failed", "cancelled", "blocked":
		assistantRunTerminalOutcomes.WithLabelValues(to).Inc()
	}
}

func observeItemClosure(kind string, status string) {
	assistantRunItemClosures.WithLabelValues(kind, status).Inc()
}

func observeLeaseContention(phase string) {
	switch phase {
	case "claim", "heartbeat", "complete", "fenced":
	default:
		phase = "other"
	}
	assistantRunLeaseContentions.WithLabelValues(phase).Inc()
}

func observeCompletionRejected(reason string) {
	switch reason {
	case "verdict", "task_graph", "active_item":
	default:
		reason = "other"
	}
	assistantRunCompletionRejected.WithLabelValues(reason).Inc()
}

func observePresentationProjection(phase string, err error) {
	if phase != "snapshot" && phase != "commit" {
		phase = "other"
	}
	outcome := "succeeded"
	if err != nil {
		outcome = "failed"
	}
	assistantPresentationProjectionTotal.WithLabelValues(phase, outcome).Inc()
}

func observeHookInvocation(
	phase HookPhase,
	decision HookDecision,
	startedAt time.Time,
	err error,
) {
	phaseLabel := string(phase)
	if !validHookPhase(phase) {
		phaseLabel = "other"
	}
	decisionLabel := string(decision)
	switch decision {
	case HookAllow, HookBlock, HookRequireConfirmation:
	default:
		decisionLabel = "other"
	}
	outcome := "succeeded"
	if err != nil {
		outcome = "failed"
	}
	assistantRunHookInvocationTotal.WithLabelValues(
		phaseLabel,
		decisionLabel,
		outcome,
	).Inc()
	assistantRunHookDuration.WithLabelValues(phaseLabel, outcome).Observe(
		time.Since(startedAt).Seconds(),
	)
}
