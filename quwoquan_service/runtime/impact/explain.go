package impact

import (
	"strconv"
	"strings"
)

// helpType 标准名常量（HelpRelationship..HelpAudience）由 tools/codegen_impact
// 从 impact_help_type_registry.yaml 生成于 help_type_table.go（同 package impact，单一真相源）。

// ActorPerspective controls pronouns for author-facing impact statements.
type ActorPerspective string

const (
	ActorTA   ActorPerspective = "ta"
	ActorSelf ActorPerspective = "self"
)

// PrimaryText instantiates the shared cloud-side impact conclusion sentence.
// App surfaces must render this value directly instead of rebuilding text.
func PrimaryText(helpType string, action string, count int64, perspective ActorPerspective) string {
	if count <= 0 {
		return ""
	}
	subject := representativeSubject(count)
	switch strings.TrimSpace(helpType) {
	case HelpRelationship:
		switch strings.TrimSpace(action) {
		case "establish_connection":
			return subject + "在这里建立了新连接"
		default:
			return subject + "通过" + actorPronoun(perspective) + "建立了新连接"
		}
	case HelpCommunity:
		switch strings.TrimSpace(action) {
		case "start_discussion":
			return subject + "带起了新的讨论"
		default:
			return subject + "加入了相关圈子"
		}
	case HelpDecision:
		switch strings.TrimSpace(action) {
		case "visit_place":
			return subject + "通过" + actorPronoun(perspective) + "的内容去了相关地点"
		default:
			return subject + "通过" + actorPronoun(perspective) + "的内容关注了相关对象"
		}
	case HelpKnowledge:
		switch strings.TrimSpace(action) {
		case "quote_answer":
			return subject + "引用了" + actorPronoun(perspective) + "的回答"
		default:
			return subject + "读完了" + actorPronoun(perspective) + "的内容"
		}
	case HelpSpread:
		switch strings.TrimSpace(action) {
		case "active_participation":
			return subject + "最近参与了这里"
		default:
			return subject + "转发了" + actorPronoun(perspective) + "的内容"
		}
	case HelpAudience:
		return subject + "看过" + actorPronoun(perspective) + "的内容"
	default:
		return ""
	}
}

func representativeSubject(count int64) string {
	if count <= 1 {
		return "一位用户"
	}
	return "一位用户等" + strconv.FormatInt(count, 10) + "人"
}

func actorPronoun(perspective ActorPerspective) string {
	if perspective == ActorSelf {
		return "我"
	}
	return "TA"
}

// EvidenceText instantiates the cloud-side conclusion sentence for a single
// impact evidence fact (drill-down detail row). It is content-anchored and
// privacy-safe: it never names the user who produced the impact ("有人").
// App surfaces render this value directly (global acceptance G2).
func EvidenceText(helpType string, action string, contentTitle string, perspective ActorPerspective) string {
	pronoun := actorPronoun(perspective)
	titleClause := ""
	if title := strings.TrimSpace(contentTitle); title != "" {
		titleClause = "《" + title + "》"
	}
	switch strings.TrimSpace(helpType) {
	case HelpRelationship:
		return "有人通过" + pronoun + "建立了新连接"
	case HelpCommunity:
		return "有人加入了相关圈子"
	case HelpDecision:
		if titleClause != "" {
			return "有人通过" + pronoun + "的" + titleClause + "关注了相关对象"
		}
		return "有人通过" + pronoun + "的内容关注了相关对象"
	case HelpKnowledge:
		return "有人读完了" + pronoun + "的内容"
	case HelpSpread:
		if titleClause != "" {
			return "有人转发了" + pronoun + "的" + titleClause
		}
		return "有人转发了" + pronoun + "的内容"
	case HelpAudience:
		if titleClause != "" {
			return "有人看过" + pronoun + "的" + titleClause
		}
		return "有人看过" + pronoun + "的内容"
	default:
		return ""
	}
}
