package intersection_test

import (
	"context"
	"errors"
	"fmt"
	. "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
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
	svc.SetClock(func() time.Time { return ts })
}

func displayReadyFactReason(
	id string,
	dimension string,
	sourceRef string,
	targetID string,
	objectKind string,
	displayName string,
	count int,
	strength float64,
) IntersectionReasonView {
	if count <= 0 {
		count = 1
	}
	actorEvidence := make([]IntersectionActorEvidenceView, 0, count)
	for i := 0; i < count; i++ {
		actorID := "actor_" + id
		if i > 0 {
			actorID = fmt.Sprintf("actor_%s_%d", id, i+1)
		}
		display := "林清越"
		if i > 0 {
			display = fmt.Sprintf("同行样本%d", i+1)
		}
		actorEvidence = append(actorEvidence, IntersectionActorEvidenceView{
			ActorID:       actorID,
			DisplayName:   display,
			AvatarURL:     "https://static.quwoquan.test/" + actorID + ".png",
			RelationLabel: "你关注的人",
			SourceRef:     sourceRef,
			PrivacyState:  "visible",
			Target: &IntersectionTargetView{
				ObjectType: "user",
				ObjectID:   actorID,
				ObjectKind: "person",
				RouteID:    "userProfile",
			},
		})
	}
	return IntersectionReasonView{
		IntersectionID:            id,
		IntersectionClass:         "fact",
		Dimension:                 dimension,
		Strength:                  strength,
		ActionTargetID:            targetID,
		ObjectKind:                objectKind,
		DisplayName:               displayName,
		AvatarURL:                 "https://static.quwoquan.test/" + id + ".png",
		ActorEvidenceTotalCount:   count,
		ActorEvidenceCompleteness: "complete",
		ActorEvidence:             actorEvidence,
		IntersectionPoints: []IntersectionPointView{
			{
				PointID:     id + "_point",
				PointClass:  "fact",
				Dimension:   dimension,
				SourceRef:   sourceRef,
				Visibility:  "public",
				Count:       count,
				SampleText:  "林清越",
				DisplayText: displayName,
			},
		},
	}
}

// withDisplayStatement 把合成 fixture 补齐到「读模型预物化 reason」的真实可下发形态
// （单轨合同：List/Summary 淘汰展示不完备 reason，排序/分桶 fixture 必须展示完备）：
// 预置 primaryText 按对象名切出 object span（target=reason 对象），并补代表人锚点。
func withDisplayStatement(
	r IntersectionReasonView,
	objectText string,
	actorName string,
	actorID string,
) IntersectionReasonView {
	r.RepresentativeActor = &IntersectionRepresentativeActorView{
		ActorID:       actorID,
		DisplayName:   actorName,
		RelationLabel: "你关注的人",
		PrivacyState:  "visible",
		Target: &IntersectionTargetView{
			ObjectType: "user",
			ObjectID:   actorID,
			ObjectKind: "person",
			RouteID:    "userProfile",
		},
	}
	if r.ActorEvidenceTotalCount == 0 {
		r.ActorEvidenceTotalCount = 1
	}
	if r.ActorEvidenceCompleteness == "" {
		r.ActorEvidenceCompleteness = "complete"
	}
	objectType := "homepage"
	switch strings.TrimSpace(r.ObjectKind) {
	case "person":
		objectType = "user"
	case "circle":
		objectType = "circle"
	case "content":
		objectType = "post"
	}
	target := &IntersectionTargetView{
		ObjectType: objectType,
		ObjectID:   strings.TrimSpace(r.ActionTargetID),
		ObjectKind: strings.TrimSpace(r.ObjectKind),
		RouteID:    "homepageDetail",
	}
	text := strings.TrimSpace(r.PrimaryText)
	idx := strings.Index(text, objectText)
	if idx < 0 {
		return r
	}
	spans := make([]IntersectionTextSpanView, 0, 3)
	if idx > 0 {
		spans = append(spans, IntersectionTextSpanView{Text: text[:idx], Role: "plain"})
	}
	spans = append(spans, IntersectionTextSpanView{Text: objectText, Role: "object", Target: target})
	if tail := text[idx+len(objectText):]; tail != "" {
		spans = append(spans, IntersectionTextSpanView{Text: tail, Role: "plain"})
	}
	r.PrimarySpans = spans
	return r
}

func displayReadyAffinityReason(
	id string,
	dimension string,
	sourceRef string,
	targetID string,
	objectKind string,
	displayName string,
	strength float64,
) IntersectionReasonView {
	r := displayReadyFactReason(id, dimension, sourceRef, targetID, objectKind, displayName, 1, strength)
	r.IntersectionClass = "affinity"
	r.IntersectionPoints[0].PointClass = "recommended"
	r.Source = sourceRef
	return r
}

