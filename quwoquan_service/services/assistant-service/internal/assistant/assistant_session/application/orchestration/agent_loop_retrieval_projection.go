package orchestration

import (
	"fmt"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

func buildSearchPlansForStep(turn assistant.AssistantTurn, skill SkillSelection, step ReactStepResult) []map[string]any {
	query := turn.Input.Text
	if step.Tool.Requested.Input != nil {
		if value, ok := step.Tool.Requested.Input["query"].(string); ok && value != "" {
			query = value
		}
		if plans := searchPlansFromToolInput(step.Tool.Requested.Input, step.Tool.Requested.ToolName); len(plans) > 0 {
			return plans
		}
	}
	return []map[string]any{{
		"query":          query,
		"label":          "综合检索",
		"purpose":        "",
		"sourceType":     step.Tool.Requested.ToolName,
		"freshnessHours": 24,
	}}
}

func searchPlansFromToolInput(input map[string]any, toolName string) []map[string]any {
	for _, key := range []string{"searchQueries", "queries"} {
		if plans := searchPlansFromRaw(input[key], toolName); len(plans) > 0 {
			return plans
		}
	}
	return nil
}

func searchPlansFromRaw(raw any, toolName string) []map[string]any {
	switch items := raw.(type) {
	case []any:
		plans := []map[string]any{}
		for _, item := range items {
			if plan := searchPlanFromAny(item, toolName); len(plan) > 0 {
				plans = append(plans, plan)
			}
		}
		return plans
	case []map[string]any:
		plans := []map[string]any{}
		for _, item := range items {
			if plan := searchPlanFromAny(item, toolName); len(plan) > 0 {
				plans = append(plans, plan)
			}
		}
		return plans
	case []string:
		plans := []map[string]any{}
		for _, item := range items {
			if plan := searchPlanFromAny(item, toolName); len(plan) > 0 {
				plans = append(plans, plan)
			}
		}
		return plans
	default:
		return nil
	}
}

func searchPlanFromAny(raw any, toolName string) map[string]any {
	switch item := raw.(type) {
	case string:
		query := strings.TrimSpace(item)
		if query == "" {
			return nil
		}
		return map[string]any{
			"query":          query,
			"label":          "检索",
			"purpose":        "",
			"sourceType":     toolName,
			"freshnessHours": 24,
		}
	case map[string]any:
		query := strings.TrimSpace(stringValue(item["query"]))
		if query == "" {
			return nil
		}
		label := strings.TrimSpace(stringValue(item["dimension"]))
		if label == "" {
			label = strings.TrimSpace(stringValue(item["label"]))
		}
		if label == "" {
			label = "检索"
		}
		return map[string]any{
			"query":          query,
			"label":          label,
			"purpose":        strings.TrimSpace(stringValue(item["purpose"])),
			"sourceType":     toolName,
			"freshnessHours": 24,
		}
	default:
		return nil
	}
}

func buildAcceptedSearchPlansForStep(turn assistant.AssistantTurn, skill SkillSelection, step ReactStepResult) []map[string]any {
	plans := buildSearchPlansForStep(turn, skill, step)
	for i := range plans {
		plans[i]["acceptReason"] = ""
	}
	return plans
}

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

// collectEmergedTags 汇总本轮 ReAct 各步 app_search 命中内容的类目（categoryId / subCategory），
// 去重后归到 Topic 维度生成路径制 tagRef，作为对话浮现的兴趣标签随 turn.completed 下发，
// 供端侧合成 assistant_interest 行为回流推荐特征（rm_recommend_feature）。
func collectEmergedTags(result ReactResult) []string {
	seen := map[string]struct{}{}
	tags := []string{}
	add := func(value string) {
		value = strings.TrimSpace(value)
		if value == "" {
			return
		}
		tagRef := "Topic/" + value
		if _, ok := seen[tagRef]; ok {
			return
		}
		seen[tagRef] = struct{}{}
		tags = append(tags, tagRef)
	}
	consume := func(m map[string]any) {
		add(stringValue(m["categoryId"]))
		add(stringValue(m["subCategory"]))
	}
	for _, step := range result.Steps {
		raw, ok := step.Tool.Completed.Result["results"]
		if !ok {
			continue
		}
		switch items := raw.(type) {
		case []any:
			for _, item := range items {
				if m, ok := item.(map[string]any); ok {
					consume(m)
				}
			}
		case []map[string]any:
			for _, m := range items {
				consume(m)
			}
		}
	}
	return tags
}
