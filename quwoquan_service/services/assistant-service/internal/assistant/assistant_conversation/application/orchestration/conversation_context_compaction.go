package orchestration

import (
	"fmt"
	"sort"
	"strings"

	contextassembly "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/contextassembly"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

var compactedSlotIDs = []string{
	"origin",
	"destination",
	"travel_date",
	"party_size",
	"budget",
	"location",
}

func compactConversationContext(
	candidates []assistant.AssistantTurn,
	recentTurnLimit int,
) ([]assistant.AssistantConversationContextTurn, *assistant.AssistantConversationContextSummary) {
	if recentTurnLimit <= 0 {
		recentTurnLimit = 1
	}
	if len(candidates) <= recentTurnLimit {
		return conversationContextFromTurns(candidates), nil
	}
	split := len(candidates) - recentTurnLimit
	compacted := candidates[:split]
	recent := candidates[split:]
	summary := summarizeConversationTurns(compacted)
	return conversationContextFromTurns(recent), &summary
}

func conversationContextFromTurns(
	candidates []assistant.AssistantTurn,
) []assistant.AssistantConversationContextTurn {
	out := make([]assistant.AssistantConversationContextTurn, 0, len(candidates)*2)
	for _, item := range candidates {
		if strings.TrimSpace(item.Input.Text) == "" {
			continue
		}
		out = append(out, assistant.AssistantConversationContextTurn{
			Role:     "user",
			Text:     item.Input.Text,
			SkillID:  item.SkillID,
			DomainID: item.DomainID,
		})
		if item.TerminalSnapshot == nil {
			continue
		}
		answer := strings.TrimSpace(item.TerminalSnapshot.AnswerText)
		if answer == "" {
			continue
		}
		out = append(out, assistant.AssistantConversationContextTurn{
			Role:     "assistant",
			Text:     answer,
			SkillID:  item.SkillID,
			DomainID: item.DomainID,
		})
	}
	return out
}

func summarizeConversationTurns(
	turns []assistant.AssistantTurn,
) assistant.AssistantConversationContextSummary {
	summary := assistant.AssistantConversationContextSummary{
		SummaryID:      "conversation-summary",
		TurnCount:      len(turns),
		ConfirmedSlots: map[string]string{},
	}
	if len(turns) == 0 {
		return summary
	}
	summary.FromTurnID = turns[0].TurnID
	summary.ToTurnID = turns[len(turns)-1].TurnID
	summary.SummaryID = strings.Join(
		[]string{"conversation-summary", summary.FromTurnID, summary.ToTurnID},
		":",
	)
	seenFacts := map[string]bool{}
	seenPending := map[string]bool{}
	for _, turn := range turns {
		userText := strings.TrimSpace(turn.Input.Text)
		if userText != "" {
			if summary.CurrentGoal == "" {
				summary.CurrentGoal = userText
			}
			for _, slotID := range compactedSlotIDs {
				if value, ok := contextassembly.ExtractSlotValue(slotID, userText); ok {
					summary.ConfirmedSlots[slotID] = value
				}
			}
			if conversationKeyFact(userText) && !seenFacts[userText] {
				seenFacts[userText] = true
				summary.ConfirmedFacts = append(summary.ConfirmedFacts, userText)
			}
		}
		if turn.TerminalSnapshot == nil {
			continue
		}
		answer := strings.TrimSpace(turn.TerminalSnapshot.AnswerText)
		if pendingConversationItem(answer) && !seenPending[answer] {
			seenPending[answer] = true
			summary.PendingItems = append(summary.PendingItems, answer)
		}
	}
	summary.ConfirmedFacts = keepLatestStrings(summary.ConfirmedFacts, 8)
	summary.PendingItems = keepLatestStrings(summary.PendingItems, 4)
	summary.Text = formatConversationSummary(summary)
	return summary
}

func formatConversationSummary(
	summary assistant.AssistantConversationContextSummary,
) string {
	lines := []string{
		fmt.Sprintf(
			"压缩轮次：%s 至 %s（%d 轮）",
			summary.FromTurnID,
			summary.ToTurnID,
			summary.TurnCount,
		),
	}
	if summary.CurrentGoal != "" {
		lines = append(lines, "原始目标："+summary.CurrentGoal)
	}
	slotIDs := make([]string, 0, len(summary.ConfirmedSlots))
	for slotID := range summary.ConfirmedSlots {
		slotIDs = append(slotIDs, slotID)
	}
	sort.Strings(slotIDs)
	for _, slotID := range slotIDs {
		lines = append(lines, fmt.Sprintf(
			"已确认槽位[%s]=%s",
			slotID,
			summary.ConfirmedSlots[slotID],
		))
	}
	for _, fact := range summary.ConfirmedFacts {
		lines = append(lines, "已确认事实："+fact)
	}
	for _, item := range summary.PendingItems {
		lines = append(lines, "未完成事项："+item)
	}
	return strings.Join(lines, "\n")
}

func conversationKeyFact(text string) bool {
	for _, marker := range []string{
		"目的地", "出发", "预算", "人", "不吃", "过敏", "称呼",
		"偏好", "需要", "计划", "目标", "必须", "不要",
	} {
		if strings.Contains(text, marker) {
			return true
		}
	}
	return false
}

func pendingConversationItem(text string) bool {
	for _, marker := range []string{"请补充", "待确认", "还需要", "尚未", "下一步"} {
		if strings.Contains(text, marker) {
			return true
		}
	}
	return false
}

func keepLatestStrings(values []string, limit int) []string {
	if limit <= 0 || len(values) <= limit {
		return values
	}
	return append([]string(nil), values[len(values)-limit:]...)
}
