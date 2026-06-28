package intersection

import (
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/content-service/internal/generated"
)

// 交集理由的纯派生/水合辅助（freshness、point/icon/target/text span 推导）
// 自 intersection_service.go 拆出（同 application 包，R03 行数预算，行为不变）。

func (s *IntersectionService) isFresh(r IntersectionReasonView) bool {
	if strings.TrimSpace(r.ExpiresAt) == "" {
		return true
	}
	exp, err := time.Parse(time.RFC3339, r.ExpiresAt)
	if err != nil {
		return true
	}
	return exp.After(s.now())
}

func freshUnix(r IntersectionReasonView) int64 {
	if strings.TrimSpace(r.FreshAt) == "" {
		return 0
	}
	t, err := time.Parse(time.RFC3339, r.FreshAt)
	if err != nil {
		return 0
	}
	return t.Unix()
}

func pointClassForReason(r IntersectionReasonView) string {
	if r.IntersectionClass == "affinity" {
		return "recommended"
	}
	return "fact"
}

func pointLabelForReason(r IntersectionReasonView) string {
	if strings.TrimSpace(r.DisplayName) != "" {
		return r.DisplayName
	}
	if strings.TrimSpace(r.IntersectionID) != "" {
		return r.IntersectionID
	}
	return r.coolKey()
}

func visibleIntersectionPoints(r IntersectionReasonView) []IntersectionPointView {
	points := make([]IntersectionPointView, 0, len(r.IntersectionPoints))
	for _, p := range r.IntersectionPoints {
		if p.Visibility == "hidden" {
			continue
		}
		points = append(points, p)
	}
	if len(points) > 0 {
		return points
	}
	label := pointLabelForReason(r)
	if strings.TrimSpace(label) == "" {
		return nil
	}
	pointID := r.IntersectionID
	if pointID == "" {
		pointID = r.coolKey()
	}
	return []IntersectionPointView{{
		PointID:     pointID,
		PointClass:  pointClassForReason(r),
		Dimension:   r.Dimension,
		DisplayText: label,
		SourceRef:   r.Source,
		Visibility:  "public",
	}}
}

func hydratePointSummary(r IntersectionReasonView) IntersectionReasonView {
	points := visibleIntersectionPoints(r)
	r.IntersectionPoints = points
	byDimension := map[string]*IntersectionDimensionTallyView{}
	order := []string{}
	fact := 0
	recommended := 0
	for _, p := range points {
		switch p.PointClass {
		case "recommended":
			recommended++
		default:
			fact++
		}
		dim := p.Dimension
		if dim == "" {
			dim = r.Dimension
		}
		tally, ok := byDimension[dim]
		if !ok {
			tally = &IntersectionDimensionTallyView{
				Dimension: dim,
				Label:     intersectionDimensionLabels[dim],
			}
			byDimension[dim] = tally
			order = append(order, dim)
		}
		tally.Count++
	}
	summary := make([]IntersectionDimensionTallyView, 0, len(order))
	for _, dim := range order {
		summary = append(summary, *byDimension[dim])
	}
	r.FactPointCount = fact
	r.RecommendedPointCount = recommended
	r.TotalPointCount = fact + recommended
	r.DimensionPointSummary = summary
	if r.PointSummarySnapshotID == "" {
		// 漂移收口 §20：交集快照/追踪 id 单通道 = pointSummarySnapshotId，
		// 缺省回落 intersectionId（不再有 recommendationTraceId 第二通道）。
		r.PointSummarySnapshotID = r.IntersectionID
	}
	if r.PointClassLabel == "" {
		if recommended > 0 && fact == 0 {
			r.PointClassLabel = "推荐交集"
		} else {
			r.PointClassLabel = "事实交集"
		}
	}
	if r.RankState == "" {
		r.RankState = "fresh"
	}
	return hydrateExplain(r)
}

