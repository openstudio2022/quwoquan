package intersection

import (
	"regexp"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/services/content-service/internal/generated"
)

var rawInteractionStatsPattern = regexp.MustCompile(`[0-9０-９]+\s*(赞|评|转|转发)`)

const (
	DisplayBindingExplicitLink     = "explicit_link"
	DisplayBindingHostImplicit     = "host_implicit"
	DisplayBindingHostPlain        = "host_plain"
	DisplayBindingHidden           = "hidden"
	DisplaySurfaceFeed             = "homeFeed"
	DisplaySurfaceWorkBrowser      = "workBrowser"
	DisplaySurfaceSearchResult     = "searchResult"
	DisplaySurfaceObjectPage       = "objectPage"
	DisplaySurfaceIntersectionList = "intersectionList"
)

// DisplayContext 是 Query Reader/Slice 输出口的展示绑定上下文。canonical reason
// 仍只表达 evidence 与 target；只有输出到具体 surface 时，才决定宾语是显式链接还是宿主上下文。
type DisplayContext struct {
	Surface    string
	HostTarget *IntersectionTargetView
	Binding    string
}

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
	r = hydrateActorEvidenceContract(r)
	if r.RepresentativeActor == nil && hasAnchor {
		r.RepresentativeActor = representativeActorForReason(r, anchor)
	}
	if hasAnchor {
		computed := explainPrimaryText(r, anchor)
		if strings.TrimSpace(r.PrimaryText) == "" ||
			!displayStatementTextAllowed(r, r.PrimaryText) {
			r.PrimaryText = computed
			r.PrimarySpans = nil
		}
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
	if !ValidateDisplayStatement(r) {
		r = hideDisplayStatement(r)
	}
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
	r.DisplayBinding = normalizedDisplayBinding(r.DisplayBinding)
	return r
}

