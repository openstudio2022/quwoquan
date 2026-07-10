package intersection

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/services/content-service/internal/generated"
)

var rawInteractionStatsPattern = regexp.MustCompile(`[0-9０-９]+\s*(赞|评|转|转发)`)

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
		r.PrimaryText = ""
		r.PrimarySpans = nil
		r.ActionHints = nil
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

// ValidateDisplayStatement 是交集 v3 展示合同闸：服务端只允许完整 SVO 且可导航的实例
// 进入 App 展示层。App 仍会 fail-closed 复核，但不再替云侧补主句。
func ValidateDisplayStatement(r IntersectionReasonView) bool {
	if !displayStatementTextAllowed(r, r.PrimaryText) {
		return false
	}
	if len(r.PrimarySpans) == 0 {
		return false
	}
	if joinedSpanText(r.PrimarySpans) != strings.TrimSpace(r.PrimaryText) {
		return false
	}
	hasObjectTarget := false
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
			hasObjectTarget = true
		}
	}
	return hasObjectTarget
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
		return append(append(subject, plainSpan("来过")), object)
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

func hasMachineRepresentativeName(r IntersectionReasonView, anchor IntersectionPointView) bool {
	name := strings.TrimSpace(representativeActorName(r, anchor))
	switch {
	case name == "":
		return false
	case strings.Contains(name, "_"):
		return true
	case strings.HasPrefix(name, "fixture_"):
		return true
	case strings.HasPrefix(name, "ixsrc_"):
		return true
	default:
		return false
	}
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
		subject := representativeSubject(r, anchor, n)
		if hasMachineRepresentativeName(r, anchor) {
			subject = countedRepresentativeSubject(r, anchor, n)
		}
		return fmt.Sprintf("%s来过%s", subject, objectName)
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
