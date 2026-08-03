package intersection_test

import (
	"context"
	"strings"
	"testing"
	"time"

	. "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
)

// commonFollower（共同粉丝）与 sharedFollowees（共同关注的人）是同一条关注边的两个
// 方向，结论句的关系限定语必须相反：共同粉丝是「关注你的人」，套用「你关注的人」
// 会把关系方向说反，属于用错误主语伪造社交事实。
func TestExplainCommonFollowerKeepsFollowDirection(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	reason := IntersectionReasonView{
		IntersectionID:    "rel_followers",
		IntersectionClass: "fact",
		Dimension:         "relationship",
		ObjectKind:        "person",
		ActionTargetID:    "u_other",
		DisplayName:       "陆衡",
		Strength:          0.8,
		RelationKind:      "none",
		FreshAt:           now.Add(-time.Hour).Format(time.RFC3339),
		IntersectionPoints: []IntersectionPointView{
			{
				PointID: "p_followers", PointClass: "fact", Dimension: "relationship",
				SourceRef: "commonFollower", Label: "共同粉丝", Count: 3,
				SampleText: "林清越", Visibility: "public",
			},
		},
	}
	src := stubSource{facts: []IntersectionReasonView{reason}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)

	feed, err := svc.Feed(context.Background(), "u_viewer", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	if len(feed) != 1 {
		t.Fatalf("want 1 reason, got %d", len(feed))
	}
	got := feed[0]
	if got.PrimaryText != "关注你的人林清越等3人也关注了「陆衡」" {
		t.Fatalf("commonFollower statement must state the follower direction, got %q", got.PrimaryText)
	}
	if strings.Contains(got.PrimaryText, "你关注的人林清越") {
		t.Fatalf("common followers are not the viewer's followees: %q", got.PrimaryText)
	}

	// span 拼回不变量：结论句必须能由 spans 无损重建（端侧只读直出）。
	var rebuilt strings.Builder
	for _, span := range got.PrimarySpans {
		rebuilt.WriteString(span.Text)
	}
	if rebuilt.String() != got.PrimaryText {
		t.Fatalf("join(primarySpans) must equal primaryText, got %q vs %q", rebuilt.String(), got.PrimaryText)
	}
}
