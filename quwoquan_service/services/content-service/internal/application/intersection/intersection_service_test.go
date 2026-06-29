package intersection

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

// failingRedisClient 包裹一个 Redis client，使受 D（Redis 不可用降级/兜底）覆盖的命令全部
// 返回错误，用于模拟 Redis 宕机。仅覆盖交集服务实际触达的命令；其余命令不应被调用。
type failingRedisClient struct {
	rtredis.Client
	err error
}

func (f failingRedisClient) ZAdd(context.Context, string, float64, string) error { return f.err }
func (f failingRedisClient) HSet(context.Context, string, string, string) error  { return f.err }
func (f failingRedisClient) Expire(context.Context, string, time.Duration) error { return f.err }
func (f failingRedisClient) HGetAll(context.Context, string) (map[string]string, error) {
	return nil, f.err
}
func (f failingRedisClient) ZRangeByScore(context.Context, string, float64, float64, int) ([]string, error) {
	return nil, f.err
}

// failingRedisRouter 满足 intersectionRedis，所有 key 都路由到失败 client。
type failingRedisRouter struct{ err error }

func (r failingRedisRouter) ForKey(string) rtredis.Client {
	return failingRedisClient{err: r.err}
}

// memWatermarkStore 是内存耐久兜底，避免单测依赖 Mongo。
type memWatermarkStore struct {
	docs      map[string]map[string]int64
	loadCalls int
	saveCalls int
}

func newMemWatermarkStore() *memWatermarkStore {
	return &memWatermarkStore{docs: map[string]map[string]int64{}}
}

func (m *memWatermarkStore) LoadWatermarks(_ context.Context, userID string) (map[string]int64, error) {
	m.loadCalls++
	out := map[string]int64{}
	for d, ts := range m.docs[userID] {
		out[d] = ts
	}
	return out, nil
}

func (m *memWatermarkStore) SaveWatermarks(_ context.Context, userID string, dims map[string]int64) error {
	m.saveCalls++
	if m.docs[userID] == nil {
		m.docs[userID] = map[string]int64{}
	}
	for d, ts := range dims {
		if ts > m.docs[userID][d] { // 单调推进
			m.docs[userID][d] = ts
		}
	}
	return nil
}

type stubSource struct {
	facts      []IntersectionReasonView
	affinities []IntersectionReasonView
	object     []IntersectionReasonView
}

func (s stubSource) FactReasons(context.Context, string, string) ([]IntersectionReasonView, error) {
	return s.facts, nil
}
func (s stubSource) AffinityReasons(context.Context, string, string) ([]IntersectionReasonView, error) {
	return s.affinities, nil
}
func (s stubSource) ObjectReasons(context.Context, string, string, string) ([]IntersectionReasonView, error) {
	return s.object, nil
}

func newTestRouter(t *testing.T) *rtredis.Router {
	t.Helper()
	return rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
}

func fixedNow(svc *IntersectionService, ts time.Time) {
	svc.now = func() time.Time { return ts }
}

func TestIntersectionService_SummaryNewCountAndVisitClears(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	src := stubSource{facts: []IntersectionReasonView{
		{IntersectionID: "a", Dimension: "identity", FreshAt: now.Add(-time.Hour).Format(time.RFC3339), ActionTargetID: "u1"},
		{IntersectionID: "b", Dimension: "identity", FreshAt: now.Add(-2 * time.Hour).Format(time.RFC3339), ActionTargetID: "u2"},
		{IntersectionID: "c", Dimension: "content", FreshAt: now.Add(-time.Hour).Format(time.RFC3339), ActionTargetID: "p1"},
	}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)
	ctx := context.Background()

	sum, err := svc.Summary(ctx, "viewer1")
	if err != nil {
		t.Fatalf("summary: %v", err)
	}
	if sum.TotalCount != 3 {
		t.Fatalf("want total 3, got %d", sum.TotalCount)
	}
	if sum.TotalNewCount != 3 {
		t.Fatalf("want all new (3), got %d", sum.TotalNewCount)
	}

	// 打开 identity 列表推进水位 → identity 未读清零，content 仍未读。
	if err := svc.MarkVisited(ctx, "viewer1", "identity"); err != nil {
		t.Fatalf("visit: %v", err)
	}
	sum2, err := svc.Summary(ctx, "viewer1")
	if err != nil {
		t.Fatalf("summary2: %v", err)
	}
	if sum2.TotalCount != 3 {
		t.Fatalf("want total still 3, got %d", sum2.TotalCount)
	}
	if sum2.TotalNewCount != 1 {
		t.Fatalf("want 1 new after identity visit, got %d", sum2.TotalNewCount)
	}
}

