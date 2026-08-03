package intersection_test

import (
	"context"
	"strings"
	"testing"
	"time"

	. "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
)

// sameIndustry 的可证事实只有「双方都声明了同一职业标签」，结论句必须停在「同行」：
// 说成「同事」会把行业相似伪装成组织归属；分类树里没有可证企业实例节点。
func TestExplainSameIndustryStopsAtSameTrade(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	reason := displayReadyFactReason(
		"identity_same_industry", "identity", "sameIndustry", "u_other",
		"person", "陆衡", 1, 0.7,
	)
	reason.FreshAt = now.Add(-time.Hour).Format(time.RFC3339)
	// 身份点的样本文本是共享职业标签本身（宾语），不是人名。
	reason.IntersectionPoints[0].Label = "同行"
	reason.IntersectionPoints[0].SampleText = "摄影师"
	reason.IntersectionPoints[0].DisplayText = "都是摄影师"
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
	if got.PrimaryText != "你和「陆衡」都是摄影师" {
		t.Fatalf("sameIndustry statement drifted: %q", got.PrimaryText)
	}
	if got.PrimaryTextL10nKey != "intersection.statement.same_industry" {
		t.Fatalf("sameIndustry l10nKey drifted: %q", got.PrimaryTextL10nKey)
	}
	for _, forbidden := range []string{"同事", "同一家", "同公司", "同团队"} {
		if strings.Contains(got.PrimaryText, forbidden) {
			t.Fatalf("shared occupation must not imply organisation: %q", got.PrimaryText)
		}
	}

	var rebuilt strings.Builder
	for _, span := range got.PrimarySpans {
		rebuilt.WriteString(span.Text)
	}
	if rebuilt.String() != got.PrimaryText {
		t.Fatalf("join(primarySpans) must equal primaryText: %q vs %q", rebuilt.String(), got.PrimaryText)
	}
}
