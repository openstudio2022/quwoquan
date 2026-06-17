package application

import (
	"strings"

	rtimpact "quwoquan_service/runtime/impact"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

// DecorateAuthorImpact 在云侧按 viewer 视角补齐影响结论句（G2：端禁止本地拼装文案）。
// 规格语义：强调「帮助结果」而非运营指标——「23人加入相关圈子 / 12人收藏了TA的内容 /
// 8人通过TA认识新朋友」；viewer 为作者本人时使用第一人称（我的影响力）。
func DecorateAuthorImpact(summary persistence.AuthorImpactSummary, viewerIsAuthor bool) persistence.AuthorImpactSummary {
	for i := range summary.Items {
		if strings.TrimSpace(summary.Items[i].PrimaryText) != "" {
			continue
		}
		perspective := rtimpact.ActorTA
		if viewerIsAuthor {
			perspective = rtimpact.ActorSelf
		}
		summary.Items[i].PrimaryText = rtimpact.PrimaryText(
			summary.Items[i].HelpType,
			summary.Items[i].Action,
			summary.Items[i].Count,
			perspective,
		)
	}
	return summary
}
