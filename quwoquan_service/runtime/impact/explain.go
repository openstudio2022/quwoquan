package impact

import (
	"strconv"
	"strings"
)

const (
	HelpRelationship = "relationship"
	HelpCommunity    = "community"
	HelpDecision     = "decision"
	HelpKnowledge    = "knowledge"
	HelpSpread       = "spread"
	HelpAudience     = "audience"
)

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
	n := strconv.FormatInt(count, 10)
	switch strings.TrimSpace(helpType) {
	case HelpRelationship:
		switch strings.TrimSpace(action) {
		case "establish_connection":
			return n + "人在这里建立了新连接"
		default:
			return n + "人通过" + actorPronoun(perspective) + "认识新朋友"
		}
	case HelpCommunity:
		switch strings.TrimSpace(action) {
		case "start_discussion":
			return n + "个讨论正在这里发生"
		default:
			return n + "人加入相关圈子"
		}
	case HelpDecision:
		return n + "人收藏了" + actorPronoun(perspective) + "的内容"
	case HelpKnowledge:
		return n + "人因" + actorPronoun(perspective) + "的分享有所收获"
	case HelpSpread:
		switch strings.TrimSpace(action) {
		case "active_participation":
			return n + "人最近参与了这里"
		default:
			return n + "人转发了" + actorPronoun(perspective) + "的内容"
		}
	case HelpAudience:
		return n + "人看过" + actorPronoun(perspective) + "的内容"
	default:
		return ""
	}
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
			return "有人收藏了" + pronoun + "的" + titleClause
		}
		return "有人收藏了" + pronoun + "的内容"
	case HelpKnowledge:
		return "有人因" + pronoun + "的分享有所收获"
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
