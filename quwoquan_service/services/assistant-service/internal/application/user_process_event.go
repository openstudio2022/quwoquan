package application

import (
	"fmt"
	"strings"
	"unicode/utf8"
)

// AssistantUserProcess 是 AssistantRun 唯一可公开的过程条目。它有意不包含
// 模型原始推理、检索 query、tool input 或 provider 诊断信息。
type AssistantUserProcess struct {
	ProcessID              string                          `json:"processId"`
	Scope                  string                          `json:"scope"`
	Stage                  string                          `json:"stage"`
	Status                 string                          `json:"status"`
	Order                  int                             `json:"order"`
	Summary                string                          `json:"summary,omitempty"`
	SkillID                string                          `json:"skillId,omitempty"`
	DomainID               string                          `json:"domainId,omitempty"`
	ToolName               string                          `json:"toolName,omitempty"`
	SearchedDocumentCount  int                             `json:"searchedDocumentCount,omitempty"`
	ProcessedDocumentCount int                             `json:"processedDocumentCount,omitempty"`
	AcceptedDocumentCount  int                             `json:"acceptedDocumentCount,omitempty"`
	AcceptedReferences     []AssistantUserProcessReference `json:"acceptedReferences,omitempty"`
}

type AssistantUserProcessReference struct {
	Title   string `json:"title"`
	URL     string `json:"url"`
	Source  string `json:"source"`
	Snippet string `json:"snippet,omitempty"`
}

const (
	assistantUserProcessScopeRoot        = "root"
	assistantUserProcessScopeSkill       = "skill"
	assistantUserProcessScopeAggregation = "aggregation"

	assistantUserProcessStageSkillSelection   = "skill_selection"
	assistantUserProcessStagePlanning         = "planning"
	assistantUserProcessStageToolExecution    = "tool_execution"
	assistantUserProcessStageEvidenceReview   = "evidence_review"
	assistantUserProcessStageAnswerGeneration = "answer_generation"

	assistantUserProcessStatusActive    = "active"
	assistantUserProcessStatusCompleted = "completed"
	assistantUserProcessStatusFailed    = "failed"
)

func userProcessReplacePayload() map[string]any {
	return map[string]any{
		"processes": []AssistantUserProcess{},
	}
}

func userProcessPayload(process AssistantUserProcess) map[string]any {
	return map[string]any{
		"process": process,
	}
}

func userProcessSummary(raw string) string {
	summary := strings.TrimSpace(raw)
	if summary == "" {
		return ""
	}
	lower := strings.ToLower(summary)
	for _, forbidden := range []string{
		"<think",
		"</think",
		"queryvariants",
		"tool_call",
		"assistant_turn",
		"provider=",
		"freshnesshours",
		"schema",
	} {
		if strings.Contains(lower, forbidden) {
			return ""
		}
	}
	if utf8.RuneCountInString(summary) > 280 {
		return string([]rune(summary)[:280]) + "…"
	}
	return summary
}

func userProcessReferences(raw any) []AssistantUserProcessReference {
	references := []AssistantUserProcessReference{}
	appendReference := func(reference map[string]any) {
		if len(references) >= 5 {
			return
		}
		item := AssistantUserProcessReference{
			Title:   strings.TrimSpace(stringValue(reference["title"])),
			URL:     strings.TrimSpace(stringValue(reference["url"])),
			Source:  strings.TrimSpace(stringValue(reference["source"])),
			Snippet: strings.TrimSpace(stringValue(reference["snippet"])),
		}
		if item.Title == "" && item.URL == "" && item.Source == "" {
			return
		}
		references = append(references, item)
	}
	switch entries := raw.(type) {
	case []map[string]any:
		for _, entry := range entries {
			appendReference(entry)
		}
	case []any:
		for _, rawEntry := range entries {
			entry, ok := rawEntry.(map[string]any)
			if !ok {
				continue
			}
			appendReference(entry)
		}
	}
	return references
}

func userProcessID(stage string, iteration int) string {
	if iteration <= 0 {
		return stage
	}
	return fmt.Sprintf("%s:%d", stage, iteration)
}

func intValue(raw any) int {
	switch value := raw.(type) {
	case int:
		return value
	case int32:
		return int(value)
	case int64:
		return int(value)
	case uint:
		return int(value)
	case uint32:
		return int(value)
	case uint64:
		return int(value)
	case float64:
		return int(value)
	case float32:
		return int(value)
	default:
		return 0
	}
}
