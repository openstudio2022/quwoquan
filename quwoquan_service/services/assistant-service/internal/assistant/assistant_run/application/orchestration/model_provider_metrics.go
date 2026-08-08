package orchestration

import (
	"errors"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

var assistantModelProviderCompletionTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_model_provider_completion_total",
		Help: "Logical model completions by bounded stage, requested tier, served tier and outcome.",
	},
	[]string{"stage", "requested_tier", "served_tier", "outcome"},
)

var assistantModelProviderDurationSeconds = promauto.NewHistogramVec(
	prometheus.HistogramOpts{
		Name: "assistant_model_provider_duration_seconds",
		Help: "End-to-end duration of one logical model completion including bounded tier degradation.",
		Buckets: []float64{
			0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60, 120,
		},
	},
	[]string{"stage", "requested_tier", "served_tier", "outcome"},
)

var assistantModelProviderTokensTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_model_provider_tokens_total",
		Help: "Accepted provider receipt tokens by bounded stage, served tier and token kind.",
	},
	[]string{"stage", "served_tier", "kind"},
)

func observeModelProviderCompletion(
	request ports.ModelCompletionRequest,
	result ports.ModelCompletionResult,
	startedAt time.Time,
	err error,
) {
	stage := boundedModelStage(request.Stage)
	requestedTier := boundedModelTier(request.Tier)
	servedTier := "none"
	if err == nil {
		servedTier = boundedModelTier(result.TierServed)
	}
	outcome := boundedModelProviderOutcome(err)
	labels := []string{stage, requestedTier, servedTier, outcome}
	assistantModelProviderCompletionTotal.WithLabelValues(labels...).Inc()
	assistantModelProviderDurationSeconds.WithLabelValues(labels...).Observe(
		time.Since(startedAt).Seconds(),
	)
	if err != nil {
		return
	}
	assistantModelProviderTokensTotal.WithLabelValues(
		stage,
		servedTier,
		"prompt",
	).Add(float64(result.Usage.PromptTokens))
	assistantModelProviderTokensTotal.WithLabelValues(
		stage,
		servedTier,
		"completion",
	).Add(float64(result.Usage.CompletionTokens))
	assistantModelProviderTokensTotal.WithLabelValues(
		stage,
		servedTier,
		"total",
	).Add(float64(result.Usage.TotalTokens))
}

func boundedModelStage(stage ports.ModelStage) string {
	switch stage {
	case ports.ModelStageSkillSelection,
		ports.ModelStageOrchestration,
		ports.ModelStageReasoning,
		ports.ModelStageEvidenceProcessing,
		ports.ModelStageCompaction,
		ports.ModelStagePresentation,
		ports.ModelStageVerification,
		ports.ModelStageFinal:
		return string(stage)
	default:
		return "other"
	}
}

func boundedModelTier(tier ports.ModelTier) string {
	if canonicalModelTier(tier) {
		return string(tier)
	}
	return "other"
}

func boundedModelProviderOutcome(err error) string {
	if err == nil {
		return "success"
	}
	var failure ports.ProviderFailure
	if !errors.As(err, &failure) || failure.Capability != "model" {
		return "other"
	}
	switch failure.Reason {
	case ports.ProviderFailureUnavailable,
		ports.ProviderFailureTimeout,
		ports.ProviderFailureInvalidResponse:
		return string(failure.Reason)
	default:
		return "other"
	}
}
