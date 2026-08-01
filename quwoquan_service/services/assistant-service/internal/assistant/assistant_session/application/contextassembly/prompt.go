package contextassembly

import (
	"fmt"
	"sort"
	"strings"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

func FormatForPrompt(result *AssemblyResult) string {
	if result == nil {
		return ""
	}
	lines := []string{
		"\n运行前上下文装配结果（只可使用这里列出的授权事实；推断值不得表述为用户确认）：",
		"- domainId: " + result.DomainID,
		"- channelId: " + result.ChannelID,
		"- memoryScope: " + result.MemoryScope,
		"- answerBoundary: " + result.AnswerBoundaryRule,
		fmt.Sprintf("- realtimeNeed: %t", result.HasRealtimeNeed),
	}
	slotIDs := make([]string, 0, len(result.SlotState.Slots))
	for slotID := range result.SlotState.Slots {
		slotIDs = append(slotIDs, slotID)
	}
	sort.Strings(slotIDs)
	for _, slotID := range slotIDs {
		slot := result.SlotState.Slots[slotID]
		if slot.Status == assistantgenerated.SlotValueStatusMissing {
			lines = append(lines, fmt.Sprintf("- slot[%s]: missing", slotID))
			continue
		}
		if slot.Status == assistantgenerated.SlotValueStatusConflicted {
			lines = append(lines, fmt.Sprintf(
				"- slot[%s]: conflicted (candidates=%s)",
				slotID,
				strings.Join(slot.Candidates, ","),
			))
			continue
		}
		if slot.Status == assistantgenerated.SlotValueStatusStale {
			lines = append(lines, fmt.Sprintf(
				"- slot[%s]: stale (source=%s; do not use before confirmation)",
				slotID,
				slot.Source,
			))
			continue
		}
		lines = append(lines, fmt.Sprintf(
			"- slot[%s]: %v (status=%s, source=%s)",
			slotID,
			slot.Value,
			slot.Status.WireName(),
			slot.Source,
		))
	}
	if city := strings.TrimSpace(result.AvailableGeoContext.CityLabel); city != "" {
		lines = append(lines, fmt.Sprintf(
			"- availableGeo: %s (source=%s, confidence=%.2f)",
			city,
			result.AvailableGeoContext.Source,
			result.AvailableGeoContext.Confidence,
		))
	}
	for _, hint := range result.RecallHints {
		if strings.TrimSpace(hint.Text) == "" {
			continue
		}
		lines = append(lines, fmt.Sprintf(
			"- recalled[%s, score=%.2f]: %s",
			hint.Source,
			hint.Score,
			hint.Text,
		))
	}
	return strings.Join(lines, "\n")
}
