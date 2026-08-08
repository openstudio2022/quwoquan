// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/native-tool-calling-model-routing/spec.md#gwt-002
package assistant_run_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

type receiptObservabilityBackend struct {
	complete func(ports.ModelCompletionRequest) (ports.ModelCompletionResult, error)
	stream   func(ports.ModelCompletionRequest, func(ports.ModelTextDelta) error) (ports.ModelCompletionResult, error)
}

func (backend *receiptObservabilityBackend) Complete(
	_ context.Context,
	request ports.ModelCompletionRequest,
) (ports.ModelCompletionResult, error) {
	return backend.complete(request)
}

func (backend *receiptObservabilityBackend) Stream(
	_ context.Context,
	request ports.ModelCompletionRequest,
	emit func(ports.ModelTextDelta) error,
) (ports.ModelCompletionResult, error) {
	return backend.stream(request, emit)
}

func TestModelProviderReceiptObservabilityTracksRequestedAndServedTier(t *testing.T) {
	requests := []ports.ModelCompletionRequest{}
	backend := &receiptObservabilityBackend{
		complete: func(request ports.ModelCompletionRequest) (ports.ModelCompletionResult, error) {
			requests = append(requests, request)
			if request.Tier == ports.ModelTierReasoning {
				return ports.ModelCompletionResult{}, ports.ProviderFailure{
					Capability: "model", Reason: ports.ProviderFailureUnavailable,
				}
			}
			return acceptedProviderReceipt("served-balanced", ports.ModelTierBalanced), nil
		},
	}
	provider := orchestration.TierDegradingModelProvider{Backend: backend}
	labels := map[string]string{
		"stage":          "reasoning",
		"requested_tier": "reasoning",
		"served_tier":    "balanced",
		"outcome":        "success",
	}
	completionBefore := gatheredCounterValue(
		t,
		"assistant_model_provider_completion_total",
		labels,
	)
	tokensBefore := gatheredCounterValue(t, "assistant_model_provider_tokens_total", map[string]string{
		"stage": "reasoning", "served_tier": "balanced", "kind": "total",
	})

	result, err := provider.Complete(t.Context(), ports.ModelCompletionRequest{
		Stage: ports.ModelStageReasoning,
		Tier:  ports.ModelTierReasoning,
	})
	if err != nil {
		t.Fatalf("Complete() error = %v", err)
	}
	if len(requests) != 2 || requests[0].Tier != ports.ModelTierReasoning ||
		requests[1].Tier != ports.ModelTierBalanced ||
		result.TierServed != ports.ModelTierBalanced {
		t.Fatalf("degrade requests=%+v result=%+v", requests, result)
	}
	assertCounterIncremented(t, "model completion", completionBefore, gatheredCounterValue(
		t,
		"assistant_model_provider_completion_total",
		labels,
	))
	if delta := gatheredCounterValue(t, "assistant_model_provider_tokens_total", map[string]string{
		"stage": "reasoning", "served_tier": "balanced", "kind": "total",
	}) - tokensBefore; delta != 7 {
		t.Fatalf("accepted token metric delta = %v, want 7", delta)
	}
	assertMetricHasOnlyLabels(t, "assistant_model_provider_completion_total", []string{
		"stage", "requested_tier", "served_tier", "outcome",
	})
	assertMetricHasOnlyLabels(t, "assistant_model_provider_duration_seconds", []string{
		"stage", "requested_tier", "served_tier", "outcome",
	})
	assertMetricHasOnlyLabels(t, "assistant_model_provider_tokens_total", []string{
		"stage", "served_tier", "kind",
	})
}

func TestModelProviderReceiptObservabilityTracksVerificationStage(t *testing.T) {
	backend := &receiptObservabilityBackend{
		complete: func(request ports.ModelCompletionRequest) (ports.ModelCompletionResult, error) {
			return acceptedProviderReceipt("verification-model", request.Tier), nil
		},
	}
	provider := orchestration.TierDegradingModelProvider{Backend: backend}
	labels := map[string]string{
		"stage":          "verification",
		"requested_tier": "reasoning",
		"served_tier":    "reasoning",
		"outcome":        "success",
	}
	before := gatheredCounterValue(t, "assistant_model_provider_completion_total", labels)
	if _, err := provider.Complete(t.Context(), ports.ModelCompletionRequest{
		Stage: ports.ModelStageVerification,
		Tier:  ports.ModelTierReasoning,
	}); err != nil {
		t.Fatalf("verification Complete() error = %v", err)
	}
	assertCounterIncremented(t, "verification model completion", before, gatheredCounterValue(
		t,
		"assistant_model_provider_completion_total",
		labels,
	))
}