// hydrateExplain 是云侧交集 Explain 管线（§17.1 主谓宾模板 + §5.4 kind 注册表 + 实例样本）：
// 由结构化证据点（kind + count + 维度 + 关系态）实例化 primaryText / secondaryText /
// connectionSummary；affinity 分通道补 confidenceLabel / modelReasonBucket；并按
// strength + intersectionClass 离散化 weightTier。
//
// G2：primaryText 唯一产出归属在此，禁止回退旧 displayText/label 作结论句来源；已预置
// primaryText（如未来读模型预物化）则尊重不覆盖。kind 未登记且无预置 primaryText 时按
// §18.1「无 primaryText → 不展示」留空，由候选窗完备性过滤优雅降级（不写死闭集、不造假）。
func hydrateExplain(r IntersectionReasonView) IntersectionReasonView {
	anchor, hasAnchor := explainAnchorPoint(r)
	// §23 一等字段：reason.kind 真相源为锚点的 sourceRef（已登记 kind），缺省回落 reason.source；
	// vertical 缺省 general（旅行等垂类落数据后由注册表 vertical 驱动，本轮全为 general）。
	if strings.TrimSpace(r.Kind) == "" {
		if hasAnchor && strings.TrimSpace(anchor.SourceRef) != "" {
			r.Kind = strings.TrimSpace(anchor.SourceRef)
		} else {
			r.Kind = strings.TrimSpace(r.Source)
		}
	}
	if strings.TrimSpace(r.Vertical) == "" {
		// §23.4 三元组正交：vertical 不来自 kind（基 kind 一律 general），
		// 由 objectKind / tagRef 真算（route/photo_spot/gear 或旅行 tag → travel_photography）。
		r.Vertical = verticalForReason(r)
	}
	if strings.TrimSpace(r.LifecycleState) == "" {
		// §21.3 状态机真算：仅在有强度变化信号（previousStrength/strengthDelta/edgeWeight）时
		// 离散化生命周期态；无信号不造假（留空，端按 freshAt/new 红点兜底）。
		r.LifecycleState = lifecycleStateForReason(r)
	}
	if r.RepresentativeActor == nil && hasAnchor {
		r.RepresentativeActor = representativeActorForReason(r, anchor)
	}
	if strings.TrimSpace(r.PrimaryText) == "" && hasAnchor {
		r.PrimaryText = explainPrimaryText(r, anchor)
	}
	if strings.TrimSpace(r.SecondaryText) == "" {
		r.SecondaryText = explainSecondaryText(r, anchor)
	}
	if strings.TrimSpace(r.ConnectionSummary) == "" {
		r.ConnectionSummary = explainConnectionSummary(r)
	}
	if r.IntersectionClass == "affinity" {
		if strings.TrimSpace(r.ConfidenceLabel) == "" {
			r.ConfidenceLabel = affinityConfidenceLabel(r)
		}
		if strings.TrimSpace(r.ModelReasonBucket) == "" {
			r.ModelReasonBucket = affinityModelReasonBucket(r)
		}
	}
	if strings.TrimSpace(r.WeightTier) == "" {
		if r.IntersectionClass == "fact" && r.Strength >= 0.8 {
			r.WeightTier = "heavy"
		} else {
			r.WeightTier = "light"
		}
	}
	if strings.TrimSpace(r.IconKey) == "" {
		r.IconKey = iconKeyForReason(r)
	}
	r = hydrateInteractionContract(r)
	if r.ObjectVisual == nil {
		r.ObjectVisual = objectVisualForReason(r)
	}
	return r
}

// iconKeyForReason 产出端侧类型图标语义键（§21.5.2 闭集）。真相源 =
// recommendation/rec_model/intersection_kind_registry.yaml（codegen generated.Intersection* 查表）。
// anchor.SourceRef 命中 kind 即用其 iconKey；未登记 kind 按 dimension 末级回退表降级，
// 端 IntersectionIconResolver 再做最终回退。
func iconKeyForReason(r IntersectionReasonView) string {
	src := ""
	if anchor, ok := explainAnchorPoint(r); ok {
		src = anchor.SourceRef
	}
	if strings.TrimSpace(src) == "" {
		src = r.Source
	}
	if key := iconKeyForKind(src); key != "" {
		return key
	}
	return generated.IntersectionIconKeyByDimension[strings.TrimSpace(r.Dimension)]
}

// iconKeyForKind 查 kind → iconKey（generated.IntersectionIconKeyByKind，源 registry.kinds[].iconKey）。
// 未登记 kind 返回空串，由 iconKeyForReason 走 dimension 末级回退。
func iconKeyForKind(kind string) string {
	return generated.IntersectionIconKeyByKind[strings.TrimSpace(kind)]
}

// objectVisualForReason 产出尾部对象视觉（§21.5.1 槽③）：该 reason 指向的主对象封面 /
// 校徽 / 头像。无可解析 target 时返回 nil，端回退 chevron 占位。
func objectVisualForReason(r IntersectionReasonView) *IntersectionVisualView {
	target := intersectionTargetForReason(r)
	if target == nil {
		return nil
	}
	return &IntersectionVisualView{
		AssetKind:   assetKindForObjectKind(r.ObjectKind),
		ImageURL:    r.AvatarURL,
		DisplayName: r.DisplayName,
		Target:      target,
	}
}

