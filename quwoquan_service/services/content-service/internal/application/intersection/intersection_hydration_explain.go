package intersection

import (
	"fmt"
	"strings"

	"quwoquan_service/services/content-service/internal/generated"
)

func representativeActorForReason(r IntersectionReasonView, anchor IntersectionPointView) *IntersectionRepresentativeActorView {
	if actor, ok := representativeActorEvidenceForReason(r); ok {
		return &IntersectionRepresentativeActorView{
			ActorID:         strings.TrimSpace(actor.ActorID),
			DisplayName:     strings.TrimSpace(actor.DisplayName),
			AvatarURL:       actor.AvatarURL,
			RelationLabel:   normalizedEvidenceRelationLabel(actor, anchor),
			PrivacyState:    normalizedPrivacyState(actor.PrivacyState),
			Target:          actor.Target,
			EvidenceRank:    evidenceKindRank(actor.SourceRef, "fact"),
			SnapshotVersion: firstNonEmpty(actor.SnapshotVersion, r.PointSummarySnapshotID),
		}
	}
	name := representativeActorName(r, anchor)
	if name == "" {
		return nil
	}
	target := intersectionTargetForReason(r)
	actorID := ""
	if target != nil && target.ObjectKind == "person" {
		actorID = target.ObjectID
	}
	privacyState := "visible"
	if strings.HasPrefix(name, "一位") {
		privacyState = "anonymous"
	}
	return &IntersectionRepresentativeActorView{
		ActorID:         actorID,
		DisplayName:     name,
		AvatarURL:       r.AvatarURL,
		RelationLabel:   representativeRelationLabel(anchor.SourceRef),
		PrivacyState:    privacyState,
		Target:          target,
		EvidenceRank:    evidenceKindRank(anchor.SourceRef, anchor.PointClass),
		SnapshotVersion: r.PointSummarySnapshotID,
	}
}

func representativeActorEvidenceForReason(r IntersectionReasonView) (IntersectionActorEvidenceView, bool) {
	for _, actor := range r.ActorEvidence {
		if strings.TrimSpace(actor.DisplayName) == "" {
			continue
		}
		if strings.TrimSpace(actor.PrivacyState) == "hidden" {
			continue
		}
		return actor, true
	}
	return IntersectionActorEvidenceView{}, false
}

func normalizedEvidenceRelationLabel(actor IntersectionActorEvidenceView, anchor IntersectionPointView) string {
	if isMeaningfulRepresentativeRelationLabel(actor.RelationLabel) {
		return strings.TrimSpace(actor.RelationLabel)
	}
	return representativeRelationLabel(firstNonEmpty(actor.SourceRef, anchor.SourceRef))
}