func TestModelProviderReceiptValidationFailsClosedForCompleteAndStream(t *testing.T) {
	invalidReceipts := map[string]ports.ModelCompletionResult{
		"missing model id": acceptedProviderReceipt("", ports.ModelTierBalanced),
		"unknown tier":     acceptedProviderReceipt("served", ports.ModelTier("premium")),
		"negative prompt": {
			ModelID: "served", TierServed: ports.ModelTierBalanced,
			Usage: ports.ModelUsage{PromptTokens: -1, CompletionTokens: 1, TotalTokens: 1},
		},
		"negative completion": {
			ModelID: "served", TierServed: ports.ModelTierBalanced,
			Usage: ports.ModelUsage{PromptTokens: 1, CompletionTokens: -1, TotalTokens: 1},
		},
		"negative total": {
			ModelID: "served", TierServed: ports.ModelTierBalanced,
			Usage: ports.ModelUsage{PromptTokens: 1, CompletionTokens: 1, TotalTokens: -1},
		},
		"negative latency": {
			ModelID: "served", TierServed: ports.ModelTierBalanced,
			Usage: ports.ModelUsage{
				PromptTokens: 1, CompletionTokens: 1, TotalTokens: 2, Latency: -time.Millisecond,
			},
		},
		"inconsistent total": {
			ModelID: "served", TierServed: ports.ModelTierBalanced,
			Usage: ports.ModelUsage{PromptTokens: 4, CompletionTokens: 3, TotalTokens: 6},
		},
	}
	for name, receipt := range invalidReceipts {
		t.Run(name, func(t *testing.T) {
			backend := &receiptObservabilityBackend{
				complete: func(ports.ModelCompletionRequest) (ports.ModelCompletionResult, error) {
					return receipt, nil
				},
				stream: func(ports.ModelCompletionRequest, func(ports.ModelTextDelta) error) (ports.ModelCompletionResult, error) {
					return receipt, nil
				},
			}
			provider := orchestration.TierDegradingModelProvider{Backend: backend}
			for operation, invoke := range map[string]func() error{
				"complete": func() error {
					_, err := provider.Complete(t.Context(), ports.ModelCompletionRequest{
						Stage: ports.ModelStageFinal, Tier: ports.ModelTierBalanced,
					})
					return err
				},
				"stream": func() error {
					_, err := provider.Stream(t.Context(), ports.ModelCompletionRequest{
						Stage: ports.ModelStageFinal, Tier: ports.ModelTierBalanced, Stream: true,
					}, nil)
					return err
				},
			} {
				t.Run(operation, func(t *testing.T) {
					labels := map[string]string{
						"stage":          "final",
						"requested_tier": "balanced",
						"served_tier":    "none",
						"outcome":        "invalid_response",
					}
					completionBefore := gatheredCounterValue(
						t,
						"assistant_model_provider_completion_total",
						labels,
					)
					tokensBefore := gatheredCounterValue(
						t,
						"assistant_model_provider_tokens_total",
						map[string]string{
							"stage": "final", "served_tier": "balanced", "kind": "total",
						},
					)
					err := invoke()
					var failure ports.ProviderFailure
					if !errors.As(err, &failure) ||
						failure.Reason != ports.ProviderFailureInvalidResponse {
						t.Fatalf("provider error = %v, want invalid_response", err)
					}
					assertCounterIncremented(
						t,
						"invalid provider receipt",
						completionBefore,
						gatheredCounterValue(
							t,
							"assistant_model_provider_completion_total",
							labels,
						),
					)
					if tokensAfter := gatheredCounterValue(
						t,
						"assistant_model_provider_tokens_total",
						map[string]string{
							"stage": "final", "served_tier": "balanced", "kind": "total",
						},
					); tokensAfter != tokensBefore {
						t.Fatalf("invalid receipt changed accepted token metric by %v", tokensAfter-tokensBefore)
					}
				})
			}
		})
	}
}

