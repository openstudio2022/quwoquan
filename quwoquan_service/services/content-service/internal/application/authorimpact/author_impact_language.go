package authorimpact

import (
	"strings"

	rtimpact "quwoquan_service/runtime/impact"
	"quwoquan_service/services/content-service/internal/application/ports"
	"quwoquan_service/services/content-service/internal/generated"
)

// DecorateAuthorImpact only attaches deterministic metadata that can be
// derived from the persisted aggregate. It must not fabricate a primaryText or
// representative actor: until the projection carries a named actor and an
// evidence-bound object target, the App receives an empty primaryText and
// fails the row closed.
func DecorateAuthorImpact(summary ports.AuthorImpactSummary, viewerIsAuthor bool) ports.AuthorImpactSummary {
	_ = viewerIsAuthor
	for i := range summary.Items {
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
func travelImpactCountTarget(item ports.AuthorImpactItem) *ports.ImpactTarget {
	kind := travelImpactObjectKindForTag(item.TagRef)
	if kind == "" {
		return nil
	}
	return &ports.ImpactTarget{
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

func routeIDForObjectKind(kind string) string {
	return generated.IntersectionRouteIDByObjectKind[strings.TrimSpace(kind)]
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
func impactActionHints(item ports.AuthorImpactItem) []ports.ImpactActionHint {
	action, ok := rtimpact.SummaryActionByHelpType[strings.TrimSpace(item.HelpType)]
	if !ok {
		action = rtimpact.DefaultSummaryAction
	}
	return []ports.ImpactActionHint{{
		ActionKey: action.Key,
		Label:     action.Label,
		IsPrimary: true,
		Priority:  1,
	}}
}
