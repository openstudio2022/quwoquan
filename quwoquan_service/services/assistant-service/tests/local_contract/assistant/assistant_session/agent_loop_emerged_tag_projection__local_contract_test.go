// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-003
package local_contract

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/streaming"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

type emergedTagProjectionModel struct{}

func (emergedTagProjectionModel) Complete(
	_ context.Context,
	request orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	switch request.Stage {
	case "reasoning":
		return orchestration.ModelResponse{StructuredDelta: map[string]any{
			"nextAction": "tool_call",
			"toolName":   "app_search",
			"toolInput":  map[string]any{"query": "西湖周末游"},
		}}, nil
	case "evidence_processing":
		return orchestration.ModelResponse{StructuredDelta: map[string]any{
			"evidenceSufficient": true,
			"retrievalProcessing": map[string]any{
				"processingSummary": "已核验站内结果",
			},
		}}, nil
	case "final":
		return orchestration.ModelResponse{
			Text: "已找到西湖周末游内容。",
			StructuredDelta: map[string]any{
				"userMarkdown": "已找到西湖周末游内容。",
			},
		}, nil
	default:
		return orchestration.ModelResponse{}, nil
	}
}

type emergedTagProjectionTool struct{}

func (emergedTagProjectionTool) ModelToolDeclarations(
	allowedToolNames []string,
) []ports.ModelToolDefinition {
	for _, name := range allowedToolNames {
		if name == "app_search" {
			return []ports.ModelToolDefinition{{
				Name:       name,
				Parameters: toolpkg.AppSearchMetadata().InputSchema,
			}}
		}
	}
	return nil
}

func (emergedTagProjectionTool) ToolMetadata(
	toolName string,
) (toolpkg.Metadata, bool) {
	if toolName != "app_search" {
		return toolpkg.Metadata{}, false
	}
	return toolpkg.AppSearchMetadata(), true
}

func (emergedTagProjectionTool) Execute(
	_ context.Context,
	request orchestration.ToolRequest,
) (orchestration.ToolExecution, error) {
	result := map[string]any{
		"summary":        "找到西湖周末游内容",
		"emergedTagRefs": []string{"Topic/旅行", "Topic/周末游", "Topic/旅行"},
		"evidenceAssessment": map[string]any{
			"status":             "accepted",
			"evidenceSufficient": true,
			"replanRequired":     false,
			"reason":             "canonical_search_hits",
			"targetIds":          []string{"post-1"},
			"documentIds":        []string{},
			"artifactRefs":       []string{},
			"sourceIds":          []string{"citation-1"},
		},
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

func TestAgentLoopConsumesStandardEmergedTagRefsWithoutToolResultBranch(
	t *testing.T,
) {
	loop := orchestration.NewAgentLoop(
		assistantSessionAgentLoopSkillRuntime{},
		orchestration.ReactRuntime{
			Model: emergedTagProjectionModel{},
			Tools: emergedTagProjectionTool{},
		},
		func() time.Time { return time.Date(2026, 8, 4, 0, 0, 0, 0, time.UTC) },
	)
	loop.Catalog = skillfixture.StaticLoader{Manifests: []skillpkg.Manifest{{
		SkillID:      "general_qa",
		DisplayName:  "通用问答",
		DomainID:     "assistant",
		ProblemClass: "general",
		ToolPolicy: skillpkg.ToolPolicy{
			AllowedTools: []string{"app_search"},
			MaxToolCalls: 1,
		},
	}}}
	policy := testFrozenPolicySelection(
		"assistant-default",
		"general_qa",
		"assistant",
	)
	policy.Template.AllowedTools = []string{"app_search"}

	events, failure, err := loop.RunTurn(t.Context(), assistant.AssistantTurn{
		TurnID:                "turn-emerged-tag-projection",
		SessionID:             "session-emerged-tag-projection",
		UserID:                "user-emerged-tag-projection",
		Input:                 assistant.AssistantTurnInput{Text: "找西湖周末游内容"},
		TraceID:               "trace-emerged-tag-projection",
		FrozenPolicySelection: policy,
	})
	if err != nil || failure != nil {
		t.Fatalf("RunTurn() err=%v failure=%+v", err, failure)
	}
	for _, event := range events {
		if event.EventType != string(assistantstreaming.AssistantStreamEventCompleted) {
			continue
		}
		tagRefs, ok := event.Payload["emergedTags"].([]string)
		if !ok || len(tagRefs) != 2 || tagRefs[0] != "Topic/旅行" ||
			tagRefs[1] != "Topic/周末游" {
			t.Fatalf("completed emergedTags=%#v", event.Payload["emergedTags"])
		}
		return
	}
	t.Fatal("completed event was not emitted")
}
