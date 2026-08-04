// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-003
package assistant_run_test

import (
	"context"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	runruntime "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

func TestResearchBudgetUsesMetadataAndCommitsNavigationExactlyOnce(t *testing.T) {
	model := &metadataResearchModel{toolName: "canonical_navigator"}
	tools := &metadataResearchTools{
		metadata: map[string]toolpkg.Metadata{
			"canonical_navigator": metadataResearchNavigateTool(),
		},
	}
	ctx := metadataResearchExecutionContext(t, model, 4, 2, 1)
	result, err := (orchestration.ReactRuntime{
		Model: model,
		Tools: tools,
	}).Run(ctx, metadataResearchTurn(), orchestration.SkillSelection{
		SkillID:      "metadata_driven_research",
		DomainID:     "knowledge",
		ToolPolicy:   []string{"canonical_navigator"},
		MaxToolCalls: 1,
	})
	if err != nil {
		t.Fatalf("metadata-driven navigate: %v", err)
	}
	if tools.executions != 1 || result.StopReason != "observation_sufficient" {
		t.Fatalf("executions=%d result=%+v", tools.executions, result)
	}
	input := tools.lastInput["destination"].(map[string]any)
	if input["type"] != "child" || input["ref"] != "document-link-1" {
		t.Fatalf("executed input=%#v", tools.lastInput)
	}
}

func TestResearchBudgetBoundsArbitraryDiscoverToolFromMetadata(t *testing.T) {
	model := &metadataResearchModel{toolName: "canonical_discoverer"}
	tools := &metadataResearchTools{
		metadata: map[string]toolpkg.Metadata{
			"canonical_discoverer": metadataResearchDiscoverTool(),
		},
		result: map[string]any{
			"summary": "bounded evidence",
			"references": []any{
				map[string]any{"sourceId": "source-1", "title": "one"},
				map[string]any{"sourceId": "source-2", "title": "two"},
			},
			"evidenceAssessment": map[string]any{
				"status":             "accepted",
				"evidenceSufficient": true,
				"replanRequired":     false,
				"sourceIds":          []any{"source-1", "source-2"},
			},
		},
	}
	ctx := metadataResearchExecutionContext(t, model, 1, 2, 1)
	result, err := (orchestration.ReactRuntime{
		Model: model,
		Tools: tools,
	}).Run(ctx, metadataResearchTurn(), orchestration.SkillSelection{
		SkillID:      "metadata_driven_research",
		DomainID:     "knowledge",
		ToolPolicy:   []string{"canonical_discoverer"},
		MaxToolCalls: 1,
	})
	if err != nil {
		t.Fatalf("metadata-driven discover: %v", err)
	}
	branches, ok := tools.lastInput["branches"].([]any)
	if !ok || len(branches) != 1 {
		t.Fatalf("parallel branches were not metadata-bounded: %#v", tools.lastInput)
	}
	if len(result.Steps) != 1 {
		t.Fatalf("steps=%+v", result.Steps)
	}
	references, ok := result.Steps[0].Tool.Completed.Result["references"].([]map[string]any)
	if !ok || len(references) != 1 || references[0]["sourceId"] != "source-1" {
		t.Fatalf("bounded references=%#v", result.Steps[0].Tool.Completed.Result["references"])
	}
}

func TestResearchRuntimeRejectsDeclarationWithoutCanonicalMetadata(t *testing.T) {
	model := &metadataResearchModel{toolName: "undeclared_metadata"}
	tools := &metadataResearchTools{declarations: []ports.ModelToolDefinition{{
		Name:       "undeclared_metadata",
		Parameters: toolpkg.ObjectSchema(map[string]any{}),
	}}}
	_, err := (orchestration.ReactRuntime{
		Model: model,
		Tools: tools,
	}).Run(t.Context(), metadataResearchTurn(), orchestration.SkillSelection{
		SkillID:    "metadata_driven_research",
		ToolPolicy: []string{"undeclared_metadata"},
	})
	if err == nil {
		t.Fatal("tool declaration without canonical metadata was accepted")
	}
	if model.calls != 0 || tools.executions != 0 {
		t.Fatalf("modelCalls=%d executions=%d", model.calls, tools.executions)
	}
}

func TestResearchRuntimeRejectsUnknownToolFromSkillAllowlistBeforeModelCall(t *testing.T) {
	model := &metadataResearchModel{toolName: "unknown_vertical_reader"}
	_, err := (orchestration.ReactRuntime{
		Model: model,
		Tools: orchestration.DefaultToolCoordinator{
			Registry: toolpkg.NewRegistry(),
		},
	}).Run(t.Context(), metadataResearchTurn(), orchestration.SkillSelection{
		SkillID:    "metadata_driven_research",
		ToolPolicy: []string{"unknown_vertical_reader"},
	})
	if err == nil {
		t.Fatal("unknown Skill capability tool was silently dropped")
	}
	if model.calls != 0 {
		t.Fatalf("model was called %d time(s) before tool policy validation", model.calls)
	}
}

type metadataResearchModel struct {
	toolName string
	calls    int
}

func (model *metadataResearchModel) ModelExecutionCapabilities() orchestration.ModelExecutionCapabilities {
	return orchestration.ModelExecutionCapabilities{
		ToolCalling:     true,
		ParallelTools:   true,
		ReasoningEffort: true,
	}
}

func (model *metadataResearchModel) Complete(
	_ context.Context,
	request orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	model.calls++
	switch request.Stage {
	case "reasoning":
		input := map[string]any{}
		if model.toolName == "canonical_navigator" {
			input["destination"] = map[string]any{
				"type": "child",
				"ref":  "document-link-1",
			}
		} else {
			input["query"] = "杭州旅行证据"
			input["branches"] = []any{"住宿", "餐饮", "交通"}
		}
		return orchestration.ModelResponse{StructuredDelta: map[string]any{
			"nextAction": "tool_call",
			"toolName":   model.toolName,
			"toolInput":  input,
		}}, nil
	case "evidence_processing":
		return orchestration.ModelResponse{StructuredDelta: map[string]any{
			"evidenceSufficient": true,
			"retrievalProcessing": map[string]any{
				"processingSummary": "证据充分",
			},
		}}, nil
	case "final":
		return orchestration.ModelResponse{
			Text: "已完成证据核验。",
			StructuredDelta: map[string]any{
				"userMarkdown": "已完成证据核验。",
			},
		}, nil
	default:
		return orchestration.ModelResponse{}, nil
	}
}

type metadataResearchTools struct {
	metadata     map[string]toolpkg.Metadata
	declarations []ports.ModelToolDefinition
	result       map[string]any
	executions   int
	lastInput    map[string]any
}

func (tools *metadataResearchTools) ModelToolDeclarations(
	allowed []string,
) []ports.ModelToolDefinition {
	if tools.declarations != nil {
		return append([]ports.ModelToolDefinition(nil), tools.declarations...)
	}
	definitions := make([]ports.ModelToolDefinition, 0, len(allowed))
	for _, name := range allowed {
		metadata, found := tools.metadata[name]
		if !found {
			continue
		}
		definitions = append(definitions, ports.ModelToolDefinition{
			Name:        name,
			Description: metadata.Description,
			Parameters:  metadata.InputSchema,
		})
	}
	return definitions
}

func (tools *metadataResearchTools) ToolMetadata(
	name string,
) (toolpkg.Metadata, bool) {
	metadata, found := tools.metadata[name]
	return metadata, found
}

func (tools *metadataResearchTools) Execute(
	_ context.Context,
	request orchestration.ToolRequest,
) (orchestration.ToolExecution, error) {
	tools.executions++
	tools.lastInput = request.Input
	result := tools.result
	if result == nil {
		result = map[string]any{
			"summary": "navigated",
			"reference": map[string]any{
				"sourceId": "source-1",
				"title":    "canonical child",
			},
			"evidenceAssessment": map[string]any{
				"status":             "accepted",
				"evidenceSufficient": true,
				"replanRequired":     false,
				"sourceIds":          []any{"source-1"},
			},
		}
	}
	return orchestration.ToolExecution{
		Requested: assistant.ToolUse{
			ToolName: request.ToolName,
			Input:    request.Input,
		},
		Completed: assistant.ToolUse{
			ToolName: request.ToolName,
			Input:    request.Input,
			Result:   result,
			Status:   "completed",
		},
	}, nil
}

func metadataResearchDiscoverTool() toolpkg.Metadata {
	return toolpkg.Metadata{
		ToolName:    "canonical_discoverer",
		Description: "Discover evidence with bounded parallel branches.",
		InputSchema: toolpkg.ObjectSchema(map[string]any{
			"query":    toolpkg.StringProperty("primary query"),
			"branches": map[string]any{"type": "array", "items": map[string]any{"type": "string"}},
		}, "query"),
		Research: toolpkg.ResearchPolicy{
			Operation:          toolpkg.ResearchOperationDiscover,
			ParallelInputField: "branches",
		},
	}
}

func metadataResearchNavigateTool() toolpkg.Metadata {
	return toolpkg.Metadata{
		ToolName:    "canonical_navigator",
		Description: "Navigate one canonical evidence target.",
		InputSchema: toolpkg.ObjectSchema(map[string]any{
			"destination": map[string]any{"type": "object"},
		}, "destination"),
		Research: toolpkg.ResearchPolicy{
			Operation:                 toolpkg.ResearchOperationNavigate,
			TargetInputField:          "destination",
			TargetKindField:           "type",
			TargetValueField:          "ref",
			ReusableSourceTargetKinds: []string{"ledger_source"},
			ChildTargetKinds:          []string{"child"},
		},
	}
}

func metadataResearchExecutionContext(
	t *testing.T,
	model orchestration.ModelProvider,
	maxSources int,
	sourceBreadth int,
	sourceDepth int,
) context.Context {
	t.Helper()
	profile := runruntime.ReasoningProfileConfig{
		Profile: generated.AssistantReasoningProfileDeep,
		Capability: runruntime.CapabilityRequirements{
			ToolCalling:     true,
			ParallelTools:   true,
			ReasoningEffort: true,
		},
		Budget: runruntime.ReasoningBudget{
			MaxDuration:  time.Minute,
			MaxTokens:    10_000,
			MaxCostUnits: 10_000,
			MaxToolCalls: 3,
			MaxSubagents: 0,
			MaxSources:   maxSources,
		},
		ReflectionEverySteps: 1,
		SourceBreadth:        sourceBreadth,
		SourceDepth:          sourceDepth,
		CheckpointEvery:      time.Minute,
		StopRules: runruntime.ReasoningStopRules{
			RequireDefinitionOfDone: true,
			RequireEvidence:         true,
			RequireVerifier:         true,
			StopOnBudgetExhaustion:  true,
		},
	}
	ctx, err := orchestration.WithAgentExecutionPolicy(
		t.Context(),
		profile,
		model,
		orchestration.RuntimeExecutionCapabilities{},
	)
	if err != nil {
		t.Fatalf("execution policy: %v", err)
	}
	return ctx
}

func metadataResearchTurn() assistant.AssistantTurn {
	return assistant.AssistantTurn{
		TurnID:  "turn-metadata-research",
		TraceID: "trace-metadata-research",
		Input: assistant.AssistantTurnInput{
			Text: "核验杭州出行证据",
		},
	}
}
