package application

import (
	"context"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

type stubSource struct {
	facts      []IntersectionReasonView
	affinities []IntersectionReasonView
}

func (s stubSource) FactReasons(context.Context, string, string) ([]IntersectionReasonView, error) {
	return s.facts, nil
}
func (s stubSource) AffinityReasons(context.Context, string, string) ([]IntersectionReasonView, error) {
	return s.affinities, nil
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
		{IntersectionID: "a", Dimension: "identity", Strength: 0.9, ActionTargetID: "u1"},
		{IntersectionID: "b", Dimension: "content", Strength: 0.8, ActionTargetID: "p1"},
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
			{IntersectionID: "f1", IntersectionClass: "fact", Dimension: "identity", Strength: 0.5, ActionTargetID: "u1"},
			{IntersectionID: "stale", IntersectionClass: "fact", Dimension: "content", Strength: 0.99, ActionTargetID: "u9", ExpiresAt: now.Add(-time.Hour).Format(time.RFC3339)},
		},
		affinities: []IntersectionReasonView{
			{IntersectionID: "p1", IntersectionClass: "affinity", Dimension: "interest", Strength: 0.95, ActionTargetID: "u2"},
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
		{IntersectionID: "a", Dimension: "identity", Strength: 0.9, ActionTargetID: "u1"},
		{IntersectionID: "b", Dimension: "content", Strength: 0.8, ActionTargetID: "u2"},
		{IntersectionID: "c", Dimension: "relationship", Strength: 0.7, ActionTargetID: "u3"},
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
