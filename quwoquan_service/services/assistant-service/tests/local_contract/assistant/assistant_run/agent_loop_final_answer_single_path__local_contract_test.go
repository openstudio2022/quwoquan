// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/native-tool-calling-model-routing/spec.md#gwt-002
package assistant_run_test

import (
	"context"
	"reflect"
	"testing"
	"time"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

type finalAnswerSinglePathBackend struct {
	streamAttempts []ports.ModelTier
	completeCalls  int
}

func (backend *finalAnswerSinglePathBackend) Complete(
	_ context.Context,
	request ports.ModelCompletionRequest,
) (ports.ModelCompletionResult, error) {
	backend.completeCalls++
	return ports.ModelCompletionResult{
		Content:      "你可以继续当前安排。",
		FinishReason: "stop",
		ModelID:      "must-not-be-called",
		TierServed:   request.Tier,
		Usage: ports.ModelUsage{
			PromptTokens:     1,
			CompletionTokens: 1,
			TotalTokens:      2,
			Latency:          time.Millisecond,
		},
	}, nil
}

func (backend *finalAnswerSinglePathBackend) Stream(
	_ context.Context,
	request ports.ModelCompletionRequest,
	_ func(ports.ModelTextDelta) error,
) (ports.ModelCompletionResult, error) {
	backend.streamAttempts = append(backend.streamAttempts, request.Tier)
	return ports.ModelCompletionResult{}, ports.ProviderFailure{
		Capability: "model",
		Reason:     ports.ProviderFailureUnavailable,
	}
}

func TestFinalAnswerDoesNotRestartWithCompleteAfterStreamTiersExhausted(t *testing.T) {
	backend := &finalAnswerSinglePathBackend{}
	runtime := orchestration.ReactRuntime{
		Model: orchestration.ProviderBackedModelProvider{
			Backend: orchestration.TierDegradingModelProvider{Backend: backend},
		},
	}
	deltas := make([]string, 0)
	response, streamed, err := runtime.SynthesizeSubagentAnswer(
		t.Context(),
		assistant.AssistantTurn{
			TurnID:  "run-final-answer-single-path",
			TraceID: "trace-final-answer-single-path",
			Input: assistant.AssistantTurnInput{
				Text: "请合并子任务结论",
			},
		},
		orchestration.SkillSelection{
			SkillID:         "final-answer-single-path",
			ProblemClass:    assistantgenerated.ProblemClassComplexReasoning.WireName(),
			SearchIntensity: assistantgenerated.SearchIntensityHigh.WireName(),
		},
		map[string]any{"skillRuns": []any{}},
		func(delta ports.ModelTextDelta) error {
			deltas = append(deltas, delta.Text)
			return nil
		},
	)
	if err == nil {
		t.Fatal("all streaming tiers unavailable must fail without starting another answer path")
	}
	if streamed || response.Text != "" || len(deltas) != 0 {
		t.Fatalf(
			"failed final stream leaked an answer: streamed=%v response=%q deltas=%v",
			streamed,
			response.Text,
			deltas,
		)
	}
	if backend.completeCalls != 0 {
		t.Fatalf("Complete calls=%d want 0 after Stream exhausted its retry chain", backend.completeCalls)
	}
	wantAttempts := []ports.ModelTier{
		ports.ModelTierReasoning,
		ports.ModelTierBalanced,
		ports.ModelTierFast,
	}
	if !reflect.DeepEqual(backend.streamAttempts, wantAttempts) {
		t.Fatalf("Stream attempts=%v want %v", backend.streamAttempts, wantAttempts)
	}
}