func hydrateActorEvidenceContract(r IntersectionReasonView) IntersectionReasonView {
	if len(r.ActorEvidence) > 0 && r.ActorEvidenceTotalCount == 0 {
		r.ActorEvidenceTotalCount = len(r.ActorEvidence)
	}
	if strings.TrimSpace(r.ActorEvidenceCompleteness) == "" {
		if len(r.ActorEvidence) > 0 && r.ActorEvidenceTotalCount == len(r.ActorEvidence) {
			r.ActorEvidenceCompleteness = "complete"
		} else {
			r.ActorEvidenceCompleteness = "unknown"
		}
	}
	for i := range r.ActorEvidence {
		e := &r.ActorEvidence[i]
		if strings.TrimSpace(e.PrivacyState) == "" {
			e.PrivacyState = "visible"
		}
		if e.SortKey == 0 {
			e.SortKey = i + 1
		}
		if strings.TrimSpace(e.SnapshotVersion) == "" {
			e.SnapshotVersion = r.PointSummarySnapshotID
		}
		if e.EvidenceRank == 0 && strings.TrimSpace(e.SourceRef) != "" {
			e.EvidenceRank = evidenceKindRank(e.SourceRef, "fact")
		}
		if e.Target == nil && strings.TrimSpace(e.ActorID) != "" {
			routeID := routeIDForObjectKind("person")
			e.Target = &IntersectionTargetView{
				ObjectType: objectTypeForTarget("person", strings.TrimSpace(e.ActorID), routeID),
				ObjectID:   strings.TrimSpace(e.ActorID),
				ObjectKind: "person",
				RouteID:    routeID,
			}
		}
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
	routeID := routeIDForObjectKind(kind)
	return &IntersectionTargetView{
		ObjectType: objectTypeForTarget(kind, id, routeID),
		ObjectID:   id,
		ObjectKind: kind,
		RouteID:    routeID,
	}
}

func routeIDForObjectKind(kind string) string {
	// 真相源 = intersection_kind_registry.yaml objectKinds[].routeId
	// （codegen generated.IntersectionRouteIDByObjectKind；端 intersectionRouteIdForObjectKind 同表）。
	// 不可导航对象（content/tag）或未知值返回空串（map 零值）。
	return generated.IntersectionRouteIDByObjectKind[strings.TrimSpace(kind)]
}

func objectTypeForTarget(kind, objectID, routeID string) string {
	switch strings.TrimSpace(routeID) {
	case "userProfile":
		return "user"
	case "circleDetail":
		return "circle"
	case "homepageDetail":
		return "homepage"
	case "workBrowser", "postDetail", "contentDetail":
		return "post"
	case "myIntersections":
		return "dimension"
	}
	switch strings.TrimSpace(kind) {
	case "person":
		return "user"
	case "circle":
		return "circle"
	case "school", "place", "enterprise", "route", "photo_spot", "gear":
		return "homepage"
	case "content":
		return "post"
	case "tag":
		return "tag"
	}
	id := strings.TrimSpace(objectID)
	switch {
	case strings.HasPrefix(id, "homepage_"):
		return "homepage"
	case strings.HasPrefix(id, "fixture_circle_"), strings.HasPrefix(id, "circle_"):
		return "circle"
	}
	return ""
}

func hostTargetForObjectRequest(objectID, objectType string) *IntersectionTargetView {
	id := strings.TrimSpace(objectID)
	if id == "" {
		return nil
	}
	objectType = strings.TrimSpace(objectType)
	switch objectType {
	case "user", "person":
		return &IntersectionTargetView{ObjectType: "user", ObjectID: id, ObjectKind: "person", RouteID: routeIDForObjectKind("person")}
	case "circle":
		return &IntersectionTargetView{ObjectType: "circle", ObjectID: id, ObjectKind: "circle", RouteID: routeIDForObjectKind("circle")}
	case "homepage", "entity":
		return &IntersectionTargetView{ObjectType: "homepage", ObjectID: id, ObjectKind: "place", RouteID: routeIDForObjectKind("place")}
	case "post", "content":
		return &IntersectionTargetView{ObjectType: "post", ObjectID: id, ObjectKind: "content", RouteID: routeIDForObjectKind("content")}
	default:
		return nil
	}
}

// hostTargetForObjectReasons resolves open request objectType values through the
// source-owned closed ObjectKind contract. This avoids maintaining a second,
// inevitably incomplete objectType switch in the application read path.
func hostTargetForObjectReasons(
	objectID string,
	objectType string,
	reasons []IntersectionReasonView,
) *IntersectionTargetView {
	if target := hostTargetForObjectRequest(objectID, objectType); target != nil {
		return target
	}
	id := strings.TrimSpace(objectID)
	for _, reason := range reasons {
		target := intersectionTargetForReason(reason)
		if target != nil && strings.TrimSpace(target.ObjectID) == id {
			return target
		}
	}
	return nil
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
	anchor, ok := explainAnchorPoint(r)
	if !ok || target == nil {
		return []IntersectionTextSpanView{{Text: text, Role: "plain"}}
	}
	spans := primaryStatementSpansForReason(r, anchor, target)
	if len(spans) > 0 && joinedSpanText(spans) == text {
		return spans
	}
	return []IntersectionTextSpanView{{Text: text, Role: "plain"}}
}

// ApplyDisplayContext 把 canonical explicit reason 投影成具体 Query Slice 的上下文表达。
// 它只消费结构化 span/target，不按字符串猜当前对象。
func ApplyDisplayContext(r IntersectionReasonView, ctx DisplayContext) IntersectionReasonView {
	binding := normalizedDisplayBinding(ctx.Binding)
	if binding == DisplayBindingExplicitLink && ctx.HostTarget != nil && sameIntersectionTarget(intersectionTargetForReason(r), ctx.HostTarget) {
		binding = DisplayBindingHostImplicit
	}
	if binding == DisplayBindingHidden {
		return hideDisplayStatement(r)
	}
	r.DisplayBinding = binding
	switch binding {
	case DisplayBindingHostImplicit:
		r = removeHostObjectSpan(r, ctx.HostTarget)
	case DisplayBindingHostPlain:
		r = plainHostObjectSpan(r, ctx.HostTarget)
	default:
		r.DisplayBinding = DisplayBindingExplicitLink
	}
	if !ValidateDisplayStatementWithContext(r, ctx) {
		return hideDisplayStatement(r)
	}
	return r
}

// ValidateDisplayStatement 是交集 v3 展示合同闸：默认严格按 explicit_link 校验，
// 只有 Reader/Slice 输出口显式传 DisplayContext 时才允许 host_implicit/host_plain。
func ValidateDisplayStatement(r IntersectionReasonView) bool {
	return ValidateDisplayStatementWithContext(r, DisplayContext{})
}

func ValidateDisplayStatementWithContext(r IntersectionReasonView, ctx DisplayContext) bool {
	if !displayStatementTextAllowed(r, r.PrimaryText) {
		return false
	}
	if len(r.PrimarySpans) == 0 {
		return false
	}
	if joinedSpanText(r.PrimarySpans) != strings.TrimSpace(r.PrimaryText) {
		return false
	}
	binding := normalizedDisplayBinding(r.DisplayBinding)
	if binding == DisplayBindingHidden {
		return false
	}
	reasonTarget := intersectionTargetForReason(r)
	if reasonTarget == nil || !displayObjectTargetAllowed(reasonTarget) {
		return false
	}
	hasReasonObjectTarget := false
	for _, span := range r.PrimarySpans {
		switch strings.TrimSpace(span.Role) {
		case "count":
			if span.Target != nil &&
				(strings.TrimSpace(r.ActorEvidenceCompleteness) != "complete" ||
					span.Target.RouteID != "myIntersections") {
				return false
			}
		case "object":
			if span.Target == nil || !displayObjectTargetAllowed(span.Target) {
				return false
			}
			if sameIntersectionTarget(span.Target, reasonTarget) {
				hasReasonObjectTarget = true
			}
		}
	}
	switch binding {
	case DisplayBindingExplicitLink:
		if ctx.HostTarget != nil && sameIntersectionTarget(reasonTarget, ctx.HostTarget) {
			return false
		}
		return hasReasonObjectTarget
	case DisplayBindingHostImplicit, DisplayBindingHostPlain:
		if ctx.HostTarget == nil || !sameIntersectionTarget(reasonTarget, ctx.HostTarget) {
			return false
		}
		return !hasReasonObjectTarget
	default:
		return false
	}
}

func displayStatementTextAllowed(r IntersectionReasonView, text string) bool {
	primary := strings.TrimSpace(text)
	if primary == "" {
		return false
	}
	if rawInteractionStatsPattern.MatchString(primary) {
		return false
	}
	for _, banned := range []string{
		"共同好友",
		"都来这里互动过",
		"在这里互动过",
		"同读者",
		"相近主题",
		"TA的内容",
		"相关圈子",
		"我的连接",
		"我的影响力",
		"这条记录",
		"这篇内容",
		"当前内容",
		"你和这里",
		"你和这个圈子",
		"你们有共同",
	} {
		if strings.Contains(primary, banned) {
			return false
		}
	}
	target := intersectionTargetForReason(r)
	if target == nil || !displayObjectTargetAllowed(target) {
		return false
	}
	if displayStatementNeedsRepresentative(r, primary) && !hasMeaningfulRepresentativeActor(r) {
		return false
	}
	return true
}

func normalizedDisplayBinding(value string) string {
	switch strings.TrimSpace(value) {
	case DisplayBindingHostImplicit:
		return DisplayBindingHostImplicit
	case DisplayBindingHostPlain:
		return DisplayBindingHostPlain
	case DisplayBindingHidden:
		return DisplayBindingHidden
	default:
		return DisplayBindingExplicitLink
	}
}

func hideDisplayStatement(r IntersectionReasonView) IntersectionReasonView {
	r.DisplayBinding = DisplayBindingHidden
	r.PrimaryText = ""
	r.PrimarySpans = nil
	r.ActionHints = nil
	return r
}

func sameIntersectionTarget(a, b *IntersectionTargetView) bool {
	if a == nil || b == nil {
		return false
	}
	if strings.TrimSpace(a.ObjectID) == "" || strings.TrimSpace(b.ObjectID) == "" {
		return false
	}
	return strings.TrimSpace(a.ObjectID) == strings.TrimSpace(b.ObjectID) &&
		strings.TrimSpace(a.ObjectType) == strings.TrimSpace(b.ObjectType)
}

func removeHostObjectSpan(r IntersectionReasonView, host *IntersectionTargetView) IntersectionReasonView {
	reasonTarget := intersectionTargetForReason(r)
	if host == nil || !sameIntersectionTarget(reasonTarget, host) {
		return r
	}
	out := make([]IntersectionTextSpanView, 0, len(r.PrimarySpans))
	removed := false
	for _, span := range r.PrimarySpans {
		if strings.TrimSpace(span.Role) == "object" && sameIntersectionTarget(span.Target, host) {
			removed = true
			continue
		}
		out = append(out, span)
	}
	if removed {
		r.PrimarySpans = out
		r.PrimaryText = strings.TrimSpace(joinedSpanText(out))
	}
	return r
}

func plainHostObjectSpan(r IntersectionReasonView, host *IntersectionTargetView) IntersectionReasonView {
	reasonTarget := intersectionTargetForReason(r)
	if host == nil || !sameIntersectionTarget(reasonTarget, host) {
		return r
	}
	out := make([]IntersectionTextSpanView, 0, len(r.PrimarySpans))
	for _, span := range r.PrimarySpans {
		if strings.TrimSpace(span.Role) == "object" && sameIntersectionTarget(span.Target, host) {
			span.Role = "plain"
			span.Target = nil
		}
		out = append(out, span)
	}
	r.PrimarySpans = out
	return r
}

func displayObjectTargetAllowed(target *IntersectionTargetView) bool {
	if target == nil || strings.TrimSpace(target.ObjectID) == "" {
		return false
	}
	switch strings.TrimSpace(target.ObjectType) {
	case "user", "circle", "homepage", "post", "task":
		return true
	default:
		return false
	}
}

func displayStatementNeedsRepresentative(r IntersectionReasonView, text string) bool {
	if r.ActorEvidenceTotalCount > 1 || len(r.ActorEvidence) > 1 {
		return true
	}
	if strings.Contains(text, "等") {
		return true
	}
	return regexp.MustCompile(`[0-9０-９]+\s*(人|位)`).MatchString(text)
}

func hasMeaningfulRepresentativeActor(r IntersectionReasonView) bool {
	actor := r.RepresentativeActor
	if actor == nil {
		return false
	}
	if strings.TrimSpace(actor.DisplayName) == "" {
		return false
	}
	name := strings.TrimSpace(actor.DisplayName)
	if strings.HasPrefix(name, "一位") || name == "用户" {
		return false
	}
	if !isMeaningfulRepresentativeRelationLabel(actor.RelationLabel) {
		return false
	}
	if actor.Target == nil || strings.TrimSpace(actor.Target.ObjectType) != "user" {
		return false
	}
	return true
}

func joinedSpanText(spans []IntersectionTextSpanView) string {
	var b strings.Builder
	for _, span := range spans {
		b.WriteString(span.Text)
	}
	return b.String()
}

func primaryStatementSpansForReason(
	r IntersectionReasonView,
	anchor IntersectionPointView,
	target *IntersectionTargetView,
) []IntersectionTextSpanView {
	if r.IntersectionClass == "affinity" {
		return affinityPrimaryStatementSpansForReason(r, anchor, target)
	}
	objectName := renderedObjectNameForReason(r, anchor.SourceRef)
	if anchor.SourceRef == "commonContact" {
		objectName = concreteObjectNameForReason(r)
	}
	if objectName == "" || target == nil {
		return nil
	}
	subject := representativeSubjectSpans(r, anchor)
	if len(subject) == 0 {
		return nil
	}
	object := IntersectionTextSpanView{Text: objectName, Role: "object", Target: target}
	switch anchor.SourceRef {
	case "sharedFollowees", "commonFollower", "sharedEntityAttention":
		return append(append(subject, plainSpan("也关注了")), object)
	case "commonContact":
		return append(append(append(subject, plainSpan("都是你和")), object), plainSpan("的共同联系人"))
	case "sharedCircle", "coMemberCircle":
		return append(append(subject, plainSpan("都加入了")), object)
	case "coCommented", "sharedDiscussion":
		action := interactionActionPhraseForReason(r)
		if action == "" {
			action = "都讨论过"
		}
		return append(append(subject, plainSpan(action)), object)
	case "coSharedContent":
		action := interactionActionPhraseForReason(r)
		if action == "" {
			action = "都转发过"
		}
		return append(append(subject, plainSpan(action)), object)
	case "coCreatedContent":
		return append(append(subject, plainSpan("都共创过")), object)
	case "coVisitedEntity":
		return append(append(subject, plainSpan("都去过")), object)
	case "coWishlistedEntity":
		return append(append(subject, plainSpan("都想去")), object)
	case "followeeVisited":
		countedSubject := countedRepresentativeSubject(r, anchor, anchorAggregateCount(r, anchor))
		countedSpans := splitCountSpan(
			countedSubject,
			anchorAggregateCount(r, anchor),
			countTargetForReason(r, anchor),
		)
		return append(append(countedSpans, plainSpan("来过")), object)
	case "followeeInObject":
		return append(append(subject, plainSpan("在")), object)
	case "followeeViewing":
		return append(append(subject, plainSpan("正在看")), object)
	case "followeeDiscussedThis":
		return append(append(subject, plainSpan("正在讨论")), object)
	default:
		return nil
	}
}

func affinityPrimaryStatementSpansForReason(
	r IntersectionReasonView,
	anchor IntersectionPointView,
	target *IntersectionTargetView,
) []IntersectionTextSpanView {
	objectName := renderedObjectNameForReason(r, anchor.SourceRef)
	text := strings.TrimSpace(r.PrimaryText)
	if objectName == "" || text == "" || target == nil {
		return nil
	}
	idx := strings.Index(text, objectName)
	if idx < 0 {
		return nil
	}
	spans := make([]IntersectionTextSpanView, 0, 3)
	if idx > 0 {
		spans = append(spans, plainSpan(text[:idx]))
	}
	spans = append(spans, IntersectionTextSpanView{Text: objectName, Role: "object", Target: target})
	if tail := text[idx+len(objectName):]; tail != "" {
		spans = append(spans, plainSpan(tail))
	}
	return spans
}

func representativeSubjectSpans(
	r IntersectionReasonView,
	anchor IntersectionPointView,
) []IntersectionTextSpanView {
	n := anchorAggregateCount(r, anchor)
	subject := representativeSubject(r, anchor, n)
	if strings.TrimSpace(subject) == "" {
		return nil
	}
	actor := r.RepresentativeActor
	if actor == nil || actor.Target == nil ||
		strings.TrimSpace(actor.Target.ObjectType) != "user" ||
		strings.TrimSpace(actor.DisplayName) == "" ||
		!strings.Contains(subject, strings.TrimSpace(actor.DisplayName)) {
		return splitCountSpan(subject, n, countTargetForReason(r, anchor))
	}
	name := strings.TrimSpace(actor.DisplayName)
	parts := strings.SplitN(subject, name, 2)
	spans := make([]IntersectionTextSpanView, 0, 5)
	if parts[0] != "" {
		spans = append(spans, plainSpan(parts[0]))
	}
	spans = append(spans, IntersectionTextSpanView{
		Text:   name,
		Role:   "object",
		Target: actor.Target,
	})
	if len(parts) > 1 && parts[1] != "" {
		spans = append(spans, splitCountSpan(parts[1], n, countTargetForReason(r, anchor))...)
	}
	return spans
}

func splitCountSpan(text string, n int, target *IntersectionTargetView) []IntersectionTextSpanView {
	if n <= 1 || target == nil {
		return []IntersectionTextSpanView{plainSpan(text)}
	}
	value := strconv.Itoa(n)
	idx := strings.Index(text, value)
	if idx < 0 {
		return []IntersectionTextSpanView{plainSpan(text)}
	}
	out := make([]IntersectionTextSpanView, 0, 3)
	if idx > 0 {
		out = append(out, plainSpan(text[:idx]))
	}
	out = append(out, IntersectionTextSpanView{Text: value, Role: "count", Target: target})
	if tail := text[idx+len(value):]; tail != "" {
		out = append(out, plainSpan(tail))
	}
	return out
}

func countTargetForReason(r IntersectionReasonView, anchor IntersectionPointView) *IntersectionTargetView {
	if strings.TrimSpace(r.ActorEvidenceCompleteness) != "complete" {
		return nil
	}
	id := firstNonEmpty(r.Dimension, anchor.SourceRef)
	if id == "" {
		return nil
	}
	return &IntersectionTargetView{
		ObjectType: "dimension",
		ObjectID:   id,
		ObjectKind: "dimension",
		RouteID:    "myIntersections",
	}
}

func plainSpan(text string) IntersectionTextSpanView {
	return IntersectionTextSpanView{Text: text, Role: "plain"}
}
