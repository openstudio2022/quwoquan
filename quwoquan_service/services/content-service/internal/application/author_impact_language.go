package application

import (
	"strings"

	rtimpact "quwoquan_service/runtime/impact"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

// DecorateAuthorImpact 在云侧按 viewer 视角补齐影响结论句（G2：端禁止本地拼装文案）。
// 规格语义：强调「帮助结果」而非运营指标，且禁止“收藏/认识新朋友”等退场词。
// viewer 为作者本人时使用第一人称（我的影响力）。
func DecorateAuthorImpact(summary persistence.AuthorImpactSummary, viewerIsAuthor bool) persistence.AuthorImpactSummary {
	for i := range summary.Items {
		perspective := rtimpact.ActorTA
		if viewerIsAuthor {
			perspective = rtimpact.ActorSelf
		}
		if strings.TrimSpace(summary.Items[i].PrimaryText) == "" {
			summary.Items[i].PrimaryText = rtimpact.PrimaryText(
				summary.Items[i].HelpType,
				summary.Items[i].Action,
				summary.Items[i].Count,
				perspective,
			)
		}
		if summary.Items[i].RepresentativeActor == nil && summary.Items[i].Count > 0 {
			summary.Items[i].RepresentativeActor = &persistence.ImpactRepresentativeActor{
				DisplayName:   "一位用户",
				RelationLabel: "被影响的人",
				PrivacyState:  "anonymous",
			}
		}
		if strings.TrimSpace(summary.Items[i].IconKey) == "" {
			summary.Items[i].IconKey = impactIconKey(summary.Items[i].HelpType)
		}
		if len(summary.Items[i].ActionHints) == 0 {
			summary.Items[i].ActionHints = impactActionHints(summary.Items[i])
		}
		// WS3 旅行影响力真算（§22.5 / §23.4 三元组正交）：由真实聚合的 IntersectionTagRef 派生
		// 旅行下钻目标对象类型（route/photo_spot/gear/place），被计数对象恒为 person（受影响的人）。
		// 非旅行信号不造假（留空，端按 helpType 兜底）。
		if summary.Items[i].CountTarget == nil {
			if target := travelImpactCountTarget(summary.Items[i]); target != nil {
				summary.Items[i].CountTarget = target
				if strings.TrimSpace(summary.Items[i].CountObjectKind) == "" {
					summary.Items[i].CountObjectKind = impactCountedActorKind
				}
			}
		}
	}
	return summary
}

// impactCountedActorKind 旅行影响力被计数对象类型：受影响的「人」（§22.5 targetObjectKind 为
// 下钻目标对象 route/photo_spot/place，countObjectKind 恒为可计数闭集中的 person）。
const impactCountedActorKind = "person"

// travelImpactCountTarget 三元组正交（§23.4）真算旅行影响力数字下钻目标：由真实聚合的
// IntersectionTagRef 命名空间派生 route/photo_spot/gear/place；非旅行信号返回 nil（不造假）。
// 与 IntersectionReason.verticalForReason 共用旅行 tag 真相源（isTravelPhotographyTag 同集语义），
// 使「旅行影响力类型」由真实行为聚合的 tagRef 产出而非仅靠 seed。
func travelImpactCountTarget(item persistence.AuthorImpactItem) *persistence.ImpactTarget {
	kind := travelImpactObjectKindForTag(item.TagRef)
	if kind == "" {
		return nil
	}
	return &persistence.ImpactTarget{
		ObjectKind: kind,
		RouteID:    routeIDForObjectKind(kind),
	}
}

// travelImpactObjectKindForTag tagRef 命名空间 → 旅行下钻目标对象类型（registry.objectKinds 闭集子集）。
// photo_spot/spot 优先于 route（"tag/travel/photo_spot" 先判 spot）；gear 次之；
// 其余命中旅行/地点 tag 归 place；非旅行 tag 返回空（routeId 仍由 generated codegen 单源解析）。
func travelImpactObjectKindForTag(tagRef string) string {
	t := strings.ToLower(strings.TrimSpace(tagRef))
	if t == "" {
		return ""
	}
	switch {
	case strings.Contains(t, "photo_spot") || strings.Contains(t, "spot"):
		return "photo_spot"
	case strings.Contains(t, "route"):
		return "route"
	case strings.Contains(t, "gear"):
		return "gear"
	case strings.Contains(t, "travel") || strings.Contains(t, "place"):
		return "place"
	}
	return ""
}

// impactIconKey 查 helpType → 端图标语义键（rtimpact.IconKeyByHelpType，源 registry.helpTypes[].iconKey）。
// 未登记 helpType 兜底 DefaultIconKey（cascadePath）。
func impactIconKey(helpType string) string {
	if key, ok := rtimpact.IconKeyByHelpType[strings.TrimSpace(helpType)]; ok {
		return key
	}
	return rtimpact.DefaultIconKey
}

// impactActionHints 查 helpType → 影响力卡主行动（rtimpact.SummaryActionByHelpType，源 registry.helpTypes[].summaryAction）。
// 未登记 helpType 兜底 DefaultSummaryAction（发布跟进）。
func impactActionHints(item persistence.AuthorImpactItem) []persistence.ImpactActionHint {
	action, ok := rtimpact.SummaryActionByHelpType[strings.TrimSpace(item.HelpType)]
	if !ok {
		action = rtimpact.DefaultSummaryAction
	}
	return []persistence.ImpactActionHint{{
		ActionKey: action.Key,
		Label:     action.Label,
		IsPrimary: true,
		Priority:  1,
	}}
}
