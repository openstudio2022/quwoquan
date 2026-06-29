package intersection

import (
	"context"
	"log/slog"
	"sort"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/content-service/internal/application/ports"
	"quwoquan_service/services/content-service/internal/generated"
)

// 交集视图值对象（IntersectionReasonView / PointView / TargetView / TextSpanView /
// VisualView / DimensionTallyView / InboxSummaryView 及 coolKey）见 intersection_views.go
// （同 application 包拆分，R03 行数预算）。

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

// IntersectionListQuery 是 ListMyIntersections 的服务端过滤/分页参数。
type IntersectionListQuery struct {
	Dimension  string
	Filter     string
	SourceRef  string
	TimeBucket string
	Cursor     string
	Limit      int
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
	watermarkStore     ports.WatermarkStore
	cooldownDays       int
	maxCandidateWindow int
	now                func() time.Time
	metrics            IntersectionMetricsRecorder
	logger             *slog.Logger
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

// WithIntersectionMetrics 注入业务 SLI 观测 recorder（漏斗/冷却/保鲜/清零/Redis 降级）。
func WithIntersectionMetrics(m IntersectionMetricsRecorder) IntersectionServiceOption {
	return func(svc *IntersectionService) {
		if m != nil {
			svc.metrics = m
		}
	}
}

// WithIntersectionWatermarkStore 注入已读水位持久兜底存储（Mongo）。注入后 Redis 退化为
// 加速缓存：写以耐久存储为准、Redis 失败不阻断主请求；读优先 Redis、缺失/失败回落耐久并回暖。
func WithIntersectionWatermarkStore(store ports.WatermarkStore) IntersectionServiceOption {
	return func(svc *IntersectionService) {
		if store != nil {
			svc.watermarkStore = store
		}
	}
}

// WithIntersectionLogger 注入结构化日志器（Redis 降级等需可观测，禁止静默吞错）。
func WithIntersectionLogger(l *slog.Logger) IntersectionServiceOption {
	return func(svc *IntersectionService) {
		if l != nil {
			svc.logger = l
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
		logger:             slog.Default(),
	}
	for _, opt := range opts {
		opt(svc)
	}
	return svc
}

func cooldownKey(userID string) string { return "rec:icool:{" + userID + "}" }

// watermarkKey 是「我的交集」收件箱 per-dimension 已读水位 hash（D1 修复后独立于读模型
// 聚合快照）。唯一类型/TTL 真相源登记在 contracts/metadata/_shared/redis_keyspace.yaml:
// ix:watermark（hash，hash_tag userId，TTL 90 天，general scene）。
func watermarkKey(userID string) string { return "ix:watermark:{" + userID + "}" }

// ReportExposure 记录已曝光对象；Feed 后续保留对象但施加 seen penalty。
//
// 跨会话冷却记忆窗是「尽力而为」的 feed 去重信号：Redis 不可用时降级——记录降级指标 +
// 结构化告警日志，不向上抛错拖垮主请求（最坏只是本轮缺少 seen 降权，不影响首页可用）。
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
			s.degradeRedis("exposure_write", err, "userId", userID)
			return nil
		}
		written++
	}
	if written > 0 {
		s.metrics.ObserveExposureReported(written)
	}
	if err := client.Expire(ctx, key, intersectionCooldownTTL); err != nil {
		s.degradeRedis("exposure_write", err, "userId", userID)
	}
	return nil
}

