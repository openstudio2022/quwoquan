// Package modeldouble 提供测试树内的对象级 typed model provider double。
// 它只服务 local_contract / api_integration，禁止被 internal/** 与 cmd/** 引用。
package modeldouble

import (
	"context"
	"encoding/json"
	"fmt"
	prompting "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/prompting"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

// DeterministicModelProvider 以固定文本回应每个 ReAct stage，使测试无需真实模型即可
// 断言状态机、事件序列与持久化事实。
type DeterministicModelProvider struct{}

var _ orchestration.ModelProvider = DeterministicModelProvider{}
var _ orchestration.ModelExecutionCapabilityProvider = DeterministicModelProvider{}

func (DeterministicModelProvider) ModelExecutionCapabilities() orchestration.ModelExecutionCapabilities {
	return orchestration.ModelExecutionCapabilities{
		ToolCalling:     true,
		ParallelTools:   true,
		ReasoningEffort: true,
	}
}

func (DeterministicModelProvider) Complete(
	_ context.Context,
	req orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	question := strings.TrimSpace(req.UserQuestion)
	if question == "" {
		question = "你的问题"
	}
	switch strings.TrimSpace(req.Stage) {
	case "skill_selection":
		manifest := skillpkg.NewRouter(req.SkillCatalog).Route(assistant.AssistantTurn{
			Input: assistant.AssistantTurnInput{Text: question},
		})
		delta := map[string]any{
			"skillId": manifest.SkillID,
			"reason":  "manifest_semantic_fallback",
		}
		text := fmt.Sprintf(`{"skillId":%q,"reason":"manifest_semantic_fallback"}`, manifest.SkillID)
		return orchestration.ModelResponse{
			Text:                   text,
			StructuredDelta:        delta,
			Usage:                  map[string]any{"inputTokens": 40, "outputTokens": 12},
			FinishReason:           "stop",
			ClientModelInteraction: clientTrace(req, text),
		}, nil
	case "reasoning":
		delta := map[string]any{
			"nextAction": "tool_call",
			"toolName":   reasoningToolName(req.ToolCatalog),
			"toolInput": map[string]any{
				"query": question,
			},
			"understandingSnapshot": map[string]any{
				"userFacingSummary":        fmt.Sprintf("我理解你想了解「%s」，会先对齐关键信息再走检索。", question),
				"retrievalDesignNarrative": fmt.Sprintf("检索上将围绕「%s」查找可公开核验的线索。", question),
			},
		}
		raw, _ := json.Marshal(delta)
		text := string(raw)
		return orchestration.ModelResponse{
			Text:                   text,
			StructuredDelta:        delta,
			Usage:                  map[string]any{"inputTokens": 32, "outputTokens": 24},
			FinishReason:           "tool_use",
			ClientModelInteraction: clientTrace(req, text),
		}, nil
	case "evidence_processing":
		summary := observationToolSummary(req.Observation)
		if summary == "" {
			summary = "工具返回了结构化摘要。"
		}
		delta := map[string]any{
			"retrievalProcessing": map[string]any{
				"processingSummary":  fmt.Sprintf("已从工具结果梳理：%s", truncateRunes(summary, 160)),
				"selectedKeyPoints":  []string{"要点已对齐工具摘要"},
				"acceptedReferences": []any{},
			},
			"evidenceSufficient": true,
		}
		raw, _ := json.Marshal(delta)
		text := string(raw)
		return orchestration.ModelResponse{
			Text:                   text,
			StructuredDelta:        delta,
			Usage:                  map[string]any{"inputTokens": 36, "outputTokens": 28},
			FinishReason:           "stop",
			ClientModelInteraction: clientTrace(req, text),
		}, nil
	case "final":
		summary := observationToolSummary(req.Observation)
		if summary == "" {
			summary = strings.TrimSpace(fmt.Sprint(req.Observation["summary"]))
		}
		if summary == "" || summary == "<nil>" {
			summary = "云端工具已返回可用上下文"
		}
		markdown := finalAnswer(req.SkillID, question, summary)
		delta := map[string]any{"userMarkdown": markdown}
		return orchestration.ModelResponse{
			Text:                   markdown,
			StructuredDelta:        delta,
			Usage:                  map[string]any{"inputTokens": 48, "outputTokens": 44},
			FinishReason:           "stop",
			ClientModelInteraction: clientTrace(req, markdown),
		}, nil
	default:
		text := fmt.Sprintf("云端模型已处理：%s", question)
		delta := map[string]any{"note": text}
		return orchestration.ModelResponse{
			Text:                   text,
			StructuredDelta:        delta,
			FinishReason:           "stop",
			ClientModelInteraction: clientTrace(req, text),
		}, nil
	}
}

func reasoningToolName(catalog []ports.ModelToolDefinition) string {
	if len(catalog) == 0 {
		return ""
	}
	return catalog[0].Name
}

func finalAnswer(skillID, question, summary string) string {
	if text := proactiveFinalAnswer(skillID, question, summary); text != "" {
		return text
	}
	if text := domainSkillFinalAnswer(skillID, question, summary); text != "" {
		return text
	}
	return fmt.Sprintf(
		"已基于云端 ReAct 流程完成回答：%s。针对“%s”，建议先按优先级整理事项，再继续补充细节。",
		summary,
		question,
	)
}

func clientTrace(req orchestration.ModelRequest, responseText string) map[string]any {
	prompt := fmt.Sprintf(
		"%s%s%s%s%s%s%s\n用户问题：%s",
		req.Prompt,
		prompting.FormatModelContextForPrompt(req.ContextTurns),
		prompting.FormatModelContextSummaryForPrompt(req.ContextSummary),
		orchestration.FormatPageContextForPrompt(req.PageContext),
		prompting.FormatAuthorizedIntersectionEvidenceForPrompt(req.IntersectionEvidence),
		prompting.FormatModelPreferencesForPrompt(
			req.SessionPreferences,
			nil,
		),
		prompting.FormatFeedbackContextForPrompt(req.FeedbackContext),
		req.UserQuestion,
	)
	return map[string]any{
		"stage":                   req.Stage,
		"skillId":                 req.SkillID,
		"turnId":                  req.TurnID,
		"traceId":                 req.TraceID,
		"contextTurnCount":        len(req.ContextTurns),
		"requestCharacterCount":   len([]rune(prompt)),
		"responseCharacterCount":  len([]rune(responseText)),
		"finishReason":            "stop",
		"contentRedactionApplied": true,
	}
}

func observationToolSummary(obs map[string]any) string {
	if obs == nil {
		return ""
	}
	if res, ok := obs["result"].(map[string]any); ok {
		s := strings.TrimSpace(fmt.Sprint(res["summary"]))
		if s != "" && s != "<nil>" {
			return s
		}
	}
	s := strings.TrimSpace(fmt.Sprint(obs["summary"]))
	if s == "<nil>" {
		return ""
	}
	return s
}

func truncateRunes(s string, maxRunes int) string {
	r := []rune(s)
	if len(r) <= maxRunes {
		return s
	}
	return string(r[:maxRunes]) + "…"
}
