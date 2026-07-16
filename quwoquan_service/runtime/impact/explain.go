package impact

import (
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

func actorPronoun(perspective ActorPerspective) string {
	if perspective == ActorSelf {
		return "你"
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
