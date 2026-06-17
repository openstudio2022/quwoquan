package application

import (
	"context"
	"strings"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

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

// TestIntersectionService_ExplainPipelineInstantiatesPrimaryText（WP1·T2）：
// 云侧 Explain 管线按 §17.1 主谓宾模板由结构化 kind+count 实例化 primaryText，
// 禁止回退旧 displayText；secondaryText 罗列跨 kind 辅助说明；连接说明按共同点产出。
func TestIntersectionService_ExplainPipelineInstantiatesPrimaryText(t *testing.T) {
	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	src := stubSource{facts: []IntersectionReasonView{
		{
			IntersectionID: "rel", IntersectionClass: "fact", Dimension: "relationship",
			Strength: 0.9, ActionTargetID: "u1", RelationKind: "none",
			// 旧 displayText 不应成为结论句来源：primaryText 必须由 kind+count 模板化。
			DisplayText: "共同关注的人",
			IntersectionPoints: []IntersectionPointView{
				{PointID: "p1", PointClass: "fact", Dimension: "relationship", SourceRef: "sharedFollowees", Label: "共同关注的人", Count: 3, Visibility: "public"},
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
	if got.PrimaryText != "你们有3位共同关注的人" {
		t.Fatalf("primaryText must instantiate sharedFollowees template, got %q", got.PrimaryText)
	}
	if !strings.Contains(got.SecondaryText, "共同圈子") {
		t.Fatalf("secondaryText should enumerate other-kind evidence, got %q", got.SecondaryText)
	}
	if got.ConnectionSummary != "你们已有2个共同点" {
		t.Fatalf("connectionSummary mismatch, got %q", got.ConnectionSummary)
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
