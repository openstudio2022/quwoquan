package orchestration

import (
	"fmt"
	"sort"
	"strings"

	contextassembly "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/contextassembly"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

var compactedSlotIDs = []string{
	"origin",
	"destination",
	"travel_date",
	"party_size",
	"budget",
	"location",
}

func compactSessionContext(
	candidates []assistant.AssistantTurn,
	recentTurnLimit int,
) ([]assistant.AssistantSessionContextTurn, *assistant.AssistantSessionContextSummary) {
	if recentTurnLimit <= 0 {
		recentTurnLimit = 1
	}
	if len(candidates) <= recentTurnLimit {
		return sessionContextFromTurns(candidates), nil
	}
	split := len(candidates) - recentTurnLimit
	compacted := candidates[:split]
	recent := candidates[split:]
	summary := summarizeSessionTurns(compacted)
	return sessionContextFromTurns(recent), &summary
}

func sessionContextFromTurns(
	candidates []assistant.AssistantTurn,
) []assistant.AssistantSessionContextTurn {
	out := make([]assistant.AssistantSessionContextTurn, 0, len(candidates)*2)
	for _, item := range candidates {
		if strings.TrimSpace(item.Input.Text) == "" {
			continue
		}
		out = append(out, assistant.AssistantSessionContextTurn{
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
		out = append(out, assistant.AssistantSessionContextTurn{
			Role:     "assistant",
			Text:     answer,
			SkillID:  item.SkillID,
			DomainID: item.DomainID,
		})
	}
	return out
}

func summarizeSessionTurns(
	turns []assistant.AssistantTurn,
) assistant.AssistantSessionContextSummary {
	return advanceSessionContextSummary(nil, turns)
}

func advanceSessionContextSummary(
	previous *assistant.AssistantSessionContextSummary,
	turns []assistant.AssistantTurn,
) assistant.AssistantSessionContextSummary {
	summary := assistant.AssistantSessionContextSummary{
		SummaryID:      "session-summary",
		ConfirmedSlots: map[string]string{},
	}
	if previous != nil {
		summary = *previous
		summary.ConfirmedFacts = append(
			[]string(nil),
			previous.ConfirmedFacts...,
		)
		summary.PendingItems = append(
			[]string(nil),
			previous.PendingItems...,
		)
		summary.ConfirmedSlots = make(
			map[string]string,
			len(previous.ConfirmedSlots),
		)
		for slotID, value := range previous.ConfirmedSlots {
			summary.ConfirmedSlots[slotID] = value
		}
	}
	seenFacts := make(map[string]bool, len(summary.ConfirmedFacts))
	for _, fact := range summary.ConfirmedFacts {
		seenFacts[fact] = true
	}
	seenPending := make(map[string]bool, len(summary.PendingItems))
	for _, item := range summary.PendingItems {
		seenPending[item] = true
	}
	for _, turn := range turns {
		if summary.FromTurnID == "" {
			summary.FromTurnID = turn.TurnID
		}
		summary.ToTurnID = turn.TurnID
		summary.TurnCount++
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
			if sessionKeyFact(userText) && !seenFacts[userText] {
				seenFacts[userText] = true
				summary.ConfirmedFacts = append(summary.ConfirmedFacts, userText)
			}
		}
		if turn.TerminalSnapshot == nil {
			continue
		}
		answer := strings.TrimSpace(turn.TerminalSnapshot.AnswerText)
		if pendingSessionItem(answer) && !seenPending[answer] {
			seenPending[answer] = true
			summary.PendingItems = append(summary.PendingItems, answer)
		}
	}
	summary.ConfirmedFacts = keepLatestStrings(summary.ConfirmedFacts, 8)
	summary.PendingItems = keepLatestStrings(summary.PendingItems, 4)
	if summary.FromTurnID != "" && summary.ToTurnID != "" {
		summary.SummaryID = strings.Join(
			[]string{"session-summary", summary.FromTurnID, summary.ToTurnID},
			":",
		)
	}
	summary.Text = formatSessionSummary(summary)
	return summary
}

func formatSessionSummary(
	summary assistant.AssistantSessionContextSummary,
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

func sessionKeyFact(text string) bool {
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

func pendingSessionItem(text string) bool {
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
