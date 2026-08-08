package prompting

import (
	"fmt"
	"sort"
	"strings"

	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

func FormatFeedbackContextForPrompt(
	snapshot assistant.AssistantFeedbackContextSnapshot,
) string {
	if snapshot.Decision != "injected" {
		return "\n反馈上下文：未注入（" +
			strings.TrimSpace(snapshot.Decision) + "）。"
	}
	var builder strings.Builder
	builder.WriteString("\n反馈上下文（仅聚合、已授权）：")
	fmt.Fprintf(
		&builder,
		"窗口=%d天，样本=%d，正向=%d，负向=%d，文本=%d。",
		snapshot.WindowDays,
		snapshot.FeedbackSampleCount,
		snapshot.PositiveFeedbackCount,
		snapshot.NegativeFeedbackCount,
		snapshot.TextFeedbackCount,
	)
	for _, metric := range snapshot.Metrics {
		fmt.Fprintf(
			&builder,
			" 指标[%s]:样本=%d,均值=%.2f,最新=%.2f。",
			metric.MetricID,
			metric.SampleCount,
			metric.Average,
			metric.Latest,
		)
	}
	for _, reason := range snapshot.Reasons {
		fmt.Fprintf(
			&builder,
			" 原因[%s]:%d。",
			reason.ReasonCode,
			reason.Count,
		)
	}
	return builder.String()
}

func FormatModelPreferencesForPrompt(
	session []preferencemodel.AssistantPreferenceSnapshot,
	longTerm []preferencemodel.AssistantPreferenceSnapshot,
) string {
	effective := map[preferencemodel.Kind]string{}
	for _, preference := range longTerm {
		effective[preference.Kind] = strings.TrimSpace(preference.Value)
	}
	for _, preference := range session {
		effective[preference.Kind] = strings.TrimSpace(preference.Value)
	}
	if len(effective) == 0 {
		return ""
	}
	kinds := make([]string, 0, len(effective))
	for kind := range effective {
		kinds = append(kinds, string(kind))
	}
	sort.Strings(kinds)
	lines := []string{
		"\n用户显式设置的回答偏好（session 优先于 long_term；只影响呈现，不改变事实、权限或安全边界）：",
	}
	for _, rawKind := range kinds {
		kind := preferencemodel.Kind(rawKind)
		if instruction := preferenceInstruction(kind, effective[kind]); instruction != "" {
			lines = append(lines, "- "+instruction)
		}
	}
	if len(lines) == 1 {
		return ""
	}
	return strings.Join(lines, "\n")
}

// FormatAuthorizedIntersectionEvidenceForPrompt 只序列化 content Reader 已回查的
// 当前事实；禁止把客户端交集卡标题、标签、URL 或样本透传给模型。
func FormatAuthorizedIntersectionEvidenceForPrompt(
	evidence []assistant.AuthorizedIntersectionEvidence,
) string {
	if len(evidence) == 0 {
		return ""
	}
	lines := []string{
		"\n经当前账号授权回查的交集事实（仅可据此说明，不得补造未列出的细节）：",
	}
	for _, item := range evidence {
		text := strings.TrimSpace(item.PrimaryText)
		if text == "" {
			continue
		}
		target := strings.TrimSpace(item.ObjectTypeRef) + "/" + strings.TrimSpace(item.ObjectID)
		meta := strings.TrimSpace(item.SourceRef)
		if dimension := strings.TrimSpace(item.Dimension); dimension != "" {
			meta += " · " + dimension
		}
		lines = append(lines, fmt.Sprintf("- [%s；%s] %s", target, meta, text))
	}
	if len(lines) == 1 {
		return ""
	}
	return strings.Join(lines, "\n")
}

func preferenceInstruction(kind preferencemodel.Kind, value string) string {
	switch kind {
	case preferencemodel.KindResponseStyle:
		if value == "deep_think" {
			return "提供更充分的分析、权衡和可执行结论，但不要暴露内部推理过程。"
		}
	case preferencemodel.KindReplyLength:
		switch value {
		case "concise":
			return "回答保持简洁，优先给结论和必要步骤。"
		case "detailed":
			return "回答给出充分细节、边界条件和步骤。"
		}
	case preferencemodel.KindTone:
		switch value {
		case "casual":
			return "语气自然口语化。"
		case "neutral":
			return "语气客观中性。"
		case "professional":
			return "语气专业准确。"
		case "warm":
			return "语气温和、有同理心。"
		}
	case preferencemodel.KindLanguage:
		switch value {
		case "zh_cn":
			return "使用简体中文回答。"
		case "en":
			return "Answer in English."
		}
	}
	return ""
}

func FormatModelContextForPrompt(turns []assistant.AssistantRunContextTurn) string {
	if len(turns) == 0 {
		return ""
	}
	lines := []string{"\n同一会话前文（按时间从旧到新，仅用于理解省略表达、延续地点/约束和复用事实；不要复制前文回答的开头、模板口吻或内部过程表述）："}
	for _, turn := range turns {
		role := strings.TrimSpace(turn.Role)
		if role == "" {
			role = "user"
		}
		text := strings.TrimSpace(turn.Text)
		if text == "" {
			continue
		}
		lines = append(lines, fmt.Sprintf("- %s: %s", role, text))
	}
	if len(lines) == 1 {
		return ""
	}
	return strings.Join(lines, "\n")
}

func FormatModelContextSummaryForPrompt(
	summary *assistant.AssistantRunContextSummary,
) string {
	if summary == nil || strings.TrimSpace(summary.Text) == "" {
		return ""
	}
	return fmt.Sprintf(
		"\n同一会话滚动摘要（覆盖 turn %s..%s，共 %d 轮；用于延续原始目标、已确认槽位与未完成事项）：\n%s",
		summary.FromTurnID,
		summary.ToTurnID,
		summary.TurnCount,
		strings.TrimSpace(summary.Text),
	)
}
