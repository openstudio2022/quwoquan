package orchestration

import (
	"fmt"
	"strings"

	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

func deltaNestedString(delta map[string]any, parentKey, childKey string) string {
	if delta == nil {
		return ""
	}
	raw, ok := delta[parentKey]
	if !ok {
		return ""
	}
	nested, ok := raw.(map[string]any)
	if !ok {
		return ""
	}
	return strings.TrimSpace(fmt.Sprint(nested[childKey]))
}

func stringSliceFromAny(raw any) []string {
	switch items := raw.(type) {
	case []any:
		out := []string{}
		for _, item := range items {
			text := strings.TrimSpace(fmt.Sprint(item))
			if text != "" {
				out = append(out, text)
			}
		}
		return out
	case []string:
		out := []string{}
		for _, item := range items {
			text := strings.TrimSpace(item)
			if text != "" {
				out = append(out, text)
			}
		}
		return out
	default:
		return []string{}
	}
}

func referencesFromEvidence(raw any) []map[string]any {
	switch items := raw.(type) {
	case []any:
		out := []map[string]any{}
		for _, item := range items {
			entry, ok := item.(map[string]any)
			if !ok {
				continue
			}
			out = append(out, entry)
		}
		return out
	case []map[string]any:
		return items
	default:
		return nil
	}
}

func buildUnderstandingSnapshotForStep(turn assistant.AssistantTurn, step ReactStepResult) map[string]any {
	delta := step.StructuredDelta
	stageNarrative := strings.TrimSpace(fmt.Sprint(delta["stageNarrative"]))
	if stageNarrative == "<nil>" {
		stageNarrative = ""
	}
	summary := stageNarrative
	if summary == "" {
		summary = deltaNestedString(delta, "understandingSnapshot", "userFacingSummary")
	}
	retrieval := ""
	if stageNarrative == "" {
		retrieval = deltaNestedString(delta, "understandingSnapshot", "retrievalDesignNarrative")
	}
	return map[string]any{
		"intentSummary":            turn.Input.Text,
		"userFacingSummary":        summary,
		"retrievalDesignNarrative": retrieval,
		"concernPoints":            []string{},
		"emotionSignal":            "",
		"resolutionItems":          []map[string]any{},
		"assumptions":              []string{},
		"mismatchSignal":           "",
		"carryForwardFacts":        []string{},
		"discardedAssumptions":     []string{},
	}
}

func buildRetrievalProcessingForStep(step ReactStepResult) map[string]any {
	delta := step.EvidenceStructuredDelta
	summary := ""
	keyPoints := []string{}
	modelRefs := []map[string]any(nil)
	if delta != nil {
		if rp, ok := delta["retrievalProcessing"].(map[string]any); ok {
			summary = strings.TrimSpace(fmt.Sprint(rp["processingSummary"]))
			keyPoints = stringSliceFromAny(rp["selectedKeyPoints"])
			modelRefs = referencesFromEvidence(rp["acceptedReferences"])
		}
	}
	reliable := toolResultReliable(step)
	toolRefs := []map[string]any{}
	if reliable {
		toolRefs = acceptedReferencesForStep(step)
	}
	searchedCount := len(toolRefs)
	if reliable {
		referencesCountFallback := searchedCount == 0 && !step.Observation.Empty
		if referencesCountFallback {
			searchedCount = 1
		}
	}
	acceptedRefs := []map[string]any{}
	if reliable {
		acceptedRefs = MergeReferences(modelRefs, toolRefs)
	}
	return map[string]any{
		"searchedDocumentCount":  searchedCount,
		"processedDocumentCount": searchedCount,
		"acceptedDocumentCount":  len(acceptedRefs),
		"processingSummary":      summary,
		"selectedKeyPoints":      keyPoints,
		"expansionReason":        "",
		"acceptedReferences":     acceptedRefs,
	}
}

func MergeReferences(primary []map[string]any, fallback []map[string]any) []map[string]any {
	merged := []map[string]any{}
	seen := map[string]bool{}
	authoritative := map[string]map[string]any{}
	for _, reference := range fallback {
		key, ok := referenceDestinationKey(reference)
		if !ok {
			continue
		}
		authoritative[key] = reference
	}
	appendOne := func(reference map[string]any) {
		if len(merged) >= 5 {
			return
		}
		key, ok := referenceDestinationKey(reference)
		if !ok || seen[key] {
			return
		}
		authoritativeReference, exists := authoritative[key]
		if !exists {
			return
		}
		seen[key] = true
		merged = append(merged, authoritativeReference)
	}
	for _, reference := range primary {
		canonical, ok := canonicalModelReference(reference)
		if ok {
			appendOne(canonical)
		}
	}
	for _, reference := range fallback {
		appendOne(reference)
	}
	return merged
}

// collectEmergedTags 只消费 Tool Fabric 的标准 emergedTagRefs 输出，不猜测
// 某个工具的 results/payload 结构。任何站内或垂类工具只要在 canonical output
// schema 声明并返回该字段，就能参与兴趣回流而无需修改 AgentLoop。
func collectEmergedTags(result ReactResult) []string {
	seen := map[string]struct{}{}
	tags := []string{}
	add := func(value string) {
		value = strings.TrimSpace(value)
		if value == "" {
			return
		}
		if _, ok := seen[value]; ok {
			return
		}
		seen[value] = struct{}{}
		tags = append(tags, value)
	}
	for _, step := range result.Steps {
		for _, tagRef := range stringSliceFromAny(
			step.Tool.Completed.Result["emergedTagRefs"],
		) {
			add(tagRef)
		}
	}
	return tags
}