func hydrateInteractionContract(r IntersectionReasonView) IntersectionReasonView {
	target := intersectionTargetForReason(r)
	if len(r.SampleVisuals) == 0 && target != nil {
		r.SampleVisuals = []IntersectionVisualView{{
			AssetKind:   assetKindForObjectKind(r.ObjectKind),
			ImageURL:    r.AvatarURL,
			DisplayName: r.DisplayName,
			Target:      target,
		}}
	}
	for i := range r.IntersectionPoints {
		if len(r.IntersectionPoints[i].SampleVisuals) == 0 && len(r.SampleVisuals) > 0 {
			r.IntersectionPoints[i].SampleVisuals = r.SampleVisuals
		}
	}
	if len(r.PrimarySpans) == 0 && strings.TrimSpace(r.PrimaryText) != "" {
		r.PrimarySpans = primarySpansForReason(r, target)
	}
	if len(r.ActionHints) == 0 {
		r.ActionHints = actionHintsForReason(r, target)
	}
	return r
}

func intersectionTargetForReason(r IntersectionReasonView) *IntersectionTargetView {
	id := strings.TrimSpace(r.ActionTargetID)
	if id == "" {
		id = strings.TrimSpace(r.RelationObjectID)
	}
	if id == "" {
		return nil
	}
	kind := strings.TrimSpace(r.ObjectKind)
	if kind == "" {
		kind = "person"
	}
	return &IntersectionTargetView{
		ObjectID:   id,
		ObjectKind: kind,
		RouteID:    routeIDForObjectKind(kind),
	}
}

func routeIDForObjectKind(kind string) string {
	// 真相源 = intersection_kind_registry.yaml objectKinds[].routeId
	// （codegen generated.IntersectionRouteIDByObjectKind；端 intersectionRouteIdForObjectKind 同表）。
	// 不可导航对象（content/tag）或未知值返回空串（map 零值）。
	return generated.IntersectionRouteIDByObjectKind[strings.TrimSpace(kind)]
}

func assetKindForObjectKind(kind string) string {
	// 真相源 = intersection_kind_registry.yaml objectKinds[].assetKind
	// （codegen generated.IntersectionAssetKindByObjectKind；端 UnifiedObjectKind.assetKind 同表）。
	// 未声明 assetKind 的对象（content/tag）或未知值兜底 icon。
	if v, ok := generated.IntersectionAssetKindByObjectKind[strings.TrimSpace(kind)]; ok {
		return v
	}
	return "icon"
}

// verticalForReason 三元组正交（§23.4）真算 reason 垂类：route/photo_spot/gear 主对象
// 必属旅行摄影垂类；place 主对象或旅行 tag（travel/photo/sunset/landscape/hiking 等命名空间）
// 命中亦归 travel_photography；其余 general。kind 不参与（基 kind 一律 general）。
func verticalForReason(r IntersectionReasonView) string {
	switch strings.TrimSpace(r.ObjectKind) {
	case "route", "photo_spot", "gear":
		return "travel_photography"
	}
	for _, tag := range r.TagRefs {
		if isTravelPhotographyTag(tag) {
			return "travel_photography"
		}
	}
	return "general"
}

func isTravelPhotographyTag(tag string) bool {
	t := strings.ToLower(strings.TrimSpace(tag))
	if t == "" {
		return false
	}
	for _, marker := range []string{"travel", "photo", "sunset", "landscape", "hiking", "scenic", "route", "spot"} {
		if strings.Contains(t, marker) {
			return true
		}
	}
	return false
}

// lifecycleStateForReason 按 §21.3 状态机离散化交集边生命周期态。只在有强度变化信号时
// 真算（previousStrength/strengthDelta/edgeWeight 任一非零）；无信号返回空，不造假。
// reactivated = 低位（previousStrength≤0.5）回升；strengthened = 健康基线上升；weakened = 衰减。
func lifecycleStateForReason(r IntersectionReasonView) string {
	if r.PreviousStrength <= 0 && r.StrengthDelta == 0 && r.EdgeWeight == 0 {
		return ""
	}
	delta := r.StrengthDelta
	if delta == 0 && r.PreviousStrength > 0 {
		delta = r.Strength - r.PreviousStrength
	}
	switch {
	case r.PreviousStrength <= 0 && r.Strength > 0:
		return "new"
	case delta <= -0.05:
		return "weakened"
	case delta >= 0.05 && r.PreviousStrength > 0 && r.PreviousStrength <= 0.5:
		return "reactivated"
	case delta >= 0.05:
		return "strengthened"
	default:
		return "stable"
	}
}