func TestModelProviderStreamFailureAfterDeltaIsOneLogicalOutcome(t *testing.T) {
	attempts := 0
	backend := &receiptObservabilityBackend{
		stream: func(
			_ ports.ModelCompletionRequest,
			emit func(ports.ModelTextDelta) error,
		) (ports.ModelCompletionResult, error) {
			attempts++
			if err := emit(ports.ModelTextDelta{Text: "partial"}); err != nil {
				return ports.ModelCompletionResult{}, err
			}
			return ports.ModelCompletionResult{}, ports.ProviderFailure{
				Capability: "model", Reason: ports.ProviderFailureTimeout,
			}
		},
	}
	provider := orchestration.TierDegradingModelProvider{Backend: backend}
	labels := map[string]string{
		"stage":          "final",
		"requested_tier": "reasoning",
		"served_tier":    "none",
		"outcome":        "timeout",
	}
	before := gatheredCounterValue(t, "assistant_model_provider_completion_total", labels)
	_, err := provider.Stream(t.Context(), ports.ModelCompletionRequest{
		Stage: ports.ModelStageFinal, Tier: ports.ModelTierReasoning, Stream: true,
	}, func(ports.ModelTextDelta) error { return nil })
	if err == nil || attempts != 1 {
		t.Fatalf("Stream() error=%v attempts=%d, want one failed logical call", err, attempts)
	}
	assertCounterIncremented(t, "streamed model failure", before, gatheredCounterValue(
		t,
		"assistant_model_provider_completion_total",
		labels,
	))
}

func TestModelProviderAllTiersUnavailableIsOneLogicalOutcome(t *testing.T) {
	attempts := 0
	backend := &receiptObservabilityBackend{
		complete: func(ports.ModelCompletionRequest) (ports.ModelCompletionResult, error) {
			attempts++
			return ports.ModelCompletionResult{}, ports.ProviderFailure{
				Capability: "model", Reason: ports.ProviderFailureUnavailable,
			}
		},
	}
	provider := orchestration.TierDegradingModelProvider{Backend: backend}
	labels := map[string]string{
		"stage":          "reasoning",
		"requested_tier": "reasoning",
		"served_tier":    "none",
		"outcome":        "unavailable",
	}
	before := gatheredCounterValue(t, "assistant_model_provider_completion_total", labels)
	if _, err := provider.Complete(t.Context(), ports.ModelCompletionRequest{
		Stage: ports.ModelStageReasoning, Tier: ports.ModelTierReasoning,
	}); err == nil || attempts != 3 {
		t.Fatalf("Complete() error=%v attempts=%d, want one call over three tiers", err, attempts)
	}
	assertCounterIncremented(t, "unavailable model completion", before, gatheredCounterValue(
		t,
		"assistant_model_provider_completion_total",
		labels,
	))
}

func acceptedProviderReceipt(modelID string, tier ports.ModelTier) ports.ModelCompletionResult {
	return ports.ModelCompletionResult{
		Content: "ok", ModelID: modelID, TierServed: tier,
		Usage: ports.ModelUsage{
			PromptTokens: 4, CompletionTokens: 3, TotalTokens: 7,
			Latency: time.Millisecond,
		},
	}
}

func assertMetricHasOnlyLabels(t *testing.T, familyName string, want []string) {
	t.Helper()
	families, err := prometheus.DefaultGatherer.Gather()
	if err != nil {
		t.Fatalf("Gather() error = %v", err)
	}
	for _, family := range families {
		if family.GetName() != familyName {
			continue
		}
		for _, metric := range family.GetMetric() {
			if len(metric.GetLabel()) != len(want) {
				t.Fatalf("%s label count=%d, want %d", familyName, len(metric.GetLabel()), len(want))
			}
			allowed := make(map[string]struct{}, len(want))
			for _, name := range want {
				allowed[name] = struct{}{}
			}
			for _, label := range metric.GetLabel() {
				if _, ok := allowed[label.GetName()]; !ok {
					t.Fatalf("%s labels are not bounded canonical set: %v", familyName, metric.GetLabel())
				}
			}
		}
		return
	}
	t.Fatalf("metric family %s is missing", familyName)
}
