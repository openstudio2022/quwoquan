package intersection

import (
	"strconv"
	"strings"

	generated "quwoquan_service/services/content-service/generated/content/post"
)

func RepresentativeActorForReason(r IntersectionReasonView, anchor IntersectionPointView) *IntersectionRepresentativeActorView {
	if actor, ok := representativeActorEvidenceForReason(r); ok {
		return &IntersectionRepresentativeActorView{
			ActorID:         strings.TrimSpace(actor.ActorID),
			DisplayName:     strings.TrimSpace(actor.DisplayName),
			AvatarURL:       actor.AvatarURL,
			RelationLabel:   normalizedEvidenceRelationLabel(actor, anchor),
			PrivacyState:    normalizedPrivacyState(actor.PrivacyState),
			Target:          actor.Target,
			EvidenceRank:    EvidenceKindRank(actor.SourceRef, "fact"),
			SnapshotVersion: firstNonEmpty(actor.SnapshotVersion, r.PointSummarySnapshotID),
		}
	}
	name := representativeActorName(r, anchor)
	if name == "" {
		return nil
	}
	target := IntersectionTargetForReason(r)
	actorID := ""
	if target != nil && target.ObjectKind == "person" {
		actorID = target.ObjectID
	}
	privacyState := "visible"
	if isAnonymousActorName(name) {
		privacyState = "anonymous"
	}
	return &IntersectionRepresentativeActorView{
		ActorID:         actorID,
		DisplayName:     name,
		AvatarURL:       r.AvatarURL,
		RelationLabel:   representativeRelationLabel(anchor.SourceRef),
		PrivacyState:    privacyState,
		Target:          target,
		EvidenceRank:    EvidenceKindRank(anchor.SourceRef, anchor.PointClass),
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
	return anonymousActorText(anchor.SourceRef)
}

// isAnonymousActorName 判断代表人名是否是注册表下发的匿名称谓（而非真实人名）。
// 匿名代表人的隐私态是 anonymous，也不得再被冠以关系限定前缀。
func isAnonymousActorName(name string) bool {
	name = strings.TrimSpace(name)
	if name == "" {
		return false
	}
	if name == resolve(generated.IntersectionAnonymousActorLabelDefault) {
		return true
	}
	for kind := range generated.IntersectionAnonymousActorLabelByKind {
		if anonymousActorText(kind) == name {
			return true
		}
	}
	return false
}

// representativeRelationLabel 查 kind → 代表人关系限定词
// （generated.IntersectionRelationLabelByKind，源 registry.presentationText.relationLabels）。
func representativeRelationLabel(sourceRef string) string {
	return relationLabelText(sourceRef)
}

func representativeSubject(r IntersectionReasonView, anchor IntersectionPointView, n int) string {
	name := representativeActorName(r, anchor)
	relation := normalizedRepresentativeRelationLabel(r, anchor)
	if name == "" {
		if n <= 1 {
			if relation != "" {
				return subjectPatternText("anonymousWithRelation", map[string]string{"relation": relation})
			}
			return anonymousActorText("")
		}
		if relation != "" {
			return subjectPatternText("countedWithRelation", map[string]string{
				"count": strconv.Itoa(n), "relation": relation,
			})
		}
		return subjectPatternText("countedPlain", map[string]string{"count": strconv.Itoa(n)})
	}
	base := name
	if relation != "" && !isAnonymousActorName(name) {
		base = subjectPatternText("relationPrefixedName", map[string]string{
			"relation": relation, "name": name,
		})
	}
	if n <= 1 {
		return base
	}
	return subjectPatternText("namedWithMore", map[string]string{
		"subject": base, "count": strconv.Itoa(n),
	})
}

func countedRepresentativeSubject(r IntersectionReasonView, anchor IntersectionPointView, n int) string {
	relation := normalizedRepresentativeRelationLabel(r, anchor)
	if n <= 1 {
		if relation != "" {
			return subjectPatternText("singleWithRelation", map[string]string{"relation": relation})
		}
		return subjectPatternText("singleUnknownRelation", nil)
	}
	if relation != "" {
		return subjectPatternText("countedWithRelation", map[string]string{
			"count": strconv.Itoa(n), "relation": relation,
		})
	}
	return subjectPatternText("countedUnknownRelation", map[string]string{"count": strconv.Itoa(n)})
}

func representativeSubjectWithUnit(r IntersectionReasonView, anchor IntersectionPointView, n int, unit string) string {
	base := representativeSubject(r, anchor, 1)
	if n <= 1 {
		return base
	}
	return subjectPatternText("namedWithMoreUnit", map[string]string{
		"subject": base, "count": strconv.Itoa(n), "unit": unit,
	})
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

// isMeaningfulRepresentativeRelationLabel 排除历史上被当成关系称谓下发的通用占位词
// （registry.presentationText.placeholderRelationLabels）：它们描述的是交集类型而非
// 「这个人是谁」，冠在人名前会变成「共同点赞张三」这种病句。
func isMeaningfulRepresentativeRelationLabel(label string) bool {
	if strings.TrimSpace(label) == "" {
		return false
	}
	return !isPlaceholderRelationLabel(label)
}

// interactionActionPhraseForReason 由逐人证据的实测计数推出互动动词短语。
//
// 只看结构化计数：证据文本本身已由注册表按 kind 渲染，再去里面做子串匹配就是
// 拿自己产出的文案反推事实，且一旦文案改词（或换语言）判定即失效。
func interactionActionPhraseForReason(r IntersectionReasonView) string {
	hasLike := false
	hasComment := false
	hasShare := false
	for _, actor := range r.ActorEvidence {
		if actor.LikeCount > 0 {
			hasLike = true
		}
		if actor.CommentCount > 0 {
			hasComment = true
		}
		if actor.ShareCount > 0 {
			hasShare = true
		}
	}
	parts := make([]string, 0, 3)
	if hasLike {
		parts = append(parts, interactionVerbText("like"))
	}
	if hasComment {
		parts = append(parts, interactionVerbText("comment"))
	}
	if hasShare {
		parts = append(parts, interactionVerbText("share"))
	}
	return joinInteractionVerbs(parts)
}

func actionHintsForReason(r IntersectionReasonView, target *IntersectionTargetView) []IntersectionActionHintView {
	src := strings.TrimSpace(r.Source)
	if anchor, ok := ExplainAnchorPoint(r); ok && strings.TrimSpace(anchor.SourceRef) != "" {
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
		return resolve(v)
	}
	return resolve(generated.IntersectionActionLabelByKey["ask_assistant"])
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

// ExplainAnchorPoint 取结论句锚点：可见点中挖掘强度最高者（§9.8 EvidenceKindRank）。
// HydratePointSummary 已先把 r.IntersectionPoints 收敛为可见点，这里直接择强。
func ExplainAnchorPoint(r IntersectionReasonView) (IntersectionPointView, bool) {
	best := IntersectionPointView{}
	bestRank := 1 << 30
	found := false
	for _, p := range r.IntersectionPoints {
		if p.Visibility == "hidden" {
			continue
		}
		rank := EvidenceKindRank(p.SourceRef, p.PointClass)
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

// ExplainPrimaryText 按 §17.1「主语[代表人+数量+关系限定] + 谓语 + 宾语」实例化事实结论句；
// affinity 走概率通道分支。
//
// 句式模板的真相源是 registry.statementTemplates（codegen generated.IntersectionStatementFormByKind），
// 不再在本函数里逐 kind 硬编码 fmt.Sprintf：文本与 primarySpans 共用同一次渲染，
// 改文案只改注册表并 codegen，且每条模板都带 l10nKey 供端接入译文。
// 未登记 kind 返回空（不造句）。
func ExplainPrimaryText(r IntersectionReasonView, anchor IntersectionPointView) string {
	if r.IntersectionClass == "affinity" {
		return affinityPrimaryText(r, anchor)
	}
	// 纯文本路径不需要可导航 target：对象位仍按模板出文字，可点击性由 spans 路径判定。
	return statementRenderForReason(r, anchor, nil).text
}

// ExplainPrimaryTextL10nKey 返回命中模板的本地化资源键（registry.statementTemplates[].l10nKey）。
// 端接入译文后按同名槽位回填；未命中模板返回空串。
func ExplainPrimaryTextL10nKey(r IntersectionReasonView, anchor IntersectionPointView) string {
	if r.IntersectionClass == "affinity" {
		return ""
	}
	return statementRenderForReason(r, anchor, nil).l10nKey
}

// concreteObjectNameForReason 取可入句的具名对象。通用占位词
// （registry.presentationText.placeholderObjectNames）不算具名：它们描述的是交集
// 类型而非某个对象，入句会产出「都去过『同游』」这种空话。
func concreteObjectNameForReason(r IntersectionReasonView) string {
	name := strings.TrimSpace(r.DisplayName)
	if name == "" || isPlaceholderObjectName(name) {
		return ""
	}
	return name
}

// containerObjectNameForReason 解析「容器/第三方对象位」（圈子/地点/内容/实体）的名字。
// person reason 的 DisplayName 是对方人名，禁止冒充容器对象名（V3 修复：
// 曾产出「…都加入了『<人名>』」错句）；无真实容器名时返回空，由调用方降级为
// 纯计数句或隐藏（§20.4 降级链），不造名。
func containerObjectNameForReason(r IntersectionReasonView) string {
	if strings.TrimSpace(r.ObjectKind) == "person" {
		return ""
	}
	return concreteObjectNameForReason(r)
}

// placeSampleName 取点级样本中的首个地名（多地点时只命名最近一处，其余靠计数下钻）。
func placeSampleName(anchor IntersectionPointView) string {
	name := strings.TrimSpace(anchor.SampleText)
	if idx := strings.IndexAny(name, "、,"); idx > 0 {
		name = strings.TrimSpace(name[:idx])
	}
	return name
}

// sharedOccupationName 取共享职业标签的展示名（identity 事实的谓语补足语）。
// 只读锚点自带的标签样本，不回退人名：人名不是职业。
func sharedOccupationName(anchor IntersectionPointView) string {
	name := strings.TrimSpace(anchor.SampleText)
	if idx := strings.IndexAny(name, "、,"); idx > 0 {
		name = strings.TrimSpace(name[:idx])
	}
	return name
}

func renderedObjectNameForReason(r IntersectionReasonView, kind string) string {
	var name string
	switch kind {
	case "sharedFollowees", "commonFollower", "sameIndustry":
		// 宾语=人本身（被共同关注的人 / 同行的对方），人名合法。
		name = concreteObjectNameForReason(r)
	default:
		// 宾语=圈子/地点/内容/实体等第三方对象，人名不得占位（V3）。
		name = containerObjectNameForReason(r)
	}
	return decorateObjectName(kind, name)
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
		return viewerSelfSubjectText()
	}
	if strings.TrimSpace(r.ActionTargetID) != "" &&
		strings.TrimSpace(r.ActionTargetID) == strings.TrimSpace(r.RelationObjectID) {
		objectType := objectTypeForTarget(
			strings.TrimSpace(r.ObjectKind),
			strings.TrimSpace(r.ActionTargetID),
			RouteIDForObjectKind(strings.TrimSpace(r.ObjectKind)),
		)
		if subject := viewerSubjectText(objectType); subject != "" {
			return subject
		}
	}
	return representativeSubject(r, anchor, n)
}

// affinityPrimaryText 概率通道结论句（必须配 confidenceLabel 标注「推荐」，§17.5/§3.4）。
func affinityPrimaryText(r IntersectionReasonView, anchor IntersectionPointView) string {
	return affinityStatementText(
		affinityChannelForReason(r, anchor),
		renderedObjectNameForReason(r, anchor.SourceRef),
	)
}

// affinityChannelForReason 判定概率通道的投放渠道（圈子 / 关注的人 / 通用）。
func affinityChannelForReason(r IntersectionReasonView, anchor IntersectionPointView) string {
	src := strings.ToLower(r.Source)
	switch {
	case anchor.SourceRef == "sharedCircle" || strings.Contains(src, "circle"):
		return "circle"
	case anchor.SourceRef == "followeeViewing" || strings.Contains(src, "friend") || strings.Contains(src, "follow"):
		return "followee"
	default:
		return "general"
	}
}

// affinityConfidenceLabel 概率通道置信标注（端只对 affinity 展示「推荐」语义）。
func affinityConfidenceLabel(r IntersectionReasonView) string {
	return affinityConfidenceText(r.Dimension)
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
		if item := secondaryTextItem(label, p.Count); item != "" {
			parts = append(parts, item)
		}
		if len(parts) >= 2 {
			break
		}
	}
	return strings.Join(parts, secondaryTextSeparatorText())
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
	return connectionSummaryText(r.TotalPointCount)
}

// Summary 我的主页聚合摘要：各维度计数 + 自上次查看未读数。
