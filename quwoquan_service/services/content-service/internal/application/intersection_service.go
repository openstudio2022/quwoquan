package application

import (
	"context"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

// IntersectionReasonView 是交集理由的服务端视图，与 recommendation/rec_model
// projections/intersection_reason.yaml 字段对齐（端只读、不本地拼装）。
type IntersectionReasonView struct {
	IntersectionID         string                           `json:"intersectionId"`
	IntersectionClass      string                           `json:"intersectionClass"` // fact | affinity
	Dimension              string                           `json:"dimension"`
	DisplayName            string                           `json:"displayName"`
	AvatarURL              string                           `json:"avatarUrl"`
	Label                  string                           `json:"label"`
	DisplayText            string                           `json:"displayText"`
	PrimaryText            string                           `json:"primaryText"`   // 主交集结论句（蓝色，云侧产出，端只读直出）
	SecondaryText          string                           `json:"secondaryText"` // 副交集辅助说明（灰色；缺省端不展示）
	WeightTier             string                           `json:"weightTier"`    // light | heavy（内容卡交集轻重等级，云侧离散产出）
	ObjectKind             string                           `json:"objectKind"`    // person | circle | school | place | enterprise
	SharedCount            int                              `json:"sharedCount"`
	Strength               float64                          `json:"strength"`
	ConfidenceLabel        string                           `json:"confidenceLabel"`
	ModelReasonBucket      string                           `json:"modelReasonBucket"`
	RelationKind           string                           `json:"relationKind"`
	RelationObjectID       string                           `json:"relationObjectId"`
	ActionType             string                           `json:"actionType"`
	ActionTargetID         string                           `json:"actionTargetId"`
	Source                 string                           `json:"source"`
	TagRefs                []string                         `json:"tagRefs"`
	FreshAt                string                           `json:"freshAt"`
	ExpiresAt              string                           `json:"expiresAt"`
	IntersectionPoints     []IntersectionPointView          `json:"intersectionPoints"`
	PointSummarySnapshotID string                           `json:"pointSummarySnapshotId"`
	FactPointCount         int                              `json:"factPointCount"`
	RecommendedPointCount  int                              `json:"recommendedPointCount"`
	TotalPointCount        int                              `json:"totalPointCount"`
	DimensionPointSummary  []IntersectionDimensionTallyView `json:"dimensionPointSummary"`
	PointClassLabel        string                           `json:"pointClassLabel"`
	ConnectionSummary      string                           `json:"connectionSummary"`
	RecommendationTraceID  string                           `json:"recommendationTraceId"`
	LastRecommendedAt      string                           `json:"lastRecommendedAt"`
	SeenAt                 string                           `json:"seenAt"`
	RankState              string                           `json:"rankState"`
}

// IntersectionPointView 是用户可见交集点列表；摘要数字只能由同一批点派生。
type IntersectionPointView struct {
	PointID          string   `json:"pointId"`
	PointClass       string   `json:"pointClass"` // fact | recommended
	Dimension        string   `json:"dimension"`
	Label            string   `json:"label"`
	DisplayText      string   `json:"displayText"`
	SourceRef        string   `json:"sourceRef"`
	Visibility       string   `json:"visibility"`
	Count            int      `json:"count"`            // 证据组聚合条数（如「共同好友 4」中的 4）
	SampleText       string   `json:"sampleText"`       // 实例化样本（某好友名/地点名/内容标题）
	SampleAvatarURLs []string `json:"sampleAvatarUrls"` // 头像簇（≤3）
}

func (v IntersectionReasonView) coolKey() string {
	if strings.TrimSpace(v.ActionTargetID) != "" {
		return v.ActionTargetID
	}
	return v.RelationObjectID
}

// IntersectionDimensionTallyView 单维度计数（与 intersection_dimension_tally.yaml 对齐）。
type IntersectionDimensionTallyView struct {
	Dimension string `json:"dimension"`
	Label     string `json:"label"`
	Count     int    `json:"count"`
	NewCount  int    `json:"newCount"`
	BriefText string `json:"briefText"` // 云侧实例化动态简报句（缺省端回落 label+newCount）
}

// IntersectionInboxSummaryView 我的交集聚合摘要（与 intersection_inbox_summary.yaml 对齐）。
type IntersectionInboxSummaryView struct {
	TotalCount    int                              `json:"totalCount"`
	TotalNewCount int                              `json:"totalNewCount"`
	Dimensions    []IntersectionDimensionTallyView `json:"dimensions"`
	GeneratedAt   string                           `json:"generatedAt"`
}

// IntersectionSource 提供事实与概率两通道的交集理由。
// 事实通道（FactReasons）为可向用户说明的真实交集（请求期查询/读模型，不打分）；
// 概率通道（AffinityReasons）为算法推荐（/v1/score 产出 RecommendationAffinity）。
// 默认实现返回空（事实数据由环境 seed 驱动，不在服务端伪造）。
type IntersectionSource interface {
	FactReasons(ctx context.Context, userID, channel string) ([]IntersectionReasonView, error)
	AffinityReasons(ctx context.Context, userID, channel string) ([]IntersectionReasonView, error)
	// ObjectReasons 返回 viewer 与某一具体对象（user/circle/entity）的关系类交集理由，
	// 用于对象页交集卡（共同好友/联系人来过/好友加入等证据组）。
	// objectType 为开放字符串（与端侧一致），未知类型由源返回空，不在服务端伪造。
	ObjectReasons(ctx context.Context, viewerID, objectID, objectType string) ([]IntersectionReasonView, error)
}

type emptyIntersectionSource struct{}

func (emptyIntersectionSource) FactReasons(context.Context, string, string) ([]IntersectionReasonView, error) {
	return nil, nil
}
func (emptyIntersectionSource) AffinityReasons(context.Context, string, string) ([]IntersectionReasonView, error) {
	return nil, nil
}
func (emptyIntersectionSource) ObjectReasons(context.Context, string, string, string) ([]IntersectionReasonView, error) {
	return nil, nil
}

// intersectionRedis 抽象 Redis 路由，便于测试注入。*rtredis.Router 满足该接口。
type intersectionRedis interface {
	ForKey(key string) rtredis.Client
}

const (
	// defaultIntersectionCooldownDays 跨会话推荐冷却窗口默认天数。
	// 唯一 TTL 真相源同时登记在 contracts/metadata/_shared/redis_keyspace.yaml: rec:icool。
	defaultIntersectionCooldownDays       = 14
	defaultIntersectionMaxCandidateWindow = 20
	intersectionCooldownTTL               = 30 * 24 * time.Hour
	watermarkCacheTTL                     = 90 * 24 * time.Hour
)

var intersectionDimensionLabels = map[string]string{
	"identity":     "身份",
	"location":     "地点",
	"content":      "内容",
	"interest":     "兴趣",
	"relationship": "关系",
}

// IntersectionService 承载交集统一体验的服务端核心机制：
// 事实/概率合并排序、跨会话冷却窗口、保鲜过滤、per-dimension 已读水位。
type IntersectionService struct {
	source             IntersectionSource
	redis              intersectionRedis
	cooldownDays       int
	maxCandidateWindow int
	now                func() time.Time
	metrics            IntersectionMetricsRecorder
}

// IntersectionServiceOption 配置项。
type IntersectionServiceOption func(*IntersectionService)

// WithIntersectionSource 注入事实/概率数据源。
func WithIntersectionSource(s IntersectionSource) IntersectionServiceOption {
	return func(svc *IntersectionService) {
		if s != nil {
			svc.source = s
		}
	}
}

// WithIntersectionCooldownDays 覆盖冷却天数（policy 可配）。
func WithIntersectionCooldownDays(days int) IntersectionServiceOption {
	return func(svc *IntersectionService) {
		if days > 0 {
			svc.cooldownDays = days
		}
	}
}

// WithIntersectionMaxCandidateWindow 控制请求期稳定排序窗口，默认 20。
func WithIntersectionMaxCandidateWindow(limit int) IntersectionServiceOption {
	return func(svc *IntersectionService) {
		if limit > 0 {
			svc.maxCandidateWindow = limit
		}
	}
}

// WithIntersectionMetrics 注入业务 SLI 观测 recorder（漏斗/冷却/保鲜/清零）。
func WithIntersectionMetrics(m IntersectionMetricsRecorder) IntersectionServiceOption {
	return func(svc *IntersectionService) {
		if m != nil {
			svc.metrics = m
		}
	}
}

// NewIntersectionService 构造交集服务。router 为 nil 时退化为无冷却/无水位（仅排序）。
func NewIntersectionService(router intersectionRedis, opts ...IntersectionServiceOption) *IntersectionService {
	svc := &IntersectionService{
		source:             emptyIntersectionSource{},
		redis:              router,
		cooldownDays:       defaultIntersectionCooldownDays,
		maxCandidateWindow: defaultIntersectionMaxCandidateWindow,
		now:                time.Now,
		metrics:            noopIntersectionMetrics{},
	}
	for _, opt := range opts {
		opt(svc)
	}
	return svc
}

func cooldownKey(userID string) string  { return "rec:icool:{" + userID + "}" }
func watermarkKey(userID string) string { return "cache:viewer_intersections:" + userID }

// ReportExposure 记录已曝光对象；Feed 后续保留对象但施加 seen penalty。
func (s *IntersectionService) ReportExposure(ctx context.Context, userID string, objectIDs []string) error {
	if s.redis == nil || strings.TrimSpace(userID) == "" || len(objectIDs) == 0 {
		return nil
	}
	key := cooldownKey(userID)
	client := s.redis.ForKey(key)
	expireScore := float64(s.now().Add(time.Duration(s.cooldownDays) * 24 * time.Hour).Unix())
	written := 0
	for _, id := range objectIDs {
		id = strings.TrimSpace(id)
		if id == "" {
			continue
		}
		if err := client.ZAdd(ctx, key, expireScore, id); err != nil {
			return err
		}
		written++
	}
	if written > 0 {
		s.metrics.ObserveExposureReported(written)
	}
	return client.Expire(ctx, key, intersectionCooldownTTL)
}

// seenKeys 返回仍在记忆窗口内的已曝光对象集合（score = 过期时刻 > now）。
func (s *IntersectionService) seenKeys(ctx context.Context, userID string) map[string]struct{} {
	out := map[string]struct{}{}
	if s.redis == nil || strings.TrimSpace(userID) == "" {
		return out
	}
	key := cooldownKey(userID)
	nowUnix := float64(s.now().Unix())
	members, err := s.redis.ForKey(key).ZRangeByScore(ctx, key, nowUnix, float64(1<<62), 0)
	if err != nil {
		return out
	}
	for _, m := range members {
		out[m] = struct{}{}
	}
	return out
}

// MarkVisited 推进已读水位并清零未读。dimension 为空表示全部维度。
func (s *IntersectionService) MarkVisited(ctx context.Context, userID, dimension string) error {
	if s.redis == nil || strings.TrimSpace(userID) == "" {
		return nil
	}
	key := watermarkKey(userID)
	client := s.redis.ForKey(key)
	nowUnix := strconv.FormatInt(s.now().Unix(), 10)
	dims := []string{dimension}
	if strings.TrimSpace(dimension) == "" {
		dims = []string{"identity", "location", "content", "interest", "relationship"}
	}
	for _, d := range dims {
		if err := client.HSet(ctx, key, "wm:"+d, nowUnix); err != nil {
			return err
		}
		s.metrics.ObserveInboxVisit(d)
	}
	return client.Expire(ctx, key, watermarkCacheTTL)
}

func (s *IntersectionService) watermarks(ctx context.Context, userID string) map[string]int64 {
	out := map[string]int64{}
	if s.redis == nil || strings.TrimSpace(userID) == "" {
		return out
	}
	key := watermarkKey(userID)
	all, err := s.redis.ForKey(key).HGetAll(ctx, key)
	if err != nil {
		return out
	}
	for field, v := range all {
		if !strings.HasPrefix(field, "wm:") {
			continue
		}
		if ts, perr := strconv.ParseInt(v, 10, 64); perr == nil {
			out[strings.TrimPrefix(field, "wm:")] = ts
		}
	}
	return out
}

// isFresh 判断交集是否在保鲜期内（expiresAt 为空视为长期有效）。
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
	if strings.TrimSpace(r.DisplayText) != "" {
		return r.DisplayText
	}
	if strings.TrimSpace(r.Label) != "" {
		return r.Label
	}
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
		Label:       r.Label,
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
		if r.RecommendationTraceID != "" {
			r.PointSummarySnapshotID = r.RecommendationTraceID
		} else {
			r.PointSummarySnapshotID = r.IntersectionID
		}
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
	return r
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

// anchorAggregateCount 取锚点对应的可枚举计数：逐条桥接型（一点一人）用 reason 级
// SharedCount，聚合型（单点携带计数）用 point.Count。
func anchorAggregateCount(r IntersectionReasonView, anchor IntersectionPointView) int {
	switch anchor.SourceRef {
	case "followeeVisited", "followeeInObject", "followeeViewing":
		if r.SharedCount > 0 {
			return r.SharedCount
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
	default:
		if anchor.Count > 0 {
			return anchor.Count
		}
		return 1
	}
}

// explainPrimaryText 按 §17.1「主语[数量+关系限定] + 谓语 + 宾语」实例化事实结论句；
// affinity 走概率通道分支。kind 取 §5.4 注册表标准名；未登记 kind 返回空（不造假）。
func explainPrimaryText(r IntersectionReasonView, anchor IntersectionPointView) string {
	if r.IntersectionClass == "affinity" {
		return affinityPrimaryText(r, anchor)
	}
	n := anchorAggregateCount(r, anchor)
	switch anchor.SourceRef {
	case "sharedFollowees", "commonFollower":
		return fmt.Sprintf("你们有%d位共同关注的人", n)
	case "commonContact":
		return fmt.Sprintf("你们有%d位共同联系人", n)
	case "sharedCircle", "coMemberCircle":
		return fmt.Sprintf("你们共同加入了%d个圈子", n)
	case "coCommented", "sharedDiscussion":
		return fmt.Sprintf("你们都讨论过%d篇相同内容", n)
	case "coSharedContent":
		return fmt.Sprintf("你们都分享过%d篇相同内容", n)
	case "coCreatedContent":
		return "你们都创作过相关内容"
	case "coVisitedEntity":
		return fmt.Sprintf("你们都去过%d个相同的地方", n)
	case "coWishlistedEntity":
		return fmt.Sprintf("你们都想去%d个相同的地方", n)
	case "sharedEntityAttention":
		return fmt.Sprintf("你和%d人共同关注了这里", n)
	case "followeeVisited":
		return fmt.Sprintf("%d位你关注的人来过这里", n)
	case "followeeInObject":
		return fmt.Sprintf("%d位你关注的人在这里", n)
	case "followeeViewing":
		return "你关注的人最近看过这些内容"
	case "followeeDiscussedThis":
		return "你关注的人也在讨论这些主题"
	case "sharedTagSample":
		if r.Source == "circleTag" {
			return "你在圈子里常看这些主题"
		}
		return "你们都关注这些主题"
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
func (s *IntersectionService) Summary(ctx context.Context, userID string) (IntersectionInboxSummaryView, error) {
	reasons, err := s.source.FactReasons(ctx, userID, "")
	if err != nil {
		return IntersectionInboxSummaryView{}, err
	}
	wm := s.watermarks(ctx, userID)
	type agg struct {
		count    int
		newCount int
	}
	byDim := map[string]*agg{}
	order := []string{}
	total := 0
	totalNew := 0
	for _, raw := range reasons {
		r := hydratePointSummary(raw)
		if !s.isFresh(r) {
			s.metrics.ObserveInboxFiltered("stale")
			continue
		}
		for _, point := range r.IntersectionPoints {
			dim := point.Dimension
			if dim == "" {
				dim = r.Dimension
			}
			a, ok := byDim[dim]
			if !ok {
				a = &agg{}
				byDim[dim] = a
				order = append(order, dim)
			}
			a.count++
			total++
			if freshUnix(r) > wm[dim] {
				a.newCount++
				totalNew++
			}
		}
	}
	dims := make([]IntersectionDimensionTallyView, 0, len(order))
	for _, d := range order {
		dims = append(dims, IntersectionDimensionTallyView{
			Dimension: d,
			Label:     intersectionDimensionLabels[d],
			Count:     byDim[d].count,
			NewCount:  byDim[d].newCount,
		})
	}
	// 未读多的维度优先，便于端侧"最多 3 个维度"截断时优先展示有新增的维度。
	sort.SliceStable(dims, func(i, j int) bool {
		if dims[i].NewCount != dims[j].NewCount {
			return dims[i].NewCount > dims[j].NewCount
		}
		return dims[i].Count > dims[j].Count
	})
	return IntersectionInboxSummaryView{
		TotalCount:    total,
		TotalNewCount: totalNew,
		Dimensions:    dims,
		GeneratedAt:   s.now().UTC().Format(time.RFC3339),
	}, nil
}

// List 按维度列出事实交集，自上次查看的新增在前。
func (s *IntersectionService) List(ctx context.Context, userID, dimension string, limit int) ([]IntersectionReasonView, error) {
	reasons, err := s.source.FactReasons(ctx, userID, "")
	if err != nil {
		return nil, err
	}
	wm := s.watermarks(ctx, userID)
	filtered := make([]IntersectionReasonView, 0, len(reasons))
	for _, raw := range reasons {
		r := hydratePointSummary(raw)
		if dimension != "" && r.Dimension != dimension {
			continue
		}
		if !s.isFresh(r) {
			s.metrics.ObserveInboxFiltered("stale")
			continue
		}
		filtered = append(filtered, r)
	}
	sort.SliceStable(filtered, func(i, j int) bool {
		iNew := freshUnix(filtered[i]) > wm[filtered[i].Dimension]
		jNew := freshUnix(filtered[j]) > wm[filtered[j].Dimension]
		if iNew != jNew {
			return iNew
		}
		return freshUnix(filtered[i]) > freshUnix(filtered[j])
	})
	if limit > 0 && len(filtered) > limit {
		filtered = filtered[:limit]
	}
	return filtered, nil
}

// Feed 首页/频道交集推荐：事实/推荐交集点同源合并；已曝光对象保留但降权。
func (s *IntersectionService) Feed(ctx context.Context, userID, channel string, limit int) ([]IntersectionReasonView, error) {
	facts, err := s.source.FactReasons(ctx, userID, channel)
	if err != nil {
		return nil, err
	}
	affinities, err := s.source.AffinityReasons(ctx, userID, channel)
	if err != nil {
		return nil, err
	}
	seen := s.seenKeys(ctx, userID)
	now := s.now().UTC().Format(time.RFC3339)
	metricChannel := channel
	if strings.TrimSpace(metricChannel) == "" {
		metricChannel = "default"
	}
	merged := make([]IntersectionReasonView, 0, len(facts)+len(affinities))
	for _, r := range append(facts, affinities...) {
		if !s.isFresh(r) {
			s.metrics.ObserveFeedFiltered(metricChannel, "stale")
			continue
		}
		r = hydratePointSummary(r)
		// T3 空窗治理：展示语言不完备的 reason 不进 spotlight 候选窗
		// （primaryText 必备；人级 reason 必须有头像，物级由对象头图承载）。
		if !isSpotlightDisplayComplete(r) {
			s.metrics.ObserveFeedFiltered(metricChannel, "display_incomplete")
			continue
		}
		r.LastRecommendedAt = now
		if _, ok := seen[r.coolKey()]; ok {
			r.RankState = "seen"
			r.SeenAt = now
		}
		class := "fact"
		if r.IntersectionClass == "affinity" {
			class = "affinity"
		}
		s.metrics.ObserveFeedCandidate(metricChannel, class, r.RankState)
		merged = append(merged, r)
	}
	sort.SliceStable(merged, func(i, j int) bool {
		iSeen := merged[i].RankState == "seen"
		jSeen := merged[j].RankState == "seen"
		if iSeen != jSeen {
			return !iSeen
		}
		iFact := merged[i].IntersectionClass != "affinity"
		jFact := merged[j].IntersectionClass != "affinity"
		if iFact != jFact {
			return iFact
		}
		if merged[i].Strength != merged[j].Strength {
			return merged[i].Strength > merged[j].Strength
		}
		if merged[i].TotalPointCount != merged[j].TotalPointCount {
			return merged[i].TotalPointCount > merged[j].TotalPointCount
		}
		return freshUnix(merged[i]) > freshUnix(merged[j])
	})
	if s.maxCandidateWindow > 0 && len(merged) > s.maxCandidateWindow {
		merged = merged[:s.maxCandidateWindow]
	}
	if limit > 0 && len(merged) > limit {
		return merged[:limit], nil
	}
	return merged, nil
}

// isSpotlightDisplayComplete 候选窗完备性（WP1·T3）：primaryText 非空，
// 且人级 reason（objectKind==person）必须带 avatarUrl；非人对象的头图由
// 端侧对象卡承载，不在 reason 上强制。
func isSpotlightDisplayComplete(r IntersectionReasonView) bool {
	if strings.TrimSpace(r.PrimaryText) == "" {
		return false
	}
	if r.ObjectKind == "person" && strings.TrimSpace(r.AvatarURL) == "" {
		return false
	}
	return true
}

// evidenceKindRank 证据组 kind 的挖掘强度（§9.8）：值越小越靠前；
// 人物 > 事物 > 地点 > 内容 > 身份 > 兴趣fact > recommended。
// kind 取值集合 = 交集词典 §5.4 唯一注册表标准名（云侧唯一真相源，端侧不解析语义）。
// 未知 kind 落中段，保证未来新增维度优雅降级（不写死闭集，缺省排在已知 fact 之后、recommended 之前）。
func evidenceKindRank(kind, pointClass string) int {
	if pointClass == "recommended" {
		return 900
	}
	switch kind {
	case "sharedFollowees", "commonFollower", "commonContact",
		"followeeInObject", "followeeVisited", "followeeViewing", "followeeDiscussedThis":
		return 10
	case "coMemberCircle", "sharedCircle", "sameCompany", "sameTeam", "sameIndustry",
		"sharedEntityAttention", "coWishlistedEntity":
		return 20
	case "coVisitedEntity":
		return 30
	case "coCommented", "coSharedContent", "coCreatedContent", "sharedDiscussion":
		return 40
	case "sameSchool", "sameDepartment", "sameMajor", "sameCohort", "alumni",
		"alumniHere", "colleagueHere":
		return 50
	case "sharedTagSample":
		return 60
	default:
		return 500
	}
}

// reasonObjectRank 取一条 reason 的最强可见点排序键（用于对象多 reason 时整体排序）。
func reasonObjectRank(r IntersectionReasonView) int {
	best := 1000
	for _, p := range r.IntersectionPoints {
		if p.Visibility == "hidden" {
			continue
		}
		if rank := evidenceKindRank(p.SourceRef, p.PointClass); rank < best {
			best = rank
		}
	}
	return best
}

// ObjectIntersections 对象页「我与该对象」的关系类交集（§2 闭集 + 三层关系分层）。
// 经 source.ObjectReasons 取请求期事实/推荐证据组，hydrate 后按锚强度排序（§9.8）。
// 数字 single-source：摘要由 hydratePointSummary 从可见点派生，端不二次推导。
func (s *IntersectionService) ObjectIntersections(ctx context.Context, viewerID, objectID, objectType string, limit int) ([]IntersectionReasonView, error) {
	if strings.TrimSpace(objectID) == "" {
		return nil, nil
	}
	reasons, err := s.source.ObjectReasons(ctx, viewerID, objectID, objectType)
	if err != nil {
		return nil, err
	}
	out := make([]IntersectionReasonView, 0, len(reasons))
	for _, raw := range reasons {
		r := hydratePointSummary(raw)
		if !s.isFresh(r) {
			continue
		}
		// 同一 reason 内的证据点按锚强度排序（事实优先、recommended 殿后）。
		sort.SliceStable(r.IntersectionPoints, func(i, j int) bool {
			ri := evidenceKindRank(r.IntersectionPoints[i].SourceRef, r.IntersectionPoints[i].PointClass)
			rj := evidenceKindRank(r.IntersectionPoints[j].SourceRef, r.IntersectionPoints[j].PointClass)
			if ri != rj {
				return ri < rj
			}
			return r.IntersectionPoints[i].Count > r.IntersectionPoints[j].Count
		})
		out = append(out, r)
	}
	sort.SliceStable(out, func(i, j int) bool {
		ri := reasonObjectRank(out[i])
		rj := reasonObjectRank(out[j])
		if ri != rj {
			return ri < rj
		}
		return out[i].TotalPointCount > out[j].TotalPointCount
	})
	if limit > 0 && len(out) > limit {
		out = out[:limit]
	}
	return out, nil
}
