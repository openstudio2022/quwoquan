package orchestration

import (
	"fmt"
	"strings"
	"unicode/utf8"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

const (
	assistantUserProcessScopeRoot        = "root"
	assistantUserProcessScopeSkill       = "skill"
	assistantUserProcessScopeAggregation = "aggregation"

	assistantUserProcessStatusActive    = "active"
	assistantUserProcessStatusCompleted = "completed"
	assistantUserProcessStatusFailed    = "failed"
)

// 过程阶段只用 PlannerPhaseId 契约枚举表达，服务与端侧共享同一批取值。
const (
	assistantUserProcessPhaseSkillSelection   = assistantgenerated.PlannerPhaseIdClassifying
	assistantUserProcessPhasePlanning         = assistantgenerated.PlannerPhaseIdPlanning
	assistantUserProcessPhaseToolExecution    = assistantgenerated.PlannerPhaseIdSearching
	assistantUserProcessPhaseEvidenceReview   = assistantgenerated.PlannerPhaseIdAssessing
	assistantUserProcessPhaseAnswerGeneration = assistantgenerated.PlannerPhaseIdAnswering
	assistantUserProcessPhaseClarifying       = assistantgenerated.PlannerPhaseIdClarifying
	assistantUserProcessPhaseAggregating      = assistantgenerated.PlannerPhaseIdAggregating
)

func userProcessReplacePayload() map[string]any {
	return map[string]any{
		"processes": []assistant.AssistantRunVisibleProcess{},
	}
}

func userProcessPayload(process assistant.AssistantRunVisibleProcess) map[string]any {
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

func UserProcessReferences(raw any) []assistant.AssistantRunVisibleReference {
	references := []assistant.AssistantRunVisibleReference{}
	appendReference := func(reference map[string]any) {
		if len(references) >= 5 {
			return
		}
		rawDestination, ok := reference["destination"].(map[string]any)
		if !ok {
			return
		}
		destination, ok := citationDestinationFromMap(rawDestination)
		if !ok {
			return
		}
		item := assistant.AssistantRunVisibleReference{
			Title:       strings.TrimSpace(stringValue(reference["title"])),
			Destination: destination,
			Source:      strings.TrimSpace(stringValue(reference["source"])),
			Snippet:     strings.TrimSpace(stringValue(reference["snippet"])),
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

func userProcessID(phase assistantgenerated.PlannerPhaseId, iteration int) string {
	if iteration <= 0 {
		return phase.WireName()
	}
	return fmt.Sprintf("%s:%d", phase.WireName(), iteration)
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
