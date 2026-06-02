package application

import (
	"context"
	"sort"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

// IntersectionReasonView 是交集理由的服务端视图，与 recommendation/rec_model
// projections/intersection_reason.yaml 字段对齐（端只读、不本地拼装）。
type IntersectionReasonView struct {
	IntersectionID    string   `json:"intersectionId"`
	IntersectionClass string   `json:"intersectionClass"` // fact | affinity
	Dimension         string   `json:"dimension"`
	DisplayName       string   `json:"displayName"`
	AvatarURL         string   `json:"avatarUrl"`
	Label             string   `json:"label"`
	DisplayText       string   `json:"displayText"`
	SharedCount       int      `json:"sharedCount"`
	Strength          float64  `json:"strength"`
	ConfidenceLabel   string   `json:"confidenceLabel"`
	ModelReasonBucket string   `json:"modelReasonBucket"`
	RelationKind      string   `json:"relationKind"`
	RelationObjectID  string   `json:"relationObjectId"`
	ActionType        string   `json:"actionType"`
	ActionTargetID    string   `json:"actionTargetId"`
	Source            string   `json:"source"`
	TagRefs           []string `json:"tagRefs"`
	FreshAt           string   `json:"freshAt"`
	ExpiresAt         string   `json:"expiresAt"`
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
}

type emptyIntersectionSource struct{}

func (emptyIntersectionSource) FactReasons(context.Context, string, string) ([]IntersectionReasonView, error) {
	return nil, nil
}
func (emptyIntersectionSource) AffinityReasons(context.Context, string, string) ([]IntersectionReasonView, error) {
	return nil, nil
}

// intersectionRedis 抽象 Redis 路由，便于测试注入。*rtredis.Router 满足该接口。
type intersectionRedis interface {
	ForKey(key string) rtredis.Client
}

const (
	// defaultIntersectionCooldownDays 跨会话推荐冷却窗口默认天数。
	// 唯一 TTL 真相源同时登记在 contracts/metadata/_shared/redis_keyspace.yaml: rec:icool。
	defaultIntersectionCooldownDays = 14
	intersectionCooldownTTL         = 30 * 24 * time.Hour
	watermarkCacheTTL               = 90 * 24 * time.Hour
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
	source       IntersectionSource
	redis        intersectionRedis
	cooldownDays int
	now          func() time.Time
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

// NewIntersectionService 构造交集服务。router 为 nil 时退化为无冷却/无水位（仅排序）。
func NewIntersectionService(router intersectionRedis, opts ...IntersectionServiceOption) *IntersectionService {
	svc := &IntersectionService{
		source:       emptyIntersectionSource{},
		redis:        router,
		cooldownDays: defaultIntersectionCooldownDays,
		now:          time.Now,
	}
	for _, opt := range opts {
		opt(svc)
	}
	return svc
}

func cooldownKey(userID string) string  { return "rec:icool:{" + userID + "}" }
func watermarkKey(userID string) string { return "cache:viewer_intersections:" + userID }

// ReportExposure 将曝光未转化的交集对象写入冷却集（跨会话）。
func (s *IntersectionService) ReportExposure(ctx context.Context, userID string, objectIDs []string) error {
	if s.redis == nil || strings.TrimSpace(userID) == "" || len(objectIDs) == 0 {
		return nil
	}
	key := cooldownKey(userID)
	client := s.redis.ForKey(key)
	expireScore := float64(s.now().Add(time.Duration(s.cooldownDays) * 24 * time.Hour).Unix())
	for _, id := range objectIDs {
		id = strings.TrimSpace(id)
		if id == "" {
			continue
		}
		if err := client.ZAdd(ctx, key, expireScore, id); err != nil {
			return err
		}
	}
	return client.Expire(ctx, key, intersectionCooldownTTL)
}

// coolingDown 返回当前仍在冷却窗口内的对象 id 集合（score = 过期时刻 > now）。
func (s *IntersectionService) coolingDown(ctx context.Context, userID string) map[string]struct{} {
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
	for _, r := range reasons {
		if !s.isFresh(r) {
			continue
		}
		a, ok := byDim[r.Dimension]
		if !ok {
			a = &agg{}
			byDim[r.Dimension] = a
			order = append(order, r.Dimension)
		}
		a.count++
		total++
		if freshUnix(r) > wm[r.Dimension] {
			a.newCount++
			totalNew++
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
	for _, r := range reasons {
		if dimension != "" && r.Dimension != dimension {
			continue
		}
		if !s.isFresh(r) {
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

// Feed 首页/频道交集推荐：事实优先（strength + 新鲜度），概率其次（strength/score），
// 统一过保鲜期与跨会话冷却窗口。
func (s *IntersectionService) Feed(ctx context.Context, userID, channel string, limit int) ([]IntersectionReasonView, error) {
	facts, err := s.source.FactReasons(ctx, userID, channel)
	if err != nil {
		return nil, err
	}
	affinities, err := s.source.AffinityReasons(ctx, userID, channel)
	if err != nil {
		return nil, err
	}
	cooled := s.coolingDown(ctx, userID)
	pick := func(in []IntersectionReasonView) []IntersectionReasonView {
		out := make([]IntersectionReasonView, 0, len(in))
		for _, r := range in {
			if !s.isFresh(r) {
				continue
			}
			if _, cooling := cooled[r.coolKey()]; cooling {
				continue
			}
			out = append(out, r)
		}
		sort.SliceStable(out, func(i, j int) bool {
			if out[i].Strength != out[j].Strength {
				return out[i].Strength > out[j].Strength
			}
			return freshUnix(out[i]) > freshUnix(out[j])
		})
		return out
	}
	merged := append(pick(facts), pick(affinities)...)
	if limit > 0 && len(merged) > limit {
		merged = merged[:limit]
	}
	return merged, nil
}
