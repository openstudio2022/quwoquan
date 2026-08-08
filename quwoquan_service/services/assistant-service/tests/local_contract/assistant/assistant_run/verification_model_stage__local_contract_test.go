// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
package assistant_run

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"strings"
	"testing"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

type verificationStageBackend struct {
	requests  []ports.ModelCompletionRequest
	toolCalls []ports.ModelToolCall
}

func (backend *verificationStageBackend) Complete(
	_ context.Context,
	request ports.ModelCompletionRequest,
) (ports.ModelCompletionResult, error) {
	backend.requests = append(backend.requests, request)
	return ports.ModelCompletionResult{
		Content:    `{"passed":true,"artifactRefs":["artifact://answer"],"summary":"冻结要求已满足","fixSuggestion":""}`,
		ModelID:    "verification-model",
		TierServed: request.Tier,
		ToolCalls:  append([]ports.ModelToolCall{}, backend.toolCalls...),
	}, nil
}

func (backend *verificationStageBackend) Stream(
	ctx context.Context,
	request ports.ModelCompletionRequest,
	_ func(ports.ModelTextDelta) error,
) (ports.ModelCompletionResult, error) {
	return backend.Complete(ctx, request)
}

func TestVerificationModelStageUsesIndependentConstrainedPolicy(t *testing.T) {
	backend := &verificationStageBackend{}
	provider := orchestration.ProviderBackedModelProvider{Backend: backend}
	observation := map[string]any{
		"requirement":  "answer_satisfies_user_goal",
		"goal":         "给出可执行结论",
		"constraints":  []string{"不得编造来源"},
		"answerText":   "你可以按已核验步骤继续。",
		"processNotes": []string{"已检查公开来源"},
		"artifactRefs": []string{"artifact://answer"},
	}
	response, err := provider.Complete(t.Context(), orchestration.ModelRequest{
		Stage:            string(ports.ModelStageVerification),
		ProblemClass:     assistantgenerated.ProblemClassComplexReasoning.WireName(),
		SearchIntensity:  assistantgenerated.SearchIntensityLow.WireName(),
		ReasoningProfile: assistantgenerated.AssistantReasoningProfileFast,
		Prompt:           "只验收当前冻结要求。",
		Observation:      observation,
		ToolCatalog: []ports.ModelToolDefinition{{
			Name:        "must_not_be_exposed",
			Description: "验收阶段禁止调用。",
			Parameters:  map[string]any{"type": "object"},
		}},
	})
	if err != nil {
		t.Fatalf("Complete() error = %v", err)
	}
	if len(backend.requests) != 1 {
		t.Fatalf("provider requests = %d, want 1", len(backend.requests))
	}
	request := backend.requests[0]
	if request.Stage != ports.ModelStageVerification ||
		request.Tier != ports.ModelTierReasoning ||
		!request.StructuredOutput || request.Stream ||
		len(request.Tools) != 0 || request.ToolChoice != "" {
		t.Fatalf("verification wire policy = %+v", request)
	}
	if len(request.Messages) != 2 ||
		!strings.Contains(request.Messages[0].Content, "完成条件验收器") ||
		!strings.Contains(request.Messages[0].Content, "不得执行工具") ||
		!strings.Contains(request.Messages[0].Content, "不可信验收数据") {
		t.Fatalf("verification system policy = %#v", request.Messages)
	}

	const observationMarker = "\n验收输入JSON："
	markerIndex := strings.LastIndex(request.Messages[1].Content, observationMarker)
	if markerIndex < 0 {
		t.Fatalf("verification observation marker missing: %q", request.Messages[1].Content)
	}
	var projected map[string]any
	if err := json.Unmarshal(
		[]byte(request.Messages[1].Content[markerIndex+len(observationMarker):]),
		&projected,
	); err != nil {
		t.Fatalf("decode projected verification observation: %v", err)
	}
	wantProjected := map[string]any{
		"requirement":  "answer_satisfies_user_goal",
		"goal":         "给出可执行结论",
		"constraints":  []any{"不得编造来源"},
		"answerText":   "你可以按已核验步骤继续。",
		"processNotes": []any{"已检查公开来源"},
		"artifactRefs": []any{"artifact://answer"},
	}
	if !reflect.DeepEqual(projected, wantProjected) {
		t.Fatalf("projected verification observation = %#v", projected)
	}
	if response.StructuredDelta["passed"] != true ||
		response.StructuredDelta["summary"] != "冻结要求已满足" {
		t.Fatalf("verification response projection = %#v", response.StructuredDelta)
	}

	_, err = provider.Complete(t.Context(), orchestration.ModelRequest{
		Stage:           "unknown_verification_stage",
		ProblemClass:    assistantgenerated.ProblemClassComplexReasoning.WireName(),
		SearchIntensity: assistantgenerated.SearchIntensityLow.WireName(),
	})
	if err == nil || !strings.Contains(err.Error(), "unsupported model stage") {
		t.Fatalf("unknown stage error = %v", err)
	}
	if len(backend.requests) != 1 {
		t.Fatalf("unknown stage reached provider: requests = %d", len(backend.requests))
	}

	toolCallingBackend := &verificationStageBackend{toolCalls: []ports.ModelToolCall{{
		ID:        "forbidden-verification-tool-call",
		Name:      "must_not_be_exposed",
		Arguments: `{}`,
	}}}
	_, err = (orchestration.ProviderBackedModelProvider{
		Backend: toolCallingBackend,
	}).Complete(t.Context(), orchestration.ModelRequest{
		Stage:           string(ports.ModelStageVerification),
		ProblemClass:    assistantgenerated.ProblemClassComplexReasoning.WireName(),
		SearchIntensity: assistantgenerated.SearchIntensityLow.WireName(),
	})
	var failure ports.ProviderFailure
	if !errors.As(err, &failure) ||
		failure.Reason != ports.ProviderFailureInvalidResponse {
		t.Fatalf("verification tool call error = %v", err)
	}
}