func TestIntersectionService_SummaryNewCountAndVisitClears(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	// Summary 只计可展示 reason，fixture 必须是展示完备形态（R12：
	// fixture 对齐真实可下发行为，裸 reason 会被 display_incomplete 淘汰）。
	fresh := func(r IntersectionReasonView, at time.Time) IntersectionReasonView {
		r.FreshAt = at.Format(time.RFC3339)
		return r
	}
	src := stubSource{facts: []IntersectionReasonView{
		fresh(displayReadyFactReason("a", "identity", "sharedFollowees", "u1", "person", "陆衡", 2, 0.9), now.Add(-time.Hour)),
		fresh(displayReadyFactReason("b", "identity", "sharedFollowees", "u2", "person", "沈行舟", 2, 0.8), now.Add(-2*time.Hour)),
		fresh(displayReadyFactReason("c", "content", "coCommented", "p1", "content", "摄影路线", 2, 0.7), now.Add(-time.Hour)),
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
		displayReadyFactReason("a", "identity", "sharedFollowees", "u1", "person", "陆衡", 8, 0.9),
		displayReadyFactReason("b", "content", "coCommented", "p1", "content", "摄影路线", 2, 0.8),
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

func TestIntersectionService_NegativeFeedbackFiltersFromFeed(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	src := stubSource{facts: []IntersectionReasonView{
		displayReadyFactReason("a", "relationship", "commonFollower", "u1", "person", "陆衡", 2, 0.9),
		displayReadyFactReason("b", "content", "coCommented", "p1", "content", "摄影路线", 2, 0.8),
	}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)
	ctx := context.Background()

	feed, err := svc.Feed(ctx, "viewer1", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	if len(feed) != 2 {
		t.Fatalf("want 2 before negative feedback, got %d", len(feed))
	}

	// 用户对 subject u1 显式「不感兴趣」→ 负反馈冷却窗口内 Feed 过滤该 subject（不再推荐），
	// 区别于曝光冷却（seen 仅降权保留）。
	if err := svc.ReportNegativeFeedback(ctx, "viewer1", "u1", "notInterested"); err != nil {
		t.Fatalf("report negative feedback: %v", err)
	}
	feed2, err := svc.Feed(ctx, "viewer1", "recommend", 10)
	if err != nil {
		t.Fatalf("feed2: %v", err)
	}
	if len(feed2) != 1 {
		t.Fatalf("want 1 after negative feedback filter, got %+v", feed2)
	}
	if feed2[0].ActionTargetID != "p1" {
		t.Fatalf("negative subject u1 must be filtered out, got %+v", feed2)
	}
}

func TestIntersectionService_NegativeFeedbackCooldownExpires(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	src := stubSource{facts: []IntersectionReasonView{
		displayReadyFactReason("a", "relationship", "commonFollower", "u1", "person", "陆衡", 2, 0.9),
	}}
	svc := NewIntersectionService(
		newTestRouter(t),
		WithIntersectionSource(src),
		WithIntersectionNegativeFeedbackCooldownDays(30),
	)
	fixedNow(svc, now)
	ctx := context.Background()

	if err := svc.ReportNegativeFeedback(ctx, "viewer1", "u1", "dismiss"); err != nil {
		t.Fatalf("report negative feedback: %v", err)
	}
	if feed, err := svc.Feed(ctx, "viewer1", "recommend", 10); err != nil || len(feed) != 0 {
		t.Fatalf("want u1 filtered within cooldown, got feed=%+v err=%v", feed, err)
	}

	// 冷却过期（+31 天）→ 解禁，可再次推荐。
	fixedNow(svc, now.Add(31*24*time.Hour))
	feed, err := svc.Feed(ctx, "viewer1", "recommend", 10)
	if err != nil {
		t.Fatalf("feed after expiry: %v", err)
	}
	if len(feed) != 1 || feed[0].ActionTargetID != "u1" {
		t.Fatalf("want u1 released after cooldown expiry, got %+v", feed)
	}
}

func TestIntersectionService_ReportNegativeFeedback_InvalidInputRejected(t *testing.T) {
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(stubSource{}))
	ctx := context.Background()

	if err := svc.ReportNegativeFeedback(ctx, "viewer1", "", "notInterested"); err == nil {
		t.Fatalf("empty subjectId must be rejected")
	}
	if err := svc.ReportNegativeFeedback(ctx, "", "u1", "notInterested"); err == nil {
		t.Fatalf("empty userId must be rejected")
	}
	// feedbackKind 必须 ∈ registry.feedbackKinds 闭集（端云同源）；非法值拒绝，禁止静默接受。
	if err := svc.ReportNegativeFeedback(ctx, "viewer1", "u1", "bogus_kind"); err == nil {
		t.Fatalf("invalid feedbackKind must be rejected")
	}
	if err := svc.ReportNegativeFeedback(ctx, "viewer1", "u1", "leaveCircle"); err != nil {
		t.Fatalf("valid closed-set feedbackKind must be accepted, got %v", err)
	}
}

func TestIntersectionService_ReportNegativeFeedback_RedisDownDegrades(t *testing.T) {
	svc := NewIntersectionService(
		failingRedisRouter{err: errors.New("redis down")},
		WithIntersectionSource(stubSource{}),
	)
	// Redis 不可用：合法负反馈上报降级返回 nil（不阻断上游批处理），非法输入仍先行拒绝。
	if err := svc.ReportNegativeFeedback(context.Background(), "viewer1", "u1", "rejectGreeting"); err != nil {
		t.Fatalf("redis down should degrade to nil, got %v", err)
	}
}

func TestIntersectionService_PointSummaryDerivedFromVisiblePoints(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	src := stubSource{facts: []IntersectionReasonView{
		{
			IntersectionID:            "multi",
			IntersectionClass:         "fact",
			Dimension:                 "relationship",
			Strength:                  0.8,
			FreshAt:                   now.Add(-time.Hour).Format(time.RFC3339),
			ActionTargetID:            "u1",
			ObjectKind:                "person",
			DisplayName:               "陆衡",
			ActorEvidenceTotalCount:   2,
			ActorEvidenceCompleteness: "complete",
			ActorEvidence: []IntersectionActorEvidenceView{
				{
					ActorID:       "actor_multi",
					DisplayName:   "林清越",
					RelationLabel: "你关注的人",
					SourceRef:     "sharedFollowees",
					PrivacyState:  "visible",
					Target: &IntersectionTargetView{
						ObjectType: "user",
						ObjectID:   "actor_multi",
						ObjectKind: "person",
						RouteID:    "userProfile",
					},
				},
				{
					ActorID:       "actor_multi_2",
					DisplayName:   "同行样本2",
					RelationLabel: "你关注的人",
					SourceRef:     "sharedFollowees",
					PrivacyState:  "visible",
					Target: &IntersectionTargetView{
						ObjectType: "user",
						ObjectID:   "actor_multi_2",
						ObjectKind: "person",
						RouteID:    "userProfile",
					},
				},
			},
			IntersectionPoints: []IntersectionPointView{
				{PointID: "p1", PointClass: "fact", Dimension: "relationship", SourceRef: "sharedFollowees", DisplayText: "共同关注的人", Count: 2, Visibility: "public"},
				{PointID: "p2", PointClass: "recommended", Dimension: "interest", SourceRef: "sharedTagSample", DisplayText: "摄影内容相似", Visibility: "public"},
				{PointID: "p3", PointClass: "fact", Dimension: "relationship", SourceRef: "sharedFollowees", DisplayText: "隐藏证据", Visibility: "hidden"},
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
			displayReadyFactReason("f1", "identity", "sharedFollowees", "u1", "person", "陆衡", 8, 0.5),
			func() IntersectionReasonView {
				r := displayReadyFactReason("stale", "content", "coCommented", "u9", "content", "旧内容", 3, 0.99)
				r.ExpiresAt = now.Add(-time.Hour).Format(time.RFC3339)
				return r
			}(),
		},
		affinities: []IntersectionReasonView{
			displayReadyAffinityReason("p1", "interest", "sharedCircle", "u2", "content", "摄影内容", 0.95),
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
		displayReadyFactReason("a", "identity", "sharedFollowees", "u1", "person", "陆衡", 8, 0.9),
		displayReadyFactReason("b", "content", "coCommented", "u2", "content", "摄影路线", 2, 0.8),
		displayReadyFactReason("c", "relationship", "commonFollower", "u3", "person", "周屿", 4, 0.7),
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
	reason := displayReadyFactReason(
		"objix_user_u_lin",
		"relationship",
		"sharedFollowees",
		"u_lin",
		"person",
		"林清越",
		4,
		0.9,
	)
	reason.RelationObjectID = "u_lin"
	reason.IntersectionPoints = []IntersectionPointView{
		{PointID: "p_content", PointClass: "fact", Dimension: "content", SourceRef: "coCommented", Label: "共同讨论过", DisplayText: "共同讨论过", Count: 3, Visibility: "public"},
		{PointID: "p_aff", PointClass: "recommended", Dimension: "interest", SourceRef: "affinity", Label: "可能合得来", DisplayText: "可能合得来", Visibility: "public"},
		{PointID: "p_friend", PointClass: "fact", Dimension: "relationship", SourceRef: "sharedFollowees", Label: "共同关注的人", DisplayText: "共同关注的人", Count: 4, Visibility: "public"},
	}
	src := stubSource{object: []IntersectionReasonView{reason}}
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
		// 人级但只有匿名代表人 → 不得进候选窗。
		{IntersectionID: "person_no_actor", Dimension: "relationship", Strength: 0.8,
			ActionTargetID: "u1", ObjectKind: "person", DisplayName: "一位用户",
			IntersectionPoints: []IntersectionPointView{{PointID: "p_bad", PointClass: "fact", Dimension: "relationship", SourceRef: "commonFollower", Count: 3, Visibility: "public"}}},
		// 人级且展示证据完备 → 进候选窗。
		displayReadyFactReason("person_ok", "relationship", "commonFollower", "u2", "person", "林清越", 2, 0.7),
		// 非人对象也要有结论句与可导航对象 → 进候选窗。
		displayReadyFactReason("place_ok", "location", "coWishlistedEntity", "e1", "place", "横竖影像馆取景地", 1, 0.6),
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
	if got["no_text"] || got["person_no_actor"] {
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

// TestEvidenceKindRank_MatchesCanonicalRegistry 固化当前 canonical kind 的排序口径。
func TestEvidenceKindRank_MatchesCanonicalRegistry(t *testing.T) {
	wantByKind := map[string]int{
		"sharedFollowees": 10, "commonFollower": 10,
		"followeeInObject": 10, "followeeVisited": 10, "followeeViewedObject": 10,
		"followeeViewing":       10,
		"followeeDiscussedThis": 10,
		"sharedCircle":          20,
		"sameIndustry":          20, "sharedEntityAttention": 20, "coWishlistedEntity": 20,
		"coVisitedEntity": 30,
		"coCommented":     40, "coSharedContent": 40,
		"sharedTagSample": 60,
		"coLiked":         70,
	}
	for kind, want := range wantByKind {
		if got := EvidenceKindRank(kind, "fact"); got != want {
			t.Fatalf("kind %s rank = %d, registry wants %d", kind, got, want)
		}
	}
	// 未知 kind 兜底 rank 500（开放字符串优雅降级，不写死闭集）。
	if got := EvidenceKindRank("someFutureKind", "fact"); got != 500 {
		t.Fatalf("unknown kind rank = %d, want 500", got)
	}
	// recommended 点恒为 rank 900，与 kind 无关。
	if got := EvidenceKindRank("sharedFollowees", "recommended"); got != 900 {
		t.Fatalf("recommended rank = %d, want 900", got)
	}
}

func TestIntersectionService_RepresentativeActorPrefersClosestRelationship(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	src := stubSource{facts: []IntersectionReasonView{
		{
			IntersectionID: "rel_priority", IntersectionClass: "fact", Dimension: "relationship",
			Strength: 0.92, ActionTargetID: "u_priority", ObjectKind: "person", DisplayName: "陆衡", RelationKind: "none",
			IntersectionPoints: []IntersectionPointView{
				{PointID: "circle", PointClass: "fact", Dimension: "relationship", SourceRef: "sharedCircle", Label: "共同圈子", Count: 12, SampleText: "城市漫游圈", Visibility: "public"},
				{PointID: "followee", PointClass: "fact", Dimension: "relationship", SourceRef: "sharedFollowees", Label: "共同关注的人", Count: 9, SampleText: "周屿", Visibility: "public"},
				{PointID: "contact", PointClass: "fact", Dimension: "relationship", SourceRef: "commonFollower", Label: "共同关注者", Count: 8, SampleText: "林清越", Visibility: "public"},
				{PointID: "content", PointClass: "fact", Dimension: "content", SourceRef: "coCommented", Label: "共同讨论", Count: 20, SampleText: "黄金投资圈", Visibility: "public"},
			},
			ActorEvidence: []IntersectionActorEvidenceView{
				{
					ActorID:       "u_lin",
					DisplayName:   "林清越",
					RelationLabel: "关注你的人",
					SourceRef:     "commonFollower",
				},
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
	if got.RepresentativeActor == nil || got.RepresentativeActor.DisplayName != "林清越" {
		t.Fatalf("representativeActor should prefer closest contact evidence, got %+v", got.RepresentativeActor)
	}
	if got.RepresentativeActor.EvidenceRank != 10 {
		t.Fatalf("closest evidence rank = %d, want 10", got.RepresentativeActor.EvidenceRank)
	}
	if got.PrimaryText != "关注你的人林清越等9人也关注了「陆衡」" {
		t.Fatalf("primaryText should use closest representative evidence, got %q", got.PrimaryText)
	}
}

func TestIntersectionService_ActorEvidenceContractHydratesCompleteList(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	src := stubSource{facts: []IntersectionReasonView{
		{
			IntersectionID: "actor_evidence", IntersectionClass: "fact", Dimension: "relationship",
			Strength: 0.92, ActionTargetID: "post_1", ObjectKind: "content", DisplayName: "川西雪山和校园摄影路线",
			PointSummarySnapshotID: "snap_actor_evidence",
			PrimaryText:            "关注你的人林清越等 2 人：1赞 1评",
			IntersectionPoints: []IntersectionPointView{
				{PointID: "actors", PointClass: "fact", Dimension: "content", SourceRef: "coCommented", Label: "共同评论", Count: 2, SampleText: "林清越、周屿", Visibility: "public"},
			},
			ActorEvidence: []IntersectionActorEvidenceView{
				{
					ActorID:           "u_lin",
					DisplayName:       "林清越",
					RelationLabel:     "关注你的人",
					RelationSourceRef: "follower",
					SourcePointID:     "actors",
					SourceRef:         "commonFollower",
					ActionSummaryText: "点赞了这条记录",
					LikeCount:         1,
				},
				{
					ActorID:           "u_zhou",
					DisplayName:       "周屿",
					RelationLabel:     "你关注的人",
					RelationSourceRef: "followee",
					SourcePointID:     "actors",
					SourceRef:         "sharedFollowees",
					ActionSummaryText: "评论了这条记录",
					CommentCount:      1,
				},
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
	if got.ActorEvidenceTotalCount != 2 {
		t.Fatalf("actor evidence total = %d, want 2", got.ActorEvidenceTotalCount)
	}
	if got.ActorEvidenceCompleteness != "complete" {
		t.Fatalf("actor evidence completeness = %q, want complete", got.ActorEvidenceCompleteness)
	}
	if len(got.ActorEvidence) != 2 {
		t.Fatalf("actor evidence len = %d, want 2", len(got.ActorEvidence))
	}
	first := got.ActorEvidence[0]
	if first.RelationLabel != "关注你的人" || first.ActionSummaryText != "点赞了这条记录" {
		t.Fatalf("first actor evidence should keep source/action, got %+v", first)
	}
	if first.EvidenceRank != 10 {
		t.Fatalf("first actor evidence rank = %d, want 10", first.EvidenceRank)
	}
	if first.SortKey != 1 {
		t.Fatalf("first actor sortKey = %d, want 1", first.SortKey)
	}
	if first.SnapshotVersion != "snap_actor_evidence" {
		t.Fatalf("first actor snapshot = %q, want snap_actor_evidence", first.SnapshotVersion)
	}
	if first.Target == nil || first.Target.ObjectID != "u_lin" || first.Target.RouteID != "userProfile" {
		t.Fatalf("first actor target should point to user profile, got %+v", first.Target)
	}
	if got.PrimaryText != "关注你的人林清越等2人赞过和评论过《川西雪山和校园摄影路线》" {
		t.Fatalf("bad preseeded raw stats text must be recomputed into SVO, got %q", got.PrimaryText)
	}
	if JoinedSpanText(got.PrimarySpans) != got.PrimaryText {
		t.Fatalf("primary spans must join back to primaryText, spans=%+v text=%q", got.PrimarySpans, got.PrimaryText)
	}
}

func TestIntersectionDisplayStatementRecomputesBadRawStatsText(t *testing.T) {
	raw := IntersectionReasonView{
		IntersectionID:            "display_contract",
		IntersectionClass:         "fact",
		Dimension:                 "content",
		Strength:                  0.92,
		ActionTargetID:            "post_1",
		ObjectKind:                "content",
		DisplayName:               "川西雪山和校园摄影路线",
		PointSummarySnapshotID:    "snap_display_contract",
		PrimaryText:               "联系人林清越等 2 人：1赞 1评",
		ActorEvidenceTotalCount:   2,
		ActorEvidenceCompleteness: "complete",
		IntersectionPoints: []IntersectionPointView{
			{PointID: "actors", PointClass: "fact", Dimension: "content", SourceRef: "coCommented", Label: "共同评论", Count: 2, SampleText: "林清越、周屿", Visibility: "public"},
		},
		ActorEvidence: []IntersectionActorEvidenceView{
			{
				ActorID:           "u_lin",
				DisplayName:       "林清越",
				RelationLabel:     "联系人",
				RelationSourceRef: "contact",
				SourcePointID:     "actors",
				SourceRef:         "commonFollower",
				ActionSummaryText: "点赞了这条记录",
				LikeCount:         1,
			},
			{
				ActorID:           "u_zhou",
				DisplayName:       "周屿",
				RelationLabel:     "你关注的人",
				RelationSourceRef: "followee",
				SourcePointID:     "actors",
				SourceRef:         "sharedFollowees",
				ActionSummaryText: "评论了这条记录",
				CommentCount:      1,
			},
		},
	}
	got := HydratePointSummary(raw)

	if got.PrimaryText != "联系人林清越等2人赞过和评论过《川西雪山和校园摄影路线》" {
		probe := HydrateActorEvidenceContract(raw)
		anchor, _ := ExplainAnchorPoint(probe)
		probe.RepresentativeActor = RepresentativeActorForReason(probe, anchor)
		probe.PrimaryText = ExplainPrimaryText(probe, anchor)
		probe = HydrateInteractionContract(probe)
		t.Fatalf(
			"primaryText = %q; probeText=%q probeAllowed=%v probeValidate=%v probeJoin=%q spans=%+v actor=%+v target=%+v complete=%q",
			got.PrimaryText,
			probe.PrimaryText,
			DisplayStatementTextAllowed(probe, probe.PrimaryText),
			ValidateDisplayStatement(probe),
			JoinedSpanText(probe.PrimarySpans),
			probe.PrimarySpans,
			probe.RepresentativeActor,
			IntersectionTargetForReason(probe),
			probe.ActorEvidenceCompleteness,
		)
	}
	if !ValidateDisplayStatement(got) {
		t.Fatalf("expected hydrated display statement to pass validation: text=%q spans=%+v actor=%+v", got.PrimaryText, got.PrimarySpans, got.RepresentativeActor)
	}
}

func TestIntersectionDisplayContextHostImplicitRemovesCurrentPostObject(t *testing.T) {
	raw := IntersectionReasonView{
		IntersectionID:            "display_host_context",
		IntersectionClass:         "fact",
		Dimension:                 "content",
		Strength:                  0.92,
		ActionTargetID:            "post_1",
		ObjectKind:                "content",
		DisplayName:               "川西雪山和校园摄影路线",
		AvatarURL:                 "https://static.quwoquan.test/post_1.jpg",
		PointSummarySnapshotID:    "snap_display_host_context",
		ActorEvidenceTotalCount:   2,
		ActorEvidenceCompleteness: "complete",
		IntersectionPoints: []IntersectionPointView{
			{PointID: "actors", PointClass: "fact", Dimension: "content", SourceRef: "coCommented", Label: "共同评论", Count: 2, SampleText: "林清越、周屿", Visibility: "public"},
		},
		ActorEvidence: []IntersectionActorEvidenceView{
			{
				ActorID:           "u_lin",
				DisplayName:       "林清越",
				RelationLabel:     "联系人",
				RelationSourceRef: "contact",
				SourcePointID:     "actors",
				SourceRef:         "commonFollower",
				ActionSummaryText: "点赞了这条记录",
				LikeCount:         1,
			},
			{
				ActorID:           "u_zhou",
				DisplayName:       "周屿",
				RelationLabel:     "你关注的人",
				RelationSourceRef: "followee",
				SourcePointID:     "actors",
				SourceRef:         "sharedFollowees",
				ActionSummaryText: "评论了这条记录",
				CommentCount:      1,
			},
		},
	}
	explicit := HydratePointSummary(raw)
	host := &IntersectionTargetView{ObjectType: "post", ObjectID: "post_1", ObjectKind: "content", RouteID: "contentDetail"}
	if ValidateDisplayStatementWithContext(explicit, DisplayContext{Surface: DisplaySurfaceFeed, HostTarget: host, Binding: DisplayBindingExplicitLink}) {
		t.Fatalf("explicit_link must reject clickable self-target on host surface: %+v", explicit.PrimarySpans)
	}

	got := ApplyDisplayContext(explicit, DisplayContext{
		Surface:    DisplaySurfaceFeed,
		HostTarget: host,
		Binding:    DisplayBindingHostImplicit,
	})
	if got.DisplayBinding != DisplayBindingHostImplicit {
		t.Fatalf("displayBinding = %q, want host_implicit", got.DisplayBinding)
	}
	if got.PrimaryText != "联系人林清越等2人赞过和评论过" {
		t.Fatalf("host implicit must remove current post object, got %q", got.PrimaryText)
	}
	if !ValidateDisplayStatementWithContext(got, DisplayContext{Surface: DisplaySurfaceFeed, HostTarget: host, Binding: DisplayBindingHostImplicit}) {
		t.Fatalf("host implicit statement should pass validation: text=%q spans=%+v", got.PrimaryText, got.PrimarySpans)
	}
	for _, span := range got.PrimarySpans {
		if span.Target != nil && span.Target.ObjectType == "post" && span.Target.ObjectID == "post_1" {
			t.Fatalf("host implicit must not keep clickable self-target span: %+v", got.PrimarySpans)
		}
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

	wm := svc.Watermarks(context.Background(), "viewer1")
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

	wm := svc.Watermarks(ctx, "viewer1")
	if wm["content"] != now.Add(-2*time.Hour).Unix() {
		t.Fatalf("Redis flush 后必须从耐久兜底恢复读位，got %+v", wm)
	}
	// 回暖：直接查 Redis 应已有该字段（后续热路径命中、不再回落耐久）。
	key := WatermarkKey("viewer1")
	all, err := router.ForKey(key).HGetAll(ctx, key)
	if err != nil {
		t.Fatalf("redis hgetall: %v", err)
	}
	if all["wm:content"] == "" {
		t.Fatalf("耐久恢复后必须回暖 Redis 缓存，got %+v", all)
	}
	store.loadCalls = 0
	if wm2 := svc.Watermarks(ctx, "viewer1"); wm2["content"] != now.Add(-2*time.Hour).Unix() {
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
			Strength: 0.9, ActionTargetID: "u1", RelationKind: "none", DisplayName: "Claude Code",
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
	if got.PrimaryText != "你关注的人林清越等3人也关注了「Claude Code」" {
		t.Fatalf("primaryText must instantiate sharedFollowees template, got %q", got.PrimaryText)
	}
	if got.RepresentativeActor == nil || got.RepresentativeActor.DisplayName != "林清越" {
		t.Fatalf("representativeActor must come from evidence snapshot, got %+v", got.RepresentativeActor)
	}
	if len(got.ActionHints) == 0 || got.ActionHints[0].ActionKey == "" {
		t.Fatalf("actionHints must be generated from kind registry, got %+v", got.ActionHints)
	}
	firstHint := got.ActionHints[0]
	if firstHint.ActionKey != "follow_person" ||
		firstHint.ActionTier != "light" ||
		firstHint.Dispatch != "navigate" {
		t.Fatalf("first actionHint must hydrate actionKeyMeta from generated registry table, got %+v", firstHint)
	}
	if len(firstHint.RequiredGates) != 1 || firstHint.RequiredGates[0] != "login" {
		t.Fatalf("first actionHint requiredGates must come from generated registry table, got %+v", firstHint.RequiredGates)
	}
	if len(got.ActionHints) < 2 {
		t.Fatalf("sharedFollowees should expose multiple actionHints from registry, got %+v", got.ActionHints)
	}
	secondHint := got.ActionHints[1]
	// greet_person 的 dispatch 是 message：按钮文案「打招呼」必须承接到破冰会话，
	// 而不是只跳对方主页（诚实红线，见注册表 actionKeys.greet_person）。
	if secondHint.ActionKey != "greet_person" ||
		secondHint.ActionTier != "light" ||
		secondHint.Dispatch != "message" {
		t.Fatalf("second actionHint must hydrate actionKeyMeta from generated registry table, got %+v", secondHint)
	}
	wantGates := []string{"login", "greetPreference", "blocked"}
	if len(secondHint.RequiredGates) != len(wantGates) {
		t.Fatalf("second actionHint requiredGates mismatch, got %+v want %+v", secondHint.RequiredGates, wantGates)
	}
	for i, want := range wantGates {
		if secondHint.RequiredGates[i] != want {
			t.Fatalf("second actionHint requiredGates[%d] = %q, want %q (all gates=%+v)", i, secondHint.RequiredGates[i], want, secondHint.RequiredGates)
		}
	}
	if !strings.Contains(got.SecondaryText, "共同圈子") {
		t.Fatalf("secondaryText should enumerate other-kind evidence, got %q", got.SecondaryText)
	}
	if got.ConnectionSummary != "你们已有2个共同点" {
		t.Fatalf("connectionSummary mismatch, got %q", got.ConnectionSummary)
	}
}

func TestIntersectionService_ObjectSharedTagSampleVagueSubjectFailsClosed(t *testing.T) {
	cases := []struct {
		name       string
		objectID   string
		objectType string
		objectKind string
		tag        string
	}{
		{
			name:       "homepage",
			objectID:   "homepage_sight_west_lake",
			objectType: "homepage",
			objectKind: "place",
			tag:        "景点",
		},
		{
			name:       "circle",
			objectID:   "circle_photo",
			objectType: "circle",
			objectKind: "circle",
			tag:        "摄影",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			src := stubSource{object: []IntersectionReasonView{{
				IntersectionID:    tc.objectID + "_tags",
				IntersectionClass: "fact",
				Dimension:         "interest",
				ObjectKind:        tc.objectKind,
				RelationObjectID:  tc.objectID,
				ActionType:        "view_object",
				ActionTargetID:    tc.objectID,
				Source:            "tagRef",
				Strength:          0.7,
				IntersectionPoints: []IntersectionPointView{{
					PointID:     tc.objectID + "_tag_1",
					PointClass:  "fact",
					Dimension:   "interest",
					Label:       tc.tag,
					DisplayText: tc.tag,
					SourceRef:   "sharedTagSample",
					Visibility:  "public",
					Count:       1,
					SampleText:  tc.tag,
				}},
			}}}
			svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))

			items, err := svc.ObjectIntersections(context.Background(), "viewer1", tc.objectID, tc.objectType, 8)
			if err != nil {
				t.Fatalf("object intersections: %v", err)
			}
			if len(items) != 0 {
				t.Fatalf("vague sharedTagSample subject must be filtered before delivery, got %+v", items)
			}
		})
	}
}

func TestIntersectionService_ListFiltersAndPaginates(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	// List 只下发展示完备 reason，fixture 用可下发形态（对齐真实读模型输出）。
	fresh := func(r IntersectionReasonView, at time.Time, bucket string) IntersectionReasonView {
		r.FreshAt = at.Format(time.RFC3339)
		r.TimeBucket = bucket
		return r
	}
	c := fresh(displayReadyFactReason("c", "location", "coWishlistedEntity", "homepage_wishlist", "place", "横竖影像馆取景地", 5, 0.8), now.Add(-3*time.Hour), "last7Days")
	src := stubSource{facts: []IntersectionReasonView{
		fresh(displayReadyFactReason("a", "relationship", "sharedFollowees", "u1", "person", "林清越", 2, 0.9), now.Add(-1*time.Hour), "today"),
		fresh(displayReadyFactReason("b", "relationship", "commonFollower", "u2", "person", "周屿", 1, 0.7), now.Add(-2*time.Hour), "today"),
		c,
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
		SourceRef: "coWishlistedEntity",
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
		return withDisplayStatement(IntersectionReasonView{
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
		}, "「胶片摄影」", "林清越", "u_lin")
	}
	src := stubSource{facts: []IntersectionReasonView{
		dupe("low_strength_today", 0.7, "today", 0.9, 9),
		dupe("winner_strength", 0.9, "last7Days", 0.1, 1),
		withDisplayStatement(IntersectionReasonView{
			IntersectionID:     "bucket_today",
			IntersectionClass:  "fact",
			Dimension:          "location",
			Kind:               "coWishlistedEntity",
			ObjectKind:         "place",
			ActionTargetID:     "place_today",
			Strength:           0.8,
			TimeBucket:         "today",
			AnchorUserWeight:   0.1,
			IntersectionPoints: points("bucket_today", "location", 1),
			PrimaryText:        "你和王然等3位用户都想去「西湖」",
			FreshAt:            now.Add(-2 * time.Hour).Format(time.RFC3339),
		}, "「西湖」", "王然", "u_wang"),
		withDisplayStatement(IntersectionReasonView{
			IntersectionID:     "bucket_last7",
			IntersectionClass:  "fact",
			Dimension:          "location",
			Kind:               "coWishlistedEntity",
			ObjectKind:         "place",
			ActionTargetID:     "place_last7",
			Strength:           0.8,
			TimeBucket:         "last7Days",
			AnchorUserWeight:   0.9,
			IntersectionPoints: points("bucket_last7", "location", 10),
			PrimaryText:        "你和6位用户都想去「798艺术区」",
			FreshAt:            now.Add(-72 * time.Hour).Format(time.RFC3339),
		}, "「798艺术区」", "顾南", "u_gu"),
		withDisplayStatement(IntersectionReasonView{
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
		}, "「周末街拍讨论」", "周屿", "u_zhou"),
		withDisplayStatement(IntersectionReasonView{
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
		}, "「胶片相机推荐」", "沈行舟", "u_shen"),
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
		return withDisplayStatement(IntersectionReasonView{
			IntersectionID:    id,
			IntersectionClass: "fact",
			Dimension:         "location",
			Kind:              "coWishlistedEntity",
			ObjectKind:        "place",
			ActionTargetID:    id,
			Strength:          0.5,
			PrimaryText:       "你和3位用户都想去「西湖」",
			FreshAt:           fresh.Format(time.RFC3339),
		}, "「西湖」", "王然", "u_wang")
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
				Strength: 0.9, ActionTargetID: "u1", RelationKind: "none", DisplayName: "Claude Code",
				IntersectionPoints: []IntersectionPointView{
					{PointID: "f1", PointClass: "fact", Dimension: "relationship", SourceRef: "sharedFollowees", Label: "共同关注的人", Count: 2, SampleText: "林清越", Visibility: "public"},
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
	if _, ok := byID["aff"]; ok {
		t.Fatalf("generic affinity text without typed SVO must fail closed, got %v", feed)
	}
}