func normalizedPrivacyState(value string) string {
	if strings.TrimSpace(value) == "" {
		return "visible"
	}
	return strings.TrimSpace(value)
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func representativeActorName(r IntersectionReasonView, anchor IntersectionPointView) string {
	if actor := r.RepresentativeActor; actor != nil {
		if name := strings.TrimSpace(actor.DisplayName); name != "" {
			return name
		}
	}
	for _, v := range anchor.SampleVisuals {
		if name := strings.TrimSpace(v.DisplayName); name != "" {
			return name
		}
	}
	if name := strings.TrimSpace(anchor.SampleText); name != "" {
		if idx := strings.Index(name, "、"); idx > 0 {
			return strings.TrimSpace(name[:idx])
		}
		if idx := strings.Index(name, ","); idx > 0 {
			return strings.TrimSpace(name[:idx])
		}
		return name
	}
	if name := strings.TrimSpace(r.DisplayName); name != "" && r.ObjectKind == "person" {
		return name
	}
	switch anchor.SourceRef {
	case "sameSchool", "sameDepartment", "sameMajor", "sameCohort", "alumni", "alumniHere":
		return "一位校友"
	case "sameCompany", "sameTeam", "sameIndustry", "colleagueHere":
		return "一位同事"
	case "commonContact":
		return "一位联系人"
	default:
		return "一位用户"
	}
}

func representativeRelationLabel(sourceRef string) string {
	switch sourceRef {
	case "sharedFollowees", "commonFollower", "followeeInObject", "followeeVisited", "followeeViewing", "followeeDiscussedThis":
		return "你关注的人"
	case "commonContact":
		return "联系人"
	case "sameSchool", "sameDepartment", "sameMajor", "sameCohort", "alumni", "alumniHere":
		return "校友"
	case "sameCompany", "sameTeam", "sameIndustry", "colleagueHere":
		return "同事"
	case "sharedCircle", "coMemberCircle":
		return "同圈成员"
	default:
		return ""
	}
}

func representativeSubject(r IntersectionReasonView, anchor IntersectionPointView, n int) string {
	name := representativeActorName(r, anchor)
	relation := normalizedRepresentativeRelationLabel(r, anchor)
	if name == "" {
		if n <= 1 {
			if relation != "" {
				return "一位" + relation
			}
			return "一位用户"
		}
		if relation != "" {
			return fmt.Sprintf("%d位%s", n, relation)
		}
		return fmt.Sprintf("%d人", n)
	}
	base := name
	if relation != "" && !strings.HasPrefix(name, "一位") {
		base = relation + name
	}
	if n <= 1 {
		return base
	}
	return fmt.Sprintf("%s等%d人", base, n)
}

func countedRepresentativeSubject(r IntersectionReasonView, anchor IntersectionPointView, n int) string {
	relation := normalizedRepresentativeRelationLabel(r, anchor)
	if n <= 1 {
		if relation != "" {
			return "1位" + relation
		}
		return "1位用户"
	}
	if relation != "" {
		return fmt.Sprintf("%d位%s", n, relation)
	}
	return fmt.Sprintf("%d位用户", n)
}

func representativeSubjectWithUnit(r IntersectionReasonView, anchor IntersectionPointView, n int, unit string) string {
	base := representativeSubject(r, anchor, 1)
	if n <= 1 {
		return base
	}
	return fmt.Sprintf("%s等%d%s", base, n, unit)
}

func normalizedRepresentativeRelationLabel(r IntersectionReasonView, anchor IntersectionPointView) string {
	if actor := r.RepresentativeActor; actor != nil {
		raw := strings.TrimSpace(actor.RelationLabel)
		if isMeaningfulRepresentativeRelationLabel(raw) {
			return raw
		}
	}
	return representativeRelationLabel(anchor.SourceRef)
}

func isMeaningfulRepresentativeRelationLabel(label string) bool {
	switch strings.TrimSpace(label) {
	case "", "共同点赞", "共同讨论", "共同传播", "共同关注", "都关注此标签", "同行足迹", "同好":
		return false
	default:
		return true
	}
}

func interactionActionPhraseForReason(r IntersectionReasonView) string {
	hasLike := false
	hasComment := false
	hasShare := false
	for _, actor := range r.ActorEvidence {
		if actor.LikeCount > 0 || strings.Contains(actor.ActionSummaryText, "赞") {
			hasLike = true
		}
		if actor.CommentCount > 0 || strings.Contains(actor.ActionSummaryText, "评") || strings.Contains(actor.ActionSummaryText, "讨论") {
			hasComment = true
		}
		if actor.ShareCount > 0 || strings.Contains(actor.ActionSummaryText, "转发") || strings.Contains(actor.ActionSummaryText, "分享") {
			hasShare = true
		}
	}
	parts := make([]string, 0, 3)
	if hasLike {
		parts = append(parts, "赞过")
	}
	if hasComment {
		parts = append(parts, "评论过")
	}
	if hasShare {
		parts = append(parts, "转发过")
	}
	switch len(parts) {
	case 0:
		return ""
	case 1:
		return parts[0]
	case 2:
		return parts[0] + "和" + parts[1]
	default:
		return parts[0] + "、" + parts[1] + "并" + parts[2]
	}
}

func actionHintsForReason(r IntersectionReasonView, target *IntersectionTargetView) []IntersectionActionHintView {
	src := strings.TrimSpace(r.Source)
	if anchor, ok := explainAnchorPoint(r); ok && strings.TrimSpace(anchor.SourceRef) != "" {
		src = anchor.SourceRef
	}
	keys := actionKeysForKind(src)
	out := make([]IntersectionActionHintView, 0, len(keys))
	for i, key := range keys {
		out = append(out, IntersectionActionHintView{
			ActionKey:          key,
			Label:              actionLabelForKey(key),
			Target:             target,
			IsPrimary:          i == 0,
			Priority:           i + 1,
			ActionTier:         actionTierForKey(key),
			RequiredGates:      requiredGatesForKey(key),
			TargetAvailability: actionTargetAvailabilityForKey(key),
			Dispatch:           actionDispatchForKey(key),
		})
	}
	return out
}

// actionKeysForKind 查 kind → 行动建议 actionKey 有序列表
// （generated.IntersectionActionKeysByKind，源 registry.actionHintsByKind）。
// 未登记 kind 兜底 ask_assistant（端只渲染，不按 kind 猜测下一步）。
func actionKeysForKind(kind string) []string {
	if keys := generated.IntersectionActionKeysByKind[strings.TrimSpace(kind)]; len(keys) > 0 {
		return keys
	}
	return []string{"ask_assistant"}
}

// actionLabelForKey 查 actionKey → 终端 UI 短标签
// （generated.IntersectionActionLabelByKey，源 registry.actionLabelByKey）。
// 未登记 key 兜底 ask_assistant 标签（解释这条交集）。
func actionLabelForKey(key string) string {
	if v, ok := generated.IntersectionActionLabelByKey[key]; ok {
		return v
	}
	return generated.IntersectionActionLabelByKey["ask_assistant"]
}

// actionTierForKey 查 actionKey → 行动阶梯层级
// （generated.IntersectionActionTierByKey，源 registry.actionKeyMeta.tier）。
// 未登记 key 安全兜底 light，避免未知灰度 key 被误判为重社交行动。
func actionTierForKey(key string) string {
	if v, ok := generated.IntersectionActionTierByKey[strings.TrimSpace(key)]; ok && strings.TrimSpace(v) != "" {
		return v
	}
	return "light"
}

// requiredGatesForKey 查 actionKey → 前置安全门列表
// （generated.IntersectionRequiredGatesByActionKey，源 registry.actionKeyMeta.requiredGates）。
// 返回副本，防止调用方误改 generated 表。
func requiredGatesForKey(key string) []string {
	gates := generated.IntersectionRequiredGatesByActionKey[strings.TrimSpace(key)]
	if len(gates) == 0 {
		return []string{}
	}
	out := make([]string, len(gates))
	copy(out, gates)
	return out
}

// actionTargetAvailabilityForKey 查 actionKey → available|deferred
// （generated.IntersectionActionTargetAvailabilityByKey，源 registry.actionKeyMeta.targetAvailability）。
// 未登记 key 兜底 available：未知轻行动只可按 target 尝试导航，不会被误判为规划态。
func actionTargetAvailabilityForKey(key string) string {
	if v, ok := generated.IntersectionActionTargetAvailabilityByKey[strings.TrimSpace(key)]; ok && strings.TrimSpace(v) != "" {
		return v
	}
	return "available"
}

// actionDispatchForKey 查 actionKey → 端交互 handler 路由类别
// （generated.IntersectionActionDispatchByKey，源 registry.actionKeyMeta.dispatch）。
// 未登记 key 兜底 navigate，保证端只走对象导航安全路径，不误触发约伴/私信/助手。
func actionDispatchForKey(key string) string {
	if v, ok := generated.IntersectionActionDispatchByKey[strings.TrimSpace(key)]; ok && strings.TrimSpace(v) != "" {
		return v
	}
	return "navigate"
}

// explainAnchorPoint 取结论句锚点：可见点中挖掘强度最高者（§9.8 evidenceKindRank）。
// hydratePointSummary 已先把 r.IntersectionPoints 收敛为可见点，这里直接择强。
func explainAnchorPoint(r IntersectionReasonView) (IntersectionPointView, bool) {
	best := IntersectionPointView{}
	bestRank := 1 << 30
	found := false
	for _, p := range r.IntersectionPoints {
		if p.Visibility == "hidden" {
			continue
		}
		rank := evidenceKindRank(p.SourceRef, p.PointClass)
		if !found || rank < bestRank {
			best = p
			bestRank = rank
			found = true
		}
	}
	return best, found
}

// anchorAggregateCount 取锚点对应的可枚举计数：单一真相源 = point.Count（聚合型单点
// 携带计数，桥接型也统一为单聚合点 Count=n，见 source.followeeVisitedReason）；缺省
// 按同 kind 兄弟点数兜底（兼容逐条点），最终回落 1。R-ID01：不再有 reason 级 SharedCount。
func anchorAggregateCount(r IntersectionReasonView, anchor IntersectionPointView) int {
	if anchor.Count > 0 {
		return anchor.Count
	}
	c := 0
	for _, p := range r.IntersectionPoints {
		if p.SourceRef == anchor.SourceRef {
			c++
		}
	}
	if c > 0 {
		return c
	}
	return 1
}

// explainPrimaryText 按 §17.1「主语[代表人+数量+关系限定] + 谓语 + 宾语」实例化事实结论句；
// affinity 走概率通道分支。kind 取 §5.4 注册表标准名；未登记 kind 返回空（不造假）。
func explainPrimaryText(r IntersectionReasonView, anchor IntersectionPointView) string {
	if r.IntersectionClass == "affinity" {
		return affinityPrimaryText(r, anchor)
	}
	n := anchorAggregateCount(r, anchor)
	switch anchor.SourceRef {
	case "sharedFollowees", "commonFollower":
		objectName := renderedObjectNameForReason(r, anchor.SourceRef)
		if objectName == "" {
			return ""
		}
		return fmt.Sprintf("%s也关注了%s", representativeSubject(r, anchor, n), objectName)
	case "commonContact":
		objectName := concreteObjectNameForReason(r)
		if objectName == "" {
			return fmt.Sprintf("%s都是你们的共同联系人", representativeSubject(r, anchor, n))
		}
		return fmt.Sprintf("%s都是你和%s的共同联系人", representativeSubject(r, anchor, n), objectName)
	case "sharedCircle", "coMemberCircle":
		objectName := renderedObjectNameForReason(r, anchor.SourceRef)
		if objectName == "" {
			return ""
		}
		return fmt.Sprintf("%s都加入了%s", representativeSubject(r, anchor, n), objectName)
	case "coCommented", "sharedDiscussion":
		objectName := renderedObjectNameForReason(r, anchor.SourceRef)
		if objectName == "" {
			return ""
		}
		if action := interactionActionPhraseForReason(r); action != "" {
			return fmt.Sprintf("%s%s%s", representativeSubject(r, anchor, n), action, objectName)
		}
		return fmt.Sprintf("%s都讨论过%s", representativeSubject(r, anchor, n), objectName)
	case "coSharedContent":
		objectName := renderedObjectNameForReason(r, anchor.SourceRef)
		if objectName == "" {
			return ""
		}
		if action := interactionActionPhraseForReason(r); action != "" {
			return fmt.Sprintf("%s%s%s", representativeSubject(r, anchor, n), action, objectName)
		}
		return fmt.Sprintf("%s都转发过%s", representativeSubject(r, anchor, n), objectName)
	case "coCreatedContent":
		objectName := renderedObjectNameForReason(r, anchor.SourceRef)
		if objectName == "" {
			return ""
		}
		return fmt.Sprintf("%s都共创过%s", representativeSubject(r, anchor, n), objectName)
	case "coVisitedEntity":
		objectName := renderedObjectNameForReason(r, anchor.SourceRef)
		if objectName == "" {
			return ""
		}
		return fmt.Sprintf("%s都去过%s", representativeSubject(r, anchor, n), objectName)
	case "coWishlistedEntity":
		objectName := renderedObjectNameForReason(r, anchor.SourceRef)
		if objectName == "" {
			return ""
		}
		return fmt.Sprintf("%s都想去%s", representativeSubject(r, anchor, n), objectName)
	case "sharedEntityAttention":
		objectName := renderedObjectNameForReason(r, anchor.SourceRef)
		if objectName == "" {
			return ""
		}
		return fmt.Sprintf("%s也关注了%s", representativeSubject(r, anchor, n), objectName)
	case "followeeVisited":
		objectName := renderedObjectNameForReason(r, anchor.SourceRef)
		if objectName == "" {
			return ""
		}
		return fmt.Sprintf("%s来过%s", countedRepresentativeSubject(r, anchor, n), objectName)
	case "followeeInObject":
		objectName := renderedObjectNameForReason(r, anchor.SourceRef)
		if objectName == "" {
			return ""
		}
		return fmt.Sprintf("%s在%s", representativeSubject(r, anchor, n), objectName)
	case "followeeViewing":
		objectName := renderedObjectNameForReason(r, anchor.SourceRef)
		if objectName == "" {
			return ""
		}
		return fmt.Sprintf("%s正在看%s", representativeSubject(r, anchor, n), objectName)
	case "followeeDiscussedThis":
		objectName := renderedObjectNameForReason(r, anchor.SourceRef)
		if objectName == "" {
			return ""
		}
		return fmt.Sprintf("%s正在讨论%s", representativeSubject(r, anchor, n), objectName)
	case "sharedTagSample":
		objectName := sharedTagSampleObjectName(r, anchor)
		if objectName == "" {
			return ""
		}
		subject := sharedTagSampleSubject(r, anchor, n)
		if subject == "" {
			return ""
		}
		if r.Source == "circleTag" {
			return fmt.Sprintf("%s在圈子里常看%s", subject, objectName)
		}
		return fmt.Sprintf("%s都关注%s", subject, objectName)
	default:
		return ""
	}
}

func concreteObjectNameForReason(r IntersectionReasonView) string {
	name := strings.TrimSpace(r.DisplayName)
	switch name {
	case "", "同游", "同好", "同校", "这里", "这个对象", "这些内容", "这些主题", "相同内容", "相同的人":
		return ""
	default:
		return name
	}
}

func renderedObjectNameForReason(r IntersectionReasonView, kind string) string {
	name := concreteObjectNameForReason(r)
	if name == "" {
		return ""
	}
	switch kind {
	case "coCommented", "sharedDiscussion", "coSharedContent", "coCreatedContent", "followeeViewing", "followeeDiscussedThis":
		return "《" + name + "》"
	default:
		return "「" + name + "」"
	}
}

func sharedTagSampleObjectName(r IntersectionReasonView, anchor IntersectionPointView) string {
	if name := concreteObjectNameForReason(r); name != "" {
		return name
	}
	name := strings.TrimSpace(anchor.SampleText)
	if idx := strings.IndexAny(name, "、,"); idx > 0 {
		name = strings.TrimSpace(name[:idx])
	}
	if name != "" {
		return name
	}
	if name := strings.TrimSpace(anchor.DisplayText); name != "" {
		return name
	}
	return strings.TrimSpace(anchor.Label)
}

func sharedTagSampleSubject(r IntersectionReasonView, anchor IntersectionPointView, n int) string {
	if strings.TrimSpace(r.Source) == "circleTag" {
		return "你"
	}
	if strings.TrimSpace(r.ActionTargetID) != "" &&
		strings.TrimSpace(r.ActionTargetID) == strings.TrimSpace(r.RelationObjectID) {
		switch objectTypeForTarget(strings.TrimSpace(r.ObjectKind), strings.TrimSpace(r.ActionTargetID), routeIDForObjectKind(strings.TrimSpace(r.ObjectKind))) {
		case "homepage":
			return "你和这里"
		case "circle":
			return "你和这个圈子"
		}
	}
	return representativeSubject(r, anchor, n)
}

// affinityPrimaryText 概率通道结论句（必须配 confidenceLabel 标注「推荐」，§17.5/§3.4）。
func affinityPrimaryText(r IntersectionReasonView, anchor IntersectionPointView) string {
	src := strings.ToLower(r.Source)
	objectName := renderedObjectNameForReason(r, anchor.SourceRef)
	switch {
	case anchor.SourceRef == "sharedCircle" || strings.Contains(src, "circle"):
		if objectName != "" {
			return "你的圈子里最近在看" + objectName
		}
		return "你的圈子里最近在看这些"
	case anchor.SourceRef == "followeeViewing" || strings.Contains(src, "friend") || strings.Contains(src, "follow"):
		if objectName != "" {
			return "你关注的人最近在看" + objectName
		}
		return "你关注的人最近在看这些"
	default:
		if objectName != "" {
			return "为你推荐" + objectName
		}
		return "为你推荐的相关内容"
	}
}

// affinityConfidenceLabel 概率通道置信标注（端只对 affinity 展示「推荐」语义）。
func affinityConfidenceLabel(r IntersectionReasonView) string {
	switch r.Dimension {
	case "relationship", "identity":
		return "推荐认识"
	default:
		return "可能感兴趣"
	}
}

// affinityModelReasonBucket 概率通道模型理由桶（埋点/灰度用，端不展示原文）。
func affinityModelReasonBucket(r IntersectionReasonView) string {
	src := strings.TrimSpace(r.Source)
	if src == "" {
		src = strings.TrimSpace(r.Dimension)
	}
	if src == "" {
		src = "general"
	}
	return "affinity:" + src
}

// explainSecondaryText 列表入口灰色辅助说明（§17.2，≤2 项）：罗列锚点之外的其它
// 维度证据组名词，跨 kind 取样（同 kind 兄弟点不重复罗列）。紧凑 surface 不展示。
func explainSecondaryText(r IntersectionReasonView, anchor IntersectionPointView) string {
	parts := make([]string, 0, 2)
	for _, p := range r.IntersectionPoints {
		if p.PointID == anchor.PointID || p.SourceRef == anchor.SourceRef {
			continue
		}
		label := strings.TrimSpace(p.Label)
		if label == "" {
			label = strings.TrimSpace(p.DisplayText)
		}
		if label == "" {
			continue
		}
		if p.Count > 1 {
			parts = append(parts, fmt.Sprintf("%s %d", label, p.Count))
		} else {
			parts = append(parts, label)
		}
		if len(parts) >= 2 {
			break
		}
	}
	return strings.Join(parts, " · ")
}

// explainConnectionSummary 对象页「连接说明」（仅 viewer↔对象关系类 reason、且共同点≥2 时产出）。
func explainConnectionSummary(r IntersectionReasonView) string {
	switch r.RelationKind {
	case "mutual", "following", "followed_by", "none":
	default:
		return ""
	}
	if r.TotalPointCount < 2 {
		return ""
	}
	return fmt.Sprintf("你们已有%d个共同点", r.TotalPointCount)
}

// Summary 我的主页聚合摘要：各维度计数 + 自上次查看未读数。
