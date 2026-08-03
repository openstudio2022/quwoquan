package intersection_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
	"testing"
	"time"
)

type captureMetrics struct {
	feedCandidates   map[string]int // class|rankState
	feedFiltered     map[string]int // reason
	exposure         int
	negativeFeedback int
	inboxVisit       map[string]int // dimension
	inboxFiltered    map[string]int // reason
	redisDegraded    map[string]int // op
}

func newCaptureMetrics() *captureMetrics {
	return &captureMetrics{
		feedCandidates: map[string]int{},
		feedFiltered:   map[string]int{},
		inboxVisit:     map[string]int{},
		inboxFiltered:  map[string]int{},
		redisDegraded:  map[string]int{},
	}
}

func (c *captureMetrics) ObserveFeedCandidate(_, class, rankState string) {
	c.feedCandidates[class+"|"+rankState]++
}
func (c *captureMetrics) ObserveFeedFiltered(_, reason string)      { c.feedFiltered[reason]++ }
func (c *captureMetrics) ObserveExposureReported(count int)         { c.exposure += count }
func (c *captureMetrics) ObserveNegativeFeedbackReported(count int) { c.negativeFeedback += count }
func (c *captureMetrics) ObserveInboxVisit(dimension string)        { c.inboxVisit[dimension]++ }
func (c *captureMetrics) ObserveInboxFiltered(reason string)        { c.inboxFiltered[reason]++ }
func (c *captureMetrics) ObserveRedisDegraded(op string)            { c.redisDegraded[op]++ }

// TestIntersectionService_FunnelMetrics 验证业务 SLI 漏斗信号在真实分支上发射：
// Feed 候选/保鲜过滤/展示不完备过滤、ReportExposure 冷却写入、MarkVisited 清零。
func TestIntersectionService_FunnelMetrics(t *testing.T) {
	now := time.Date(2026, 6, 10, 12, 0, 0, 0, time.UTC)
	fresh := now.Add(-time.Hour).Format(time.RFC3339)
	past := now.Add(-time.Hour).Format(time.RFC3339)

	src := stubSource{
		facts: []IntersectionReasonView{
			// 新鲜 + 完备事实候选（sharedFollowees → primaryText）。
			func() IntersectionReasonView {
				r := displayReadyFactReason("f1", "relationship", "sharedFollowees", "u1", "person", "陆衡", 3, 0.9)
				r.FreshAt = fresh
				return r
			}(),
			// 展示不完备：未登记 kind → primaryText 空 → display_incomplete。
			{
				IntersectionID: "inc",
				Dimension:      "interest",
				FreshAt:        fresh,
				IntersectionPoints: []IntersectionPointView{
					{PointID: "pi", SourceRef: "unknownKind", Label: "x", Visibility: "public"},
				},
			},
			// 过保鲜 → stale 过滤。
			{IntersectionID: "s1", Dimension: "content", ExpiresAt: past},
		},
		affinities: []IntersectionReasonView{
			// 概率候选（affinity → primaryText「为你推荐…」）。
			func() IntersectionReasonView {
				r := displayReadyAffinityReason("a1", "interest", "sharedTagSample", "p1", "content", "摄影内容", 0.7)
				r.FreshAt = fresh
				return r
			}(),
		},
	}

	metrics := newCaptureMetrics()
	svc := NewIntersectionService(newTestRouter(t),
		WithIntersectionSource(src),
		WithIntersectionMetrics(metrics),
	)
	fixedNow(svc, now)
	ctx := context.Background()

	if _, err := svc.Feed(ctx, "viewer1", "campus", 10); err != nil {
		t.Fatalf("feed: %v", err)
	}
	if metrics.feedCandidates["fact|fresh"] != 1 {
		t.Fatalf("want 1 fact|fresh candidate, got %d", metrics.feedCandidates["fact|fresh"])
	}
	if metrics.feedCandidates["affinity|fresh"] != 1 {
		t.Fatalf("want 1 affinity|fresh candidate, got %d", metrics.feedCandidates["affinity|fresh"])
	}
	if metrics.feedFiltered["stale"] != 1 {
		t.Fatalf("want 1 stale filtered, got %d", metrics.feedFiltered["stale"])
	}
	if metrics.feedFiltered["display_incomplete"] != 1 {
		t.Fatalf("want 1 display_incomplete filtered, got %d", metrics.feedFiltered["display_incomplete"])
	}

	if err := svc.ReportExposure(ctx, "viewer1", []string{"obj1", "obj2", "  "}); err != nil {
		t.Fatalf("exposure: %v", err)
	}
	if metrics.exposure != 2 {
		t.Fatalf("want 2 exposures reported (trimmed empty dropped), got %d", metrics.exposure)
	}

	if err := svc.MarkVisited(ctx, "viewer1", ""); err != nil {
		t.Fatalf("visit: %v", err)
	}
	// 空维度 → 全部 5 个维度各清零一次。
	for _, d := range []string{"identity", "location", "content", "interest", "relationship"} {
		if metrics.inboxVisit[d] != 1 {
			t.Fatalf("want 1 visit for %s, got %d", d, metrics.inboxVisit[d])
		}
	}
}
