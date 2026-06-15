package application

import (
	"strconv"
	"strings"

	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

// DecorateAuthorImpact 在云侧按 viewer 视角补齐影响结论句（G2：端禁止本地拼装文案）。
// 规格语义：强调「帮助结果」而非运营指标——「23人加入相关圈子 / 12人收藏了TA的内容 /
// 8人通过TA认识新朋友」；viewer 为作者本人时使用第一人称（我的影响力）。
func DecorateAuthorImpact(summary persistence.AuthorImpactSummary, viewerIsAuthor bool) persistence.AuthorImpactSummary {
	for i := range summary.Items {
		if strings.TrimSpace(summary.Items[i].DisplayText) != "" {
			continue
		}
		summary.Items[i].DisplayText = authorImpactDisplayText(
			summary.Items[i].HelpType,
			summary.Items[i].Count,
			viewerIsAuthor,
		)
	}
	return summary
}

func authorImpactDisplayText(helpType string, count int64, viewerIsAuthor bool) string {
	if count <= 0 {
		return ""
	}
	n := strconv.FormatInt(count, 10)
	pronoun := "TA"
	if viewerIsAuthor {
		pronoun = "我"
	}
	switch strings.TrimSpace(helpType) {
	case persistence.AuthorImpactHelpCommunity:
		return n + "人加入相关圈子"
	case persistence.AuthorImpactHelpDecision:
		return n + "人收藏了" + pronoun + "的内容"
	case persistence.AuthorImpactHelpRelationship:
		return n + "人通过" + pronoun + "认识新朋友"
	case persistence.AuthorImpactHelpKnowledge:
		return n + "人因" + pronoun + "的分享有所收获"
	case persistence.AuthorImpactHelpSpread:
		return n + "人转发了" + pronoun + "的内容"
	case persistence.AuthorImpactHelpAudience:
		return n + "人看过" + pronoun + "的内容"
	default:
		return ""
	}
}