func TestIntersectionService_ExposureRetainsButDemotesSeen(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	src := stubSource{facts: []IntersectionReasonView{
		{IntersectionID: "a", Dimension: "identity", Strength: 0.9, ActionTargetID: "u1", PrimaryText: "你的8位校友关注了这里"},
		{IntersectionID: "b", Dimension: "content", Strength: 0.8, ActionTargetID: "p1", PrimaryText: "你们都讨论过2篇相同内容"},
	}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)
	ctx := context.Background()

	feed, err := svc.Feed(ctx, "viewer1", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	if len(feed) != 2 {
		t.Fatalf("want 2 before exposure, got %d", len(feed))
	}

	// 曝光 u1 未转化 → 后续仍保留，但按 seen penalty 排到未看对象后。
	if err := svc.ReportExposure(ctx, "viewer1", []string{"u1"}); err != nil {
		t.Fatalf("exposure: %v", err)
	}
	feed2, err := svc.Feed(ctx, "viewer1", "recommend", 10)
	if err != nil {
		t.Fatalf("feed2: %v", err)
	}
	if len(feed2) != 2 {
		t.Fatalf("want both objects retained after exposure, got %+v", feed2)
	}
	if feed2[0].ActionTargetID != "p1" || feed2[1].ActionTargetID != "u1" {
		t.Fatalf("want unseen p1 before seen u1, got %+v", feed2)
	}
	if feed2[1].RankState != "seen" || feed2[1].SeenAt == "" {
		t.Fatalf("seen item should carry rankState/seenAt, got %+v", feed2[1])
	}
}

func TestIntersectionService_PointSummaryDerivedFromVisiblePoints(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	src := stubSource{facts: []IntersectionReasonView{
		{
			IntersectionID: "multi",
			Dimension:      "relationship",
			Strength:       0.8,
			PrimaryText:    "你们有2位共同关注的人",
			FreshAt:        now.Add(-time.Hour).Format(time.RFC3339),
			ActionTargetID: "u1",
			IntersectionPoints: []IntersectionPointView{
				{PointID: "p1", PointClass: "fact", Dimension: "relationship", DisplayText: "共同好友 A", Visibility: "public"},
				{PointID: "p2", PointClass: "recommended", Dimension: "interest", DisplayText: "摄影内容相似", Visibility: "public"},
				{PointID: "p3", PointClass: "fact", Dimension: "relationship", DisplayText: "隐藏证据", Visibility: "hidden"},
			},
		},
	}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)

	feed, err := svc.Feed(context.Background(), "viewer1", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	if len(feed) != 1 {
		t.Fatalf("want 1 feed item, got %d", len(feed))
	}
	item := feed[0]
	if item.TotalPointCount != 2 || item.FactPointCount != 1 || item.RecommendedPointCount != 1 {
		t.Fatalf("point counts must derive from visible points, got %+v", item)
	}
	if len(item.IntersectionPoints) != 2 {
		t.Fatalf("hidden point should not be counted or returned, got %+v", item.IntersectionPoints)
	}
	sum, err := svc.Summary(context.Background(), "viewer1")
	if err != nil {
		t.Fatalf("summary: %v", err)
	}
	if sum.TotalCount != 2 {
		t.Fatalf("summary total must equal visible point count, got %d", sum.TotalCount)
	}
}

func TestIntersectionService_FeedFactBeforeAffinityAndFreshness(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	src := stubSource{
		facts: []IntersectionReasonView{
			{IntersectionID: "f1", IntersectionClass: "fact", Dimension: "identity", Strength: 0.5, ActionTargetID: "u1", PrimaryText: "你的8位校友关注了这里"},
			{IntersectionID: "stale", IntersectionClass: "fact", Dimension: "content", Strength: 0.99, ActionTargetID: "u9", PrimaryText: "你们都讨论过3篇相同内容", ExpiresAt: now.Add(-time.Hour).Format(time.RFC3339)},
		},
		affinities: []IntersectionReasonView{
			{IntersectionID: "p1", IntersectionClass: "affinity", Dimension: "interest", Strength: 0.95, ActionTargetID: "u2", PrimaryText: "为你推荐的相关内容"},
		},
	}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)

	feed, err := svc.Feed(context.Background(), "viewer1", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	if len(feed) != 2 {
		t.Fatalf("want 2 (stale filtered), got %d", len(feed))
	}
	if feed[0].IntersectionClass != "fact" {
		t.Fatalf("fact must rank before affinity, got %s first", feed[0].IntersectionClass)
	}
	if feed[1].IntersectionClass != "affinity" {
		t.Fatalf("affinity must be last, got %s", feed[1].IntersectionClass)
	}
}

func TestIntersectionService_MaxCandidateWindowCapsBeforeLimit(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	src := stubSource{facts: []IntersectionReasonView{
		{IntersectionID: "a", Dimension: "identity", Strength: 0.9, ActionTargetID: "u1", PrimaryText: "你的8位校友关注了这里"},
		{IntersectionID: "b", Dimension: "content", Strength: 0.8, ActionTargetID: "u2", PrimaryText: "你们都讨论过2篇相同内容"},
		{IntersectionID: "c", Dimension: "relationship", Strength: 0.7, ActionTargetID: "u3", PrimaryText: "你们有4位共同关注的人"},
	}}
	svc := NewIntersectionService(
		newTestRouter(t),
		WithIntersectionSource(src),
		WithIntersectionMaxCandidateWindow(2),
	)
	fixedNow(svc, now)

	feed, err := svc.Feed(context.Background(), "viewer1", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	if len(feed) != 2 {
		t.Fatalf("want max candidate window 2, got %d", len(feed))
	}
}

func TestIntersectionService_ObjectIntersectionsRanksByAnchorStrength(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	// 单对象多证据组：内容(coCommented) 先给、人物(sharedFollowees) 后给，
	// 期望 hydrate 后按锚强度（人物 > 内容）重排，事实在前、推荐殿后。
	src := stubSource{object: []IntersectionReasonView{
		{
			IntersectionID:   "objix_user_u_lin",
			Dimension:        "relationship",
			ActionTargetID:   "u_lin",
			RelationObjectID: "u_lin",
			IntersectionPoints: []IntersectionPointView{
				{PointID: "p_content", PointClass: "fact", Dimension: "content", SourceRef: "coCommented", Label: "共同讨论过", DisplayText: "共同讨论过", Count: 3},
				{PointID: "p_aff", PointClass: "recommended", Dimension: "interest", SourceRef: "affinity", Label: "可能合得来", DisplayText: "可能合得来"},
				{PointID: "p_friend", PointClass: "fact", Dimension: "relationship", SourceRef: "sharedFollowees", Label: "共同关注的人", DisplayText: "共同关注的人", Count: 4},
			},
		},
	}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)

	items, err := svc.ObjectIntersections(context.Background(), "viewer1", "u_lin", "user", 8)
	if err != nil {
		t.Fatalf("object intersections: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("want 1 reason, got %d", len(items))
	}
	pts := items[0].IntersectionPoints
	if len(pts) != 3 {
		t.Fatalf("want 3 points, got %d", len(pts))
	}
	// §9.8：人物(sharedFollowees) 排第一，内容(coCommented) 次之，recommended 殿后。
	if pts[0].SourceRef != "sharedFollowees" {
		t.Fatalf("want sharedFollowees first, got %s", pts[0].SourceRef)
	}
	if pts[1].SourceRef != "coCommented" {
		t.Fatalf("want coCommented second, got %s", pts[1].SourceRef)
	}
	if pts[2].PointClass != "recommended" {
		t.Fatalf("want recommended last, got %s", pts[2].PointClass)
	}
	// single-source：fact=2、recommended=1、total=3。
	if items[0].FactPointCount != 2 || items[0].RecommendedPointCount != 1 || items[0].TotalPointCount != 3 {
		t.Fatalf("point summary mismatch: fact=%d rec=%d total=%d",
			items[0].FactPointCount, items[0].RecommendedPointCount, items[0].TotalPointCount)
	}
}

// TestIntersectionService_SpotlightFiltersIncompleteDisplay（WP1·T3）：
// 进入候选窗的 reason 必须 primaryText 非空；人级 reason 必须带 avatarUrl。
func TestIntersectionService_SpotlightFiltersIncompleteDisplay(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	src := stubSource{facts: []IntersectionReasonView{
		// 无任何展示语言 → 不得进候选窗。
		{IntersectionID: "no_text", Dimension: "content", Strength: 0.9, ActionTargetID: "p0"},
		// 人级但缺头像 → 不得进候选窗。
		{IntersectionID: "person_no_avatar", Dimension: "relationship", Strength: 0.8,
			ActionTargetID: "u1", ObjectKind: "person", PrimaryText: "你们有3位共同关注的人"},
		// 人级且头像完备 → 进候选窗。
		{IntersectionID: "person_ok", Dimension: "relationship", Strength: 0.7,
			ActionTargetID: "u2", ObjectKind: "person", PrimaryText: "你们有2位共同关注的人",
			DisplayName: "林清越", AvatarURL: "https://static.quwoquan.test/a.png"},
		// 非人对象无需头像，但要有结论句 → 进候选窗。
		{IntersectionID: "place_ok", Dimension: "location", Strength: 0.6,
			ActionTargetID: "e1", ObjectKind: "place", PrimaryText: "1位你关注的人来过这里"},
	}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)

	feed, err := svc.Feed(context.Background(), "viewer1", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	got := map[string]bool{}
	for _, r := range feed {
		got[r.IntersectionID] = true
		if strings.TrimSpace(r.PrimaryText) == "" {
			t.Fatalf("candidate window reason %s missing primaryText", r.IntersectionID)
		}
	}
	if got["no_text"] || got["person_no_avatar"] {
		t.Fatalf("incomplete reasons must not enter candidate window, got %v", got)
	}
	if !got["person_ok"] || !got["place_ok"] {
		t.Fatalf("complete reasons must enter candidate window, got %v", got)
	}
}

func TestIntersectionService_ObjectIntersectionsEmptyObjectID(t *testing.T) {
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(stubSource{}))
	items, err := svc.ObjectIntersections(context.Background(), "viewer1", "", "user", 8)
	if err != nil {
		t.Fatalf("object intersections: %v", err)
	}
	if len(items) != 0 {
		t.Fatalf("want empty for blank objectId, got %d", len(items))
	}
}

// TestEvidenceKindRank_MatchesWP1AppendixA 把 WP1 附录 A（kind → rank 映射清单，
// 交接 WP3 的正式交接物）固化为契约断言：rank 数值与清单同源，防止双方漂移。
// 清单位置：specs/product/2026H1-positioning-refactor/wp-01-intersection-data-and-expression.md 附录 A。
func TestEvidenceKindRank_MatchesWP1AppendixA(t *testing.T) {
	appendixA := map[string]int{
		// rank 10 · 人
		"sharedFollowees": 10, "commonFollower": 10, "commonContact": 10,
		"followeeInObject": 10, "followeeVisited": 10, "followeeViewing": 10,
		"followeeDiscussedThis": 10,
		// rank 20 · 事物
		"coMemberCircle": 20, "sharedCircle": 20, "sameCompany": 20, "sameTeam": 20,
		"sameIndustry": 20, "sharedEntityAttention": 20, "coWishlistedEntity": 20,
		// rank 30 · 地点
		"coVisitedEntity": 30,
		// rank 40 · 内容
		"coCommented": 40, "coSharedContent": 40, "coCreatedContent": 40,
		"sharedDiscussion": 40,
		// rank 50 · 身份
		"sameSchool": 50, "sameDepartment": 50, "sameMajor": 50, "sameCohort": 50,
		"alumni": 50, "alumniHere": 50, "colleagueHere": 50,
		// rank 60 · 兴趣 fact
		"sharedTagSample": 60,
	}
	for kind, want := range appendixA {
		if got := evidenceKindRank(kind, "fact"); got != want {
			t.Fatalf("kind %s rank = %d, appendix A wants %d", kind, got, want)
		}
	}
	// 未知 kind 兜底 rank 500（开放字符串优雅降级，不写死闭集）。
	if got := evidenceKindRank("someFutureKind", "fact"); got != 500 {
		t.Fatalf("unknown kind rank = %d, want 500", got)
	}
	// recommended 点恒为 rank 900，与 kind 无关。
	if got := evidenceKindRank("sharedFollowees", "recommended"); got != 900 {
		t.Fatalf("recommended rank = %d, want 900", got)
	}
}

// ── D：Redis 不可用降级 / 持久兜底 ───────────────────────────────────────────

// TestIntersectionService_MarkVisited_RedisDownPersistsDurable 验证 Redis 宕机时
// 清零仍写入耐久兜底、不向上抛错、发降级指标（写降级不阻断主请求 + 读位不丢）。
func TestIntersectionService_MarkVisited_RedisDownPersistsDurable(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	store := newMemWatermarkStore()
	metrics := newCaptureMetrics()
	svc := NewIntersectionService(
		failingRedisRouter{err: errors.New("redis down")},
		WithIntersectionSource(stubSource{}),
		WithIntersectionWatermarkStore(store),
		WithIntersectionMetrics(metrics),
	)
	fixedNow(svc, now)

	if err := svc.MarkVisited(context.Background(), "viewer1", "identity"); err != nil {
		t.Fatalf("Redis 宕机时清零必须降级返回 nil，得到 %v", err)
	}
	if store.docs["viewer1"]["identity"] != now.Unix() {
		t.Fatalf("清零必须持久到耐久兜底，got %+v", store.docs["viewer1"])
	}
	if metrics.redisDegraded["watermark_write"] == 0 {
		t.Fatalf("Redis 写失败必须发降级指标 watermark_write，got %+v", metrics.redisDegraded)
	}
}

// TestIntersectionService_Watermarks_RedisDownFallsBackToDurable 验证 Redis 读失败时
// 回落耐久兜底（已读位不丢），并发降级指标。
func TestIntersectionService_Watermarks_RedisDownFallsBackToDurable(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	store := newMemWatermarkStore()
	store.docs["viewer1"] = map[string]int64{"identity": now.Add(-time.Hour).Unix()}
	metrics := newCaptureMetrics()
	svc := NewIntersectionService(
		failingRedisRouter{err: errors.New("redis down")},
		WithIntersectionSource(stubSource{}),
		WithIntersectionWatermarkStore(store),
		WithIntersectionMetrics(metrics),
	)
	fixedNow(svc, now)

	wm := svc.watermarks(context.Background(), "viewer1")
	if wm["identity"] != now.Add(-time.Hour).Unix() {
		t.Fatalf("Redis 故障必须回落耐久兜底读位，got %+v", wm)
	}
	if metrics.redisDegraded["watermark_read"] == 0 {
		t.Fatalf("Redis 读失败必须发降级指标 watermark_read，got %+v", metrics.redisDegraded)
	}
}

// TestIntersectionService_Watermarks_RedisFlushRecoversAndWarms 验证 Redis 被 flush
// （可用但为空）时从耐久兜底恢复读位，并回暖 Redis（后续读命中 Redis）。
func TestIntersectionService_Watermarks_RedisFlushRecoversAndWarms(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	router := newTestRouter(t)
	store := newMemWatermarkStore()
	store.docs["viewer1"] = map[string]int64{"content": now.Add(-2 * time.Hour).Unix()}
	svc := NewIntersectionService(
		router,
		WithIntersectionSource(stubSource{}),
		WithIntersectionWatermarkStore(store),
	)
	fixedNow(svc, now)
	ctx := context.Background()

	wm := svc.watermarks(ctx, "viewer1")
	if wm["content"] != now.Add(-2*time.Hour).Unix() {
		t.Fatalf("Redis flush 后必须从耐久兜底恢复读位，got %+v", wm)
	}
	// 回暖：直接查 Redis 应已有该字段（后续热路径命中、不再回落耐久）。
	key := watermarkKey("viewer1")
	all, err := router.ForKey(key).HGetAll(ctx, key)
	if err != nil {
		t.Fatalf("redis hgetall: %v", err)
	}
	if all["wm:content"] == "" {
		t.Fatalf("耐久恢复后必须回暖 Redis 缓存，got %+v", all)
	}
	store.loadCalls = 0
	if wm2 := svc.watermarks(ctx, "viewer1"); wm2["content"] != now.Add(-2*time.Hour).Unix() {
		t.Fatalf("回暖后再读应命中 Redis，got %+v", wm2)
	}
	if store.loadCalls != 0 {
		t.Fatalf("回暖后再读不应再触达耐久兜底，loadCalls=%d", store.loadCalls)
	}
}

// TestIntersectionService_ReportExposure_RedisDownDegrades 验证曝光上报在 Redis 宕机时
// 降级返回 nil（不拖垮 feed），并发降级指标。
func TestIntersectionService_ReportExposure_RedisDownDegrades(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	metrics := newCaptureMetrics()
	svc := NewIntersectionService(
		failingRedisRouter{err: errors.New("redis down")},
		WithIntersectionSource(stubSource{}),
		WithIntersectionMetrics(metrics),
	)
	fixedNow(svc, now)

	if err := svc.ReportExposure(context.Background(), "viewer1", []string{"u1", "u2"}); err != nil {
		t.Fatalf("Redis 宕机时曝光上报必须降级返回 nil，得到 %v", err)
	}
	if metrics.redisDegraded["exposure_write"] == 0 {
		t.Fatalf("Redis 写失败必须发降级指标 exposure_write，got %+v", metrics.redisDegraded)
	}
}

// TestIntersectionService_MarkVisited_DurableErrorSurfaces 验证耐久写失败（真正不可用）
// 仍向上抛错——耐久是真相源，不能静默丢读位。
func TestIntersectionService_MarkVisited_DurableErrorSurfaces(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	svc := NewIntersectionService(
		newTestRouter(t),
		WithIntersectionSource(stubSource{}),
		WithIntersectionWatermarkStore(errWatermarkStore{err: errors.New("mongo down")}),
	)
	fixedNow(svc, now)
	if err := svc.MarkVisited(context.Background(), "viewer1", "identity"); err == nil {
		t.Fatalf("耐久兜底写失败必须向上抛错（真相源不可静默丢失）")
	}
}

// errWatermarkStore 让耐久写恒失败。
type errWatermarkStore struct{ err error }

func (e errWatermarkStore) LoadWatermarks(context.Context, string) (map[string]int64, error) {
	return map[string]int64{}, nil
}
func (e errWatermarkStore) SaveWatermarks(context.Context, string, map[string]int64) error {
	return e.err
}

// TestIntersectionService_ExplainPipelineInstantiatesPrimaryText（WP1·T2）：
// 云侧 Explain 管线按 §17.1 主谓宾模板由结构化 kind+count 实例化 primaryText，
// 禁止回退旧 displayText；secondaryText 罗列跨 kind 辅助说明；连接说明按共同点产出。
func TestIntersectionService_ExplainPipelineInstantiatesPrimaryText(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	src := stubSource{facts: []IntersectionReasonView{
		{
			IntersectionID: "rel", IntersectionClass: "fact", Dimension: "relationship",
			Strength: 0.9, ActionTargetID: "u1", RelationKind: "none",
			// R-ID01：reason 级 displayText 已零兼容删除；primaryText 必须由 kind+count 模板化产出。
			IntersectionPoints: []IntersectionPointView{
				{PointID: "p1", PointClass: "fact", Dimension: "relationship", SourceRef: "sharedFollowees", Label: "共同关注的人", Count: 3, SampleText: "林清越", Visibility: "public"},
				{PointID: "p2", PointClass: "fact", Dimension: "relationship", SourceRef: "sharedCircle", Label: "共同圈子", Count: 2, Visibility: "public"},
			},
		},
	}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)

	feed, err := svc.Feed(context.Background(), "viewer1", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	if len(feed) != 1 {
		t.Fatalf("want 1 reason, got %d", len(feed))
	}
	got := feed[0]
	if got.PrimaryText != "你和林清越等3人共同关注了相同的人" {
		t.Fatalf("primaryText must instantiate sharedFollowees template, got %q", got.PrimaryText)
	}
	if got.RepresentativeActor == nil || got.RepresentativeActor.DisplayName != "林清越" {
		t.Fatalf("representativeActor must come from evidence snapshot, got %+v", got.RepresentativeActor)
	}
	if len(got.ActionHints) == 0 || got.ActionHints[0].ActionKey == "" {
		t.Fatalf("actionHints must be generated from kind registry, got %+v", got.ActionHints)
	}
	if !strings.Contains(got.SecondaryText, "共同圈子") {
		t.Fatalf("secondaryText should enumerate other-kind evidence, got %q", got.SecondaryText)
	}
	if got.ConnectionSummary != "你们已有2个共同点" {
		t.Fatalf("connectionSummary mismatch, got %q", got.ConnectionSummary)
	}
}

func TestIntersectionService_ListFiltersAndPaginates(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	src := stubSource{facts: []IntersectionReasonView{
		{
			IntersectionID: "a", IntersectionClass: "fact", Dimension: "relationship",
			Strength: 0.9, FreshAt: now.Add(-1 * time.Hour).Format(time.RFC3339), TimeBucket: "today",
			IntersectionPoints: []IntersectionPointView{
				{PointID: "a1", PointClass: "fact", Dimension: "relationship", SourceRef: "sharedFollowees", Label: "共同关注的人", Count: 2, SampleText: "林清越", Visibility: "public"},
			},
		},
		{
			IntersectionID: "b", IntersectionClass: "fact", Dimension: "relationship",
			Strength: 0.7, FreshAt: now.Add(-2 * time.Hour).Format(time.RFC3339), TimeBucket: "today",
			IntersectionPoints: []IntersectionPointView{
				{PointID: "b1", PointClass: "fact", Dimension: "relationship", SourceRef: "commonContact", Label: "共同联系人", Count: 1, SampleText: "周屿", Visibility: "public"},
			},
		},
		{
			IntersectionID: "c", IntersectionClass: "fact", Dimension: "location",
			Strength: 0.8, FreshAt: now.Add(-3 * time.Hour).Format(time.RFC3339), TimeBucket: "last7Days",
			IntersectionPoints: []IntersectionPointView{
				{PointID: "c1", PointClass: "fact", Dimension: "location", SourceRef: "followeeVisited", Label: "来过这里", Count: 5, SampleText: "顾南", Visibility: "public"},
			},
		},
	}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)

	page, nextCursor, hasMore, err := svc.List(context.Background(), "viewer1", IntersectionListQuery{
		Dimension:  "relationship",
		TimeBucket: "today",
		Limit:      1,
	})
	if err != nil {
		t.Fatalf("list page 1: %v", err)
	}
	if len(page) != 1 || page[0].IntersectionID != "a" || !hasMore || nextCursor == "" {
		t.Fatalf("unexpected page 1: items=%+v next=%q hasMore=%v", page, nextCursor, hasMore)
	}
	page, _, hasMore, err = svc.List(context.Background(), "viewer1", IntersectionListQuery{
		Dimension:  "relationship",
		TimeBucket: "today",
		Cursor:     nextCursor,
		Limit:      1,
	})
	if err != nil {
		t.Fatalf("list page 2: %v", err)
	}
	if len(page) != 1 || page[0].IntersectionID != "b" || hasMore {
		t.Fatalf("unexpected page 2: items=%+v hasMore=%v", page, hasMore)
	}
	page, _, _, err = svc.List(context.Background(), "viewer1", IntersectionListQuery{
		SourceRef: "followeeVisited",
		Limit:     10,
	})
	if err != nil {
		t.Fatalf("list sourceRef: %v", err)
	}
	if len(page) != 1 || page[0].IntersectionID != "c" {
		t.Fatalf("sourceRef filter mismatch: %+v", page)
	}
}

func TestIntersectionService_ListDedupeBeforeBucketAndPagination(t *testing.T) {
	now := time.Date(2026, 6, 9, 12, 0, 0, 0, time.UTC)
	points := func(prefix, dimension string, count int) []IntersectionPointView {
		out := make([]IntersectionPointView, 0, count)
		for i := 0; i < count; i++ {
			out = append(out, IntersectionPointView{
				PointID:    fmt.Sprintf("%s_%d", prefix, i),
				PointClass: "fact",
				Dimension:  dimension,
				Visibility: "public",
			})
		}
		return out
	}
	dupe := func(id string, strength float64, bucket string, anchor float64, total int) IntersectionReasonView {
		return IntersectionReasonView{
			IntersectionID:     id,
			IntersectionClass:  "fact",
			Dimension:          "relationship",
			Kind:               "sharedFollowees",
			ObjectKind:         "person",
			ActionTargetID:     "u_same",
			Strength:           strength,
			TimeBucket:         bucket,
			AnchorUserWeight:   anchor,
			IntersectionPoints: points(id, "relationship", total),
			PrimaryText:        "你和林清越等8位用户都关注「胶片摄影」",
			FreshAt:            now.Add(-time.Hour).Format(time.RFC3339),
		}
	}
	src := stubSource{facts: []IntersectionReasonView{
		dupe("low_strength_today", 0.7, "today", 0.9, 9),
		dupe("winner_strength", 0.9, "last7Days", 0.1, 1),
		{
			IntersectionID:     "bucket_today",
			IntersectionClass:  "fact",
			Dimension:          "location",
			Kind:               "coVisitedEntity",
			ObjectKind:         "place",
			ActionTargetID:     "place_today",
			Strength:           0.8,
			TimeBucket:         "today",
			AnchorUserWeight:   0.1,
			IntersectionPoints: points("bucket_today", "location", 1),
			PrimaryText:        "你和王然等3位用户都去过「西湖」",
			FreshAt:            now.Add(-2 * time.Hour).Format(time.RFC3339),
		},
		{
			IntersectionID:     "bucket_last7",
			IntersectionClass:  "fact",
			Dimension:          "location",
			Kind:               "coVisitedEntity",
			ObjectKind:         "place",
			ActionTargetID:     "place_last7",
			Strength:           0.8,
			TimeBucket:         "last7Days",
			AnchorUserWeight:   0.9,
			IntersectionPoints: points("bucket_last7", "location", 10),
			PrimaryText:        "你和6位用户都去过「798艺术区」",
			FreshAt:            now.Add(-72 * time.Hour).Format(time.RFC3339),
		},
		{
			IntersectionID:     "anchor_winner",
			IntersectionClass:  "fact",
			Dimension:          "content",
			Kind:               "coCommented",
			ObjectKind:         "circle",
			ActionTargetID:     "circle_anchor",
			Strength:           0.6,
			TimeBucket:         "yesterday",
			AnchorUserWeight:   0.8,
			IntersectionPoints: points("anchor_winner", "content", 2),
			PrimaryText:        "你和周屿等4位用户参与了「周末街拍讨论」",
			FreshAt:            now.Add(-26 * time.Hour).Format(time.RFC3339),
		},
		{
			IntersectionID:     "count_winner",
			IntersectionClass:  "fact",
			Dimension:          "content",
			Kind:               "coCommented",
			ObjectKind:         "circle",
			ActionTargetID:     "circle_count",
			Strength:           0.6,
			TimeBucket:         "yesterday",
			AnchorUserWeight:   0.8,
			IntersectionPoints: points("count_winner", "content", 8),
			PrimaryText:        "你和8位用户参与了「胶片相机推荐」讨论",
			FreshAt:            now.Add(-28 * time.Hour).Format(time.RFC3339),
		},
	}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)

	page, nextCursor, hasMore, err := svc.List(context.Background(), "viewer1", IntersectionListQuery{Limit: 3})
	if err != nil {
		t.Fatalf("list page 1: %v", err)
	}
	if !hasMore || strings.TrimSpace(nextCursor) == "" {
		t.Fatalf("expected pagination after dedupe, next=%q hasMore=%v", nextCursor, hasMore)
	}
	gotIDs := []string{page[0].IntersectionID, page[1].IntersectionID, page[2].IntersectionID}
	wantIDs := []string{"winner_strength", "bucket_today", "bucket_last7"}
	for i := range wantIDs {
		if gotIDs[i] != wantIDs[i] {
			t.Fatalf("page 1 order mismatch: got %v want %v", gotIDs, wantIDs)
		}
	}
	if page[0].DedupeKey != "viewer1:u_same:person:sharedFollowees" {
		t.Fatalf("dedupeKey must be returned from canonical tuple, got %q", page[0].DedupeKey)
	}
	for _, item := range page {
		if item.IntersectionID == "low_strength_today" {
			t.Fatalf("dedupe must keep stronger duplicate, got %+v", page)
		}
	}

	page2, _, hasMore, err := svc.List(context.Background(), "viewer1", IntersectionListQuery{
		Cursor: nextCursor,
		Limit:  3,
	})
	if err != nil {
		t.Fatalf("list page 2: %v", err)
	}
	if hasMore {
		t.Fatalf("unexpected third page: %+v", page2)
	}
	if len(page2) != 2 || page2[0].IntersectionID != "count_winner" || page2[1].IntersectionID != "anchor_winner" {
		t.Fatalf("page 2 order/count mismatch: %+v", page2)
	}
}

func TestIntersectionService_ListDerivesExclusiveTimeBuckets(t *testing.T) {
	now := time.Date(2026, 6, 29, 12, 0, 0, 0, time.UTC)
	item := func(id string, fresh time.Time) IntersectionReasonView {
		return IntersectionReasonView{
			IntersectionID:    id,
			IntersectionClass: "fact",
			Dimension:         "location",
			Kind:              "coVisitedEntity",
			ObjectKind:        "place",
			ActionTargetID:    id,
			Strength:          0.5,
			PrimaryText:       "你和3位用户都去过「西湖」",
			FreshAt:           fresh.Format(time.RFC3339),
		}
	}
	src := stubSource{facts: []IntersectionReasonView{
		item("today", now.Add(-time.Hour)),
		item("yesterday", now.AddDate(0, 0, -1)),
		item("last7", now.AddDate(0, 0, -3)),
		item("this_month", now.AddDate(0, 0, -10)),
		item("last_month", time.Date(2026, 5, 20, 9, 0, 0, 0, time.UTC)),
	}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)

	page, _, _, err := svc.List(context.Background(), "viewer1", IntersectionListQuery{Limit: 10})
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	got := map[string]string{}
	for _, item := range page {
		got[item.IntersectionID] = item.TimeBucket
	}
	want := map[string]string{
		"today":      "today",
		"yesterday":  "yesterday",
		"last7":      "last7Days",
		"this_month": "thisMonth",
		"last_month": "lastMonth",
	}
	for id, bucket := range want {
		if got[id] != bucket {
			t.Fatalf("%s bucket = %q, want %q; all=%v", id, got[id], bucket, got)
		}
	}
}

// TestIntersectionService_AffinityChannelLabeled（WP1·T2）：概率通道必须分通道——
// affinity reason 带 confidenceLabel 与 modelReasonBucket，fact 不得带 confidenceLabel。
func TestIntersectionService_AffinityChannelLabeled(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	src := stubSource{
		facts: []IntersectionReasonView{
			{
				IntersectionID: "fact1", IntersectionClass: "fact", Dimension: "relationship",
				Strength: 0.9, ActionTargetID: "u1", RelationKind: "none",
				IntersectionPoints: []IntersectionPointView{
					{PointID: "f1", PointClass: "fact", Dimension: "relationship", SourceRef: "sharedFollowees", Label: "共同关注的人", Count: 2, Visibility: "public"},
				},
			},
		},
		affinities: []IntersectionReasonView{
			{
				IntersectionID: "aff", IntersectionClass: "affinity", Dimension: "content",
				Strength: 0.8, ActionTargetID: "c1", Source: "social_circle",
				IntersectionPoints: []IntersectionPointView{
					{PointID: "a1", PointClass: "recommended", Dimension: "content", SourceRef: "sharedCircle", Label: "圈子热看", Visibility: "public"},
				},
			},
		},
	}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)

	feed, err := svc.Feed(context.Background(), "viewer1", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	byID := map[string]IntersectionReasonView{}
	for _, r := range feed {
		byID[r.IntersectionID] = r
	}
	fact, ok := byID["fact1"]
	if !ok {
		t.Fatalf("fact reason missing, got %v", feed)
	}
	if strings.TrimSpace(fact.ConfidenceLabel) != "" {
		t.Fatalf("fact reason must not carry confidenceLabel, got %q", fact.ConfidenceLabel)
	}
	aff, ok := byID["aff"]
	if !ok {
		t.Fatalf("affinity reason missing, got %v", feed)
	}
	if strings.TrimSpace(aff.PrimaryText) == "" {
		t.Fatalf("affinity primaryText must be produced")
	}
	if strings.TrimSpace(aff.ConfidenceLabel) == "" {
		t.Fatalf("affinity must carry confidenceLabel (channel separation)")
	}
	if !strings.HasPrefix(aff.ModelReasonBucket, "affinity:") {
		t.Fatalf("affinity must carry modelReasonBucket, got %q", aff.ModelReasonBucket)
	}
}
