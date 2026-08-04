// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/native-tool-calling-model-routing/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-003
package assistant_run

import (
	"context"
	"errors"
	"strings"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

const catalogBridgeDeclaredTool = "canonical_evidence_reader"

type catalogBridgeModelBackend struct {
	native   bool
	result   ports.ModelCompletionResult
	requests []ports.ModelCompletionRequest
}

func (b *catalogBridgeModelBackend) Complete(
	_ context.Context,
	request ports.ModelCompletionRequest,
) (ports.ModelCompletionResult, error) {
	b.requests = append(b.requests, request)
	return b.result, nil
}

func (b *catalogBridgeModelBackend) Stream(
	ctx context.Context,
	request ports.ModelCompletionRequest,
	_ func(ports.ModelTextDelta) error,
) (ports.ModelCompletionResult, error) {
	return b.Complete(ctx, request)
}

func (b *catalogBridgeModelBackend) SupportsNativeToolCalling() bool {
	return b.native
}

func TestModelToolCatalogBridgeAcceptsAnyCurrentlyDeclaredConformingTool(
	t *testing.T,
) {
	for _, test := range []struct {
		name   string
		native bool
		result ports.ModelCompletionResult
	}{
		{
			name:   "native",
			native: true,
			result: ports.ModelCompletionResult{
				Content: `{"nextAction":"tool_call","stageNarrative":"你需要继续核验当前事实。"}`,
				ToolCalls: []ports.ModelToolCall{{
					ID:        "call_catalog",
					Name:      catalogBridgeDeclaredTool,
					Arguments: `{"subject":"current fact"}`,
				}},
			},
		},
		{
			name: "structured_fallback",
			result: ports.ModelCompletionResult{Content: `{
				"nextAction":"tool_call",
				"toolName":"canonical_evidence_reader",
				"toolInput":{"subject":"current fact"},
				"stageNarrative":"你需要继续核验当前事实。"
			}`},
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			backend := &catalogBridgeModelBackend{
				native: test.native,
				result: test.result,
			}
			response, err := (orchestration.ProviderBackedModelProvider{
				Backend: backend,
			}).Complete(t.Context(), catalogBridgeModelRequest())
			if err != nil {
				t.Fatalf("Complete() error = %v", err)
			}
			if response.StructuredDelta["toolName"] != catalogBridgeDeclaredTool {
				t.Fatalf("structured toolName = %v", response.StructuredDelta["toolName"])
			}
			if len(backend.requests) != 1 {
				t.Fatalf("requests = %d, want 1", len(backend.requests))
			}
			request := backend.requests[0]
			if len(request.Messages) == 0 ||
				!strings.Contains(request.Messages[0].Content, "不可信") ||
				!strings.Contains(request.Messages[0].Content, "ask_user") {
				t.Fatalf("reasoning security/ask_user boundary missing: %q", request.Messages)
			}
			if test.native {
				if request.ToolChoice != ports.ModelToolChoiceAuto ||
					len(request.Tools) != 1 ||
					request.Tools[0].Name != catalogBridgeDeclaredTool ||
					request.Tools[0].Description != "读取当前声明范围内的可核验事实。" ||
					request.Tools[0].Parameters["type"] != "object" {
					t.Fatalf("native catalog projection = %+v", request)
				}
				return
			}
			if len(request.Tools) != 0 || request.ToolChoice != "" {
				t.Fatalf("structured fallback leaked native tools: %+v", request)
			}
			systemPrompt := request.Messages[0].Content
			for _, fragment := range []string{
				catalogBridgeDeclaredTool,
				"读取当前声明范围内的可核验事实。",
				`"subject"`,
			} {
				if !strings.Contains(systemPrompt, fragment) {
					t.Fatalf("structured prompt missing %q: %s", fragment, systemPrompt)
				}
			}
		})
	}
}

func TestModelToolCatalogBridgeRejectsUndeclaredToolAcrossProtocols(
	t *testing.T,
) {
	for _, test := range []struct {
		name   string
		native bool
		result ports.ModelCompletionResult
	}{
		{
			name:   "native",
			native: true,
			result: ports.ModelCompletionResult{
				Content: `{"nextAction":"tool_call","stageNarrative":"你需要继续核验。"}`,
				ToolCalls: []ports.ModelToolCall{{
					ID:        "call_undeclared",
					Name:      "undeclared_tool",
					Arguments: `{}`,
				}},
			},
		},
		{
			name: "structured_fallback",
			result: ports.ModelCompletionResult{Content: `{
				"nextAction":"tool_call",
				"toolName":"undeclared_tool",
				"toolInput":{},
				"stageNarrative":"你需要继续核验。"
			}`},
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			backend := &catalogBridgeModelBackend{
				native: test.native,
				result: test.result,
			}
			_, err := (orchestration.ProviderBackedModelProvider{
				Backend: backend,
			}).Complete(t.Context(), catalogBridgeModelRequest())
			var failure ports.ProviderFailure
			if !errors.As(err, &failure) ||
				failure.Capability != "model" ||
				failure.Reason != ports.ProviderFailureInvalidResponse {
				t.Fatalf("error = %v, want fail-closed invalid model response", err)
			}
		})
	}
}

func TestModelToolCatalogBridgePreservesAskUserAcrossProtocols(t *testing.T) {
	for _, native := range []bool{true, false} {
		name := "structured_fallback"
		if native {
			name = "native"
		}
		t.Run(name, func(t *testing.T) {
			backend := &catalogBridgeModelBackend{
				native: native,
				result: ports.ModelCompletionResult{Content: `{
					"nextAction":"ask_user",
					"askUser":{"slotId":"scope","prompt":"你要核验哪个范围？","required":true},
					"stageNarrative":"你需要先确认范围。"
				}`},
			}
			response, err := (orchestration.ProviderBackedModelProvider{
				Backend: backend,
			}).Complete(t.Context(), catalogBridgeModelRequest())
			if err != nil {
				t.Fatalf("Complete() error = %v", err)
			}
			askUser, ok := response.StructuredDelta["askUser"].(map[string]any)
			if !ok || askUser["prompt"] != "你要核验哪个范围？" {
				t.Fatalf("askUser = %#v", response.StructuredDelta["askUser"])
			}
			if response.StructuredDelta["toolName"] != nil {
				t.Fatalf("ask_user unexpectedly selected tool %v", response.StructuredDelta["toolName"])
			}
		})
	}
}

func catalogBridgeModelRequest() orchestration.ModelRequest {
	return orchestration.ModelRequest{
		Stage:           "reasoning",
		Prompt:          "核验当前事实",
		UserQuestion:    "请核验",
		ProblemClass:    "complex_reasoning",
		SearchIntensity: "medium",
		ToolCatalog: []ports.ModelToolDefinition{{
			Name:        catalogBridgeDeclaredTool,
			Description: "读取当前声明范围内的可核验事实。",
			Parameters: map[string]any{
				"type":                 "object",
				"additionalProperties": false,
				"properties": map[string]any{
					"subject": map[string]any{"type": "string"},
				},
				"required": []string{"subject"},
			},
		}},
	}
}