// degradeRedis 统一记录一次 Redis 降级：发降级指标 + 结构化 warn 日志（禁止静默吞错）。
func (s *IntersectionService) degradeRedis(op string, err error, kv ...any) {
	s.metrics.ObserveRedisDegraded(op)
	if s.logger != nil {
		s.logger.Warn("intersection redis degraded", append([]any{"op", op, "error", err}, kv...)...)
	}
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
//
// 持久兜底语义：已读水位是用户感知的耐久状态（清零后不应因 Redis flush/宕机回弹为未读）。
//   - 注入了 watermarkStore 时：先写耐久存储（真相源）；耐久写失败才视为真错误向上抛。
//     随后尽力回写 Redis 缓存，Redis 失败仅降级（指标+日志），不阻断主请求。
//   - 未注入 watermarkStore 时（如纯单测）：退化为 Redis-only，Redis 失败同样降级返回 nil，
//     不拖垮主请求（最坏本次清零未生效，符合「降级不阻断」要求）。
func (s *IntersectionService) MarkVisited(ctx context.Context, userID, dimension string) error {
	if strings.TrimSpace(userID) == "" {
		return nil
	}
	nowTs := s.now().Unix()
	dims := []string{dimension}
	if strings.TrimSpace(dimension) == "" {
		dims = []string{"identity", "location", "content", "interest", "relationship"}
	}

	// 1) 耐久写（真相源）。
	if s.watermarkStore != nil {
		durable := make(map[string]int64, len(dims))
		for _, d := range dims {
			durable[d] = nowTs
		}
		if err := s.watermarkStore.SaveWatermarks(ctx, userID, durable); err != nil {
			return err
		}
	}
	for _, d := range dims {
		s.metrics.ObserveInboxVisit(d)
	}

	// 2) 回写 Redis 缓存（尽力而为；有耐久兜底时 Redis 失败仅降级）。
	if s.redis == nil {
		return nil
	}
	key := watermarkKey(userID)
	client := s.redis.ForKey(key)
	nowUnix := strconv.FormatInt(nowTs, 10)
	for _, d := range dims {
		if err := client.HSet(ctx, key, "wm:"+d, nowUnix); err != nil {
			s.degradeRedis("watermark_write", err, "userId", userID)
			return nil
		}
	}
	if err := client.Expire(ctx, key, watermarkCacheTTL); err != nil {
		s.degradeRedis("watermark_write", err, "userId", userID)
	}
	return nil
}

// watermarks 读取 per-dimension 已读水位：Redis 优先（热路径）；Redis 失败或缺失时回落耐久兜底
// 存储并尽力回暖 Redis（Redis flush/宕机后读位不丢）。任一路径都不向上抛错——读位缺失只会让
// 红点偏多（全部视为未读），不阻断主请求。
func (s *IntersectionService) watermarks(ctx context.Context, userID string) map[string]int64 {
	out := map[string]int64{}
	if strings.TrimSpace(userID) == "" {
		return out
	}
	key := watermarkKey(userID)

	redisErr := false
	if s.redis != nil {
		all, err := s.redis.ForKey(key).HGetAll(ctx, key)
		if err != nil {
			redisErr = true
			s.degradeRedis("watermark_read", err, "userId", userID)
		} else {
			for field, v := range all {
				if !strings.HasPrefix(field, "wm:") {
					continue
				}
				if ts, perr := strconv.ParseInt(v, 10, 64); perr == nil {
					out[strings.TrimPrefix(field, "wm:")] = ts
				}
			}
			if len(out) > 0 {
				return out // Redis 命中，热路径直出。
			}
		}
	}

	// Redis 未命中（缓存冷/被 flush）或 Redis 故障：回落耐久兜底。
	if s.watermarkStore == nil {
		return out
	}
	durable, err := s.watermarkStore.LoadWatermarks(ctx, userID)
	if err != nil {
		if s.logger != nil {
			s.logger.Warn("intersection watermark durable load failed", "userId", userID, "error", err)
		}
		return out
	}
	if len(durable) == 0 {
		return out
	}
	// 尽力回暖 Redis（仅当 Redis 可用且本轮非故障读）。
	if s.redis != nil && !redisErr {
		client := s.redis.ForKey(key)
		for d, ts := range durable {
			if herr := client.HSet(ctx, key, "wm:"+d, strconv.FormatInt(ts, 10)); herr != nil {
				s.degradeRedis("watermark_write", herr, "userId", userID)
				break
			}
		}
		_ = client.Expire(ctx, key, watermarkCacheTTL)
	}
	return durable
}

// isFresh 判断交集是否在保鲜期内（expiresAt 为空视为长期有效）。
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

// List 按维度/sourceRef/timeBucket/filter 分页列出事实交集。
// 列表契约：先全局去重，再按 strength/timeBucket/anchor/count 稳定排序，最后分页。
func (s *IntersectionService) List(ctx context.Context, userID string, query IntersectionListQuery) ([]IntersectionReasonView, string, bool, error) {
	reasons, err := s.source.FactReasons(ctx, userID, "")
	if err != nil {
		return nil, "", false, err
	}
	wm := s.watermarks(ctx, userID)
	filtered := make([]IntersectionReasonView, 0, len(reasons))
	for _, raw := range reasons {
		r := hydratePointSummary(raw)
		if strings.TrimSpace(r.TimeBucket) == "" {
			r.TimeBucket = resolveIntersectionListTimeBucket(s.now(), r.FreshAt)
		}
		if !matchesIntersectionListQuery(r, query, wm) {
			continue
		}
		if !s.isFresh(r) {
			s.metrics.ObserveInboxFiltered("stale")
			continue
		}
		filtered = append(filtered, r)
	}
	filtered = rankAndDedupeIntersectionList(userID, filtered)
	limit := query.Limit
	if limit <= 0 {
		limit = 50
	}
	if limit > 100 {
		limit = 100
	}
	offset := decodeIntersectionListCursor(query.Cursor)
	if offset > len(filtered) {
		offset = len(filtered)
	}
	end := offset + limit
	hasMore := end < len(filtered)
	if end > len(filtered) {
		end = len(filtered)
	}
	nextCursor := ""
	if hasMore {
		nextCursor = strconv.Itoa(end)
	}
	return filtered[offset:end], nextCursor, hasMore, nil
}

func rankAndDedupeIntersectionList(userID string, items []IntersectionReasonView) []IntersectionReasonView {
	chosen := make(map[string]IntersectionReasonView, len(items))
	for _, item := range items {
		key := intersectionListDedupeKey(userID, item)
		if strings.TrimSpace(item.DedupeKey) == "" {
			item.DedupeKey = key
		}
		existing, ok := chosen[key]
		if !ok || compareIntersectionListRank(item, existing) < 0 {
			chosen[key] = item
		}
	}
	ranked := make([]IntersectionReasonView, 0, len(chosen))
	for _, item := range chosen {
		ranked = append(ranked, item)
	}
	sort.SliceStable(ranked, func(i, j int) bool {
		return compareIntersectionListRank(ranked[i], ranked[j]) < 0
	})
	return ranked
}

func intersectionListDedupeKey(userID string, r IntersectionReasonView) string {
	viewerID := strings.TrimSpace(userID)
	objectID := strings.TrimSpace(r.ActionTargetID)
	if objectID == "" {
		objectID = strings.TrimSpace(r.RelationObjectID)
	}
	if objectID == "" {
		objectID = strings.TrimSpace(r.IntersectionID)
	}
	objectType := strings.TrimSpace(r.ObjectKind)
	intersectionKind := strings.TrimSpace(r.Kind)
	if intersectionKind == "" {
		intersectionKind = strings.TrimSpace(r.Source)
	}
	return strings.Join([]string{viewerID, objectID, objectType, intersectionKind}, ":")
}

func resolveIntersectionListTimeBucket(now time.Time, freshAt string) string {
	fresh, err := time.Parse(time.RFC3339, strings.TrimSpace(freshAt))
	if err != nil {
		return "lastMonth"
	}
	today := dateOnlyUTC(now)
	day := dateOnlyUTC(fresh)
	if day.Equal(today) {
		return "today"
	}
	if day.Equal(today.AddDate(0, 0, -1)) {
		return "yesterday"
	}
	if !day.Before(today.AddDate(0, 0, -7)) {
		return "last7Days"
	}
	if day.Year() == today.Year() && day.Month() == today.Month() {
		return "thisMonth"
	}
	lastMonth := today.AddDate(0, -1, 0)
	if day.Year() == lastMonth.Year() && day.Month() == lastMonth.Month() {
		return "lastMonth"
	}
	return "outOfRange"
}

func dateOnlyUTC(t time.Time) time.Time {
	utc := t.UTC()
	return time.Date(utc.Year(), utc.Month(), utc.Day(), 0, 0, 0, 0, time.UTC)
}

func compareIntersectionListRank(a, b IntersectionReasonView) int {
	if a.Strength != b.Strength {
		if a.Strength > b.Strength {
			return -1
		}
		return 1
	}
	if ap, bp := intersectionListTimeBucketPriority(a), intersectionListTimeBucketPriority(b); ap != bp {
		if ap < bp {
			return -1
		}
		return 1
	}
	if a.AnchorUserWeight != b.AnchorUserWeight {
		if a.AnchorUserWeight > b.AnchorUserWeight {
			return -1
		}
		return 1
	}
	if a.TotalPointCount != b.TotalPointCount {
		if a.TotalPointCount > b.TotalPointCount {
			return -1
		}
		return 1
	}
	if a.MutualCount != b.MutualCount {
		if a.MutualCount > b.MutualCount {
			return -1
		}
		return 1
	}
	return strings.Compare(stableIntersectionListKey(a), stableIntersectionListKey(b))
}

func intersectionListTimeBucketPriority(r IntersectionReasonView) int {
	switch strings.TrimSpace(r.TimeBucket) {
	case "today":
		return 0
	case "yesterday":
		return 1
	case "last7Days":
		return 2
	case "thisMonth":
		return 3
	case "lastMonth":
		return 4
	default:
		return 5
	}
}

func stableIntersectionListKey(r IntersectionReasonView) string {
	if key := strings.TrimSpace(r.DedupeKey); key != "" {
		return key
	}
	return strings.Join([]string{
		strings.TrimSpace(r.ActionTargetID),
		strings.TrimSpace(r.RelationObjectID),
		strings.TrimSpace(r.ObjectKind),
		strings.TrimSpace(r.Kind),
		strings.TrimSpace(r.IntersectionID),
	}, ":")
}

func matchesIntersectionListQuery(r IntersectionReasonView, query IntersectionListQuery, wm map[string]int64) bool {
	dimension := strings.TrimSpace(query.Dimension)
	if dimension != "" && r.Dimension != dimension {
		return false
	}
	timeBucket := strings.TrimSpace(query.TimeBucket)
	if timeBucket != "" && r.TimeBucket != timeBucket {
		return false
	}
	sourceRef := strings.TrimSpace(query.SourceRef)
	if sourceRef != "" && !reasonHasSourceRef(r, sourceRef) {
		return false
	}
	switch strings.TrimSpace(query.Filter) {
	case "", "all":
		return true
	case "new":
		return freshUnix(r) > wm[r.Dimension]
	case "fact":
		return r.IntersectionClass == "" || r.IntersectionClass == "fact"
	case "affinity", "recommended":
		return r.IntersectionClass == "affinity"
	default:
		return true
	}
}

func reasonHasSourceRef(r IntersectionReasonView, sourceRef string) bool {
	if r.Source == sourceRef {
		return true
	}
	for _, point := range r.IntersectionPoints {
		if point.SourceRef == sourceRef {
			return true
		}
	}
	return false
}

func decodeIntersectionListCursor(cursor string) int {
	cursor = strings.TrimSpace(cursor)
	if cursor == "" {
		return 0
	}
	n, err := strconv.Atoi(cursor)
	if err != nil || n < 0 {
		return 0
	}
	return n
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
// kind→rank 唯一真相源 = 机器可读注册表
// contracts/metadata/recommendation/rec_model/intersection_kind_registry.yaml 的 evidenceRank 字段，
// 经 tools/codegen_rec_intersection 生成 generated.IntersectionEvidenceRank 查表（§23 去桥接，禁手写 switch 第二份）。
// pointClass==recommended 固定落末段 900；未登记 kind 落中段（500），保证未来新增维度优雅降级。
func evidenceKindRank(kind, pointClass string) int {
	if pointClass == "recommended" {
		return 900
	}
	if rank, ok := generated.IntersectionEvidenceRank[kind]; ok {
		return rank
	}
	return 500
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