func primarySpansForReason(r IntersectionReasonView, target *IntersectionTargetView) []IntersectionTextSpanView {
	text := strings.TrimSpace(r.PrimaryText)
	if text == "" {
		return nil
	}
	name := strings.TrimSpace(r.DisplayName)
	if target == nil || name == "" || !strings.Contains(text, name) {
		return []IntersectionTextSpanView{{Text: text, Role: "plain"}}
	}
	parts := strings.SplitN(text, name, 2)
	spans := make([]IntersectionTextSpanView, 0, 3)
	if parts[0] != "" {
		spans = append(spans, IntersectionTextSpanView{Text: parts[0], Role: "plain"})
	}
	spans = append(spans, IntersectionTextSpanView{
		Text:   name,
		Role:   "object",
		Target: target,
	})
	if len(parts) > 1 && parts[1] != "" {
		spans = append(spans, IntersectionTextSpanView{Text: parts[1], Role: "plain"})
	}
	return spans
}

func representativeActorForReason(r IntersectionReasonView, anchor IntersectionPointView) *IntersectionRepresentativeActorView {
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

func representativeActorName(r IntersectionReasonView, anchor IntersectionPointView) string {
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
		return "共同联系人"
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
	if name == "" {
		name = "一位用户"
	}
	if n <= 1 {
		return name
	}
	return fmt.Sprintf("%s等%d人", name, n)
}

func representativeSubjectWithUnit(r IntersectionReasonView, anchor IntersectionPointView, n int, unit string) string {
	name := representativeActorName(r, anchor)
	if name == "" {
		name = "一位用户"
	}
	if n <= 1 {
		return name
	}
	return fmt.Sprintf("%s等%d%s", name, n, unit)
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
			ActionKey: key,
			Label:     actionLabelForKey(key),
			Target:    target,
			IsPrimary: i == 0,
			Priority:  i + 1,
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
		return fmt.Sprintf("你和%s共同关注了相同的人", representativeSubject(r, anchor, n))
	case "commonContact":
		return fmt.Sprintf("你和%s有共同联系人", representativeSubject(r, anchor, n))
	case "sharedCircle", "coMemberCircle":
		return fmt.Sprintf("你和%s共同加入了圈子", representativeSubject(r, anchor, n))
	case "coCommented", "sharedDiscussion":
		return fmt.Sprintf("你和%s都讨论过相同内容", representativeSubject(r, anchor, n))
	case "coSharedContent":
		return fmt.Sprintf("你和%s都分享过相同内容", representativeSubject(r, anchor, n))
	case "coCreatedContent":
		return fmt.Sprintf("你和%s都创作过相关内容", representativeSubject(r, anchor, n))
	case "coVisitedEntity":
		return fmt.Sprintf("你和%s都去过相同的地方", representativeSubject(r, anchor, n))
	case "coWishlistedEntity":
		return fmt.Sprintf("你和%s都想去相同的地方", representativeSubject(r, anchor, n))
	case "sharedEntityAttention":
		return fmt.Sprintf("你和%s共同关注了这里", representativeSubject(r, anchor, n))
	case "followeeVisited":
		return fmt.Sprintf("%s来过这里", representativeSubjectWithUnit(r, anchor, n, "位你关注的人"))
	case "followeeInObject":
		return fmt.Sprintf("%s在这里", representativeSubjectWithUnit(r, anchor, n, "位你关注的人"))
	case "followeeViewing":
		return fmt.Sprintf("%s最近看过这些内容", representativeSubjectWithUnit(r, anchor, n, "位你关注的人"))
	case "followeeDiscussedThis":
		return fmt.Sprintf("%s也在讨论这些主题", representativeSubjectWithUnit(r, anchor, n, "位你关注的人"))
	case "sharedTagSample":
		if r.Source == "circleTag" {
			return fmt.Sprintf("%s在圈子里常看这些主题", representativeSubject(r, anchor, n))
		}
		return fmt.Sprintf("你和%s都关注这些主题", representativeSubject(r, anchor, n))
	default:
		return ""
	}
}

// affinityPrimaryText 概率通道结论句（必须配 confidenceLabel 标注「推荐」，§17.5/§3.4）。
func affinityPrimaryText(r IntersectionReasonView, anchor IntersectionPointView) string {
	src := strings.ToLower(r.Source)
	switch {
	case anchor.SourceRef == "sharedCircle" || strings.Contains(src, "circle"):
		return "你的圈子里最近在看这些"
	case anchor.SourceRef == "followeeViewing" || strings.Contains(src, "friend") || strings.Contains(src, "follow"):
		return "你关注的人最近在看这些"
	default:
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
