// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/native-tool-calling-model-routing/spec.md#gwt-002
package local_contract

import (
	"context"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
)

type recordingTierBackend struct {
	attempted    []ports.ModelTier
	failUntil    map[ports.ModelTier]bool
	failureCause ports.ProviderFailureReason
	emitBefore   string
}

func (b *recordingTierBackend) Complete(
	_ context.Context,
	request ports.ModelCompletionRequest,
) (ports.ModelCompletionResult, error) {
	b.attempted = append(b.attempted, request.Tier)
	if b.failUntil[request.Tier] {
		return ports.ModelCompletionResult{}, ports.ProviderFailure{
			Capability: "model",
			Reason:     b.failureCause,
		}
	}
	return ports.ModelCompletionResult{
		Content:    "ok",
		TierServed: request.Tier,
	}, nil
}

func (b *recordingTierBackend) Stream(
	_ context.Context,
	request ports.ModelCompletionRequest,
	emit func(ports.ModelTextDelta) error,
) (ports.ModelCompletionResult, error) {
	b.attempted = append(b.attempted, request.Tier)
	if b.failUntil[request.Tier] {
		if b.emitBefore != "" && emit != nil {
			if err := emit(ports.ModelTextDelta{Text: b.emitBefore}); err != nil {
				return ports.ModelCompletionResult{}, err
			}
		}
		return ports.ModelCompletionResult{}, ports.ProviderFailure{
			Capability: "model",
			Reason:     b.failureCause,
		}
	}
	return ports.ModelCompletionResult{
		Content:    "ok",
		TierServed: request.Tier,
	}, nil
}

func TestTierDegradeContinuesRunOnUnavailableTier(t *testing.T) {
	backend := &recordingTierBackend{
		failUntil: map[ports.ModelTier]bool{
			ports.ModelTierReasoning: true,
		},
		failureCause: ports.ProviderFailureUnavailable,
	}
	provider := orchestration.TierDegradingModelProvider{Backend: backend}
	result, err := provider.Complete(context.Background(), ports.ModelCompletionRequest{
		Stage: ports.ModelStageFinal,
		Tier:  ports.ModelTierReasoning,
	})
	if err != nil {
		t.Fatalf("Complete() error = %v", err)
	}
	if result.TierServed != ports.ModelTierBalanced {
		t.Fatalf("tierServed=%q want balanced after degrade", result.TierServed)
	}
	if len(backend.attempted) != 2 ||
		backend.attempted[0] != ports.ModelTierReasoning ||
		backend.attempted[1] != ports.ModelTierBalanced {
		t.Fatalf("attempted=%v want reasoning then balanced", backend.attempted)
	}
}

func TestTierDegradeDoesNotMaskProtocolFailure(t *testing.T) {
	backend := &recordingTierBackend{
		failUntil: map[ports.ModelTier]bool{
			ports.ModelTierReasoning: true,
			ports.ModelTierBalanced:  true,
			ports.ModelTierFast:      true,
		},
		failureCause: ports.ProviderFailureInvalidResponse,
	}
	provider := orchestration.TierDegradingModelProvider{Backend: backend}
	if _, err := provider.Complete(context.Background(), ports.ModelCompletionRequest{
		Stage: ports.ModelStageFinal,
		Tier:  ports.ModelTierReasoning,
	}); err == nil {
		t.Fatal("invalid response must surface instead of degrading")
	}
	if len(backend.attempted) != 1 {
		t.Fatalf("attempted=%v want a single attempt for deterministic failure", backend.attempted)
	}
}

func TestTierDegradeStopsAfterStreamingStarted(t *testing.T) {
	backend := &recordingTierBackend{
		failUntil: map[ports.ModelTier]bool{
			ports.ModelTierReasoning: true,
		},
		failureCause: ports.ProviderFailureUnavailable,
		emitBefore:   "已经发给用户的片段",
	}
	provider := orchestration.TierDegradingModelProvider{Backend: backend}
	_, err := provider.Stream(
		context.Background(),
		ports.ModelCompletionRequest{
			Stage:  ports.ModelStageFinal,
			Tier:   ports.ModelTierReasoning,
			Stream: true,
		},
		func(ports.ModelTextDelta) error { return nil },
	)
	if err == nil {
		t.Fatal("degrade must not restart a stream that already emitted text")
	}
	if len(backend.attempted) != 1 {
		t.Fatalf("attempted=%v want a single streaming attempt", backend.attempted)
	}
}
