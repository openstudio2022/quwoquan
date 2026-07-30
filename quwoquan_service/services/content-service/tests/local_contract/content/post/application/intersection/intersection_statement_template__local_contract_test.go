// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-006
package intersection_test

import (
	"context"
	"strings"
	"testing"
	"time"

	generated "quwoquan_service/services/content-service/generated/content/post"
	. "quwoquan_service/services/content-service/internal/content/post/application/intersection"
)

// 结论句必须由 registry.statementTemplates 渲染：文本、spans、l10nKey 同源，
// 改注册表即可改文案，不得再回到 Go 里按 kind 硬编码中文句式。
func TestStatementTemplateRendersTextSpansAndL10nKey(t *testing.T) {
	now := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	// fixture 形状与 commonFollower 合约测试对齐：只给事实点 + 人名，
	// 让 Explain 管线自己产出 primaryText / spans / l10nKey。
	reason := IntersectionReasonView{
		IntersectionID:    "rel_shared_followees",
		IntersectionClass: "fact",
		Dimension:         "relationship",
		ObjectKind:        "person",
		ActionTargetID:    "u_other",
		DisplayName:       "陆衡",
		Strength:          0.9,
		FreshAt:           now.Add(-time.Hour).Format(time.RFC3339),
		IntersectionPoints: []IntersectionPointView{
			{
				PointID: "p_shared", PointClass: "fact", Dimension: "relationship",
				SourceRef: "sharedFollowees", Label: "共同关注", Count: 3,
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

	form := generated.IntersectionStatementFormByKind["sharedFollowees"]
	if form.L10nKey == "" || form.Template == "" {
		t.Fatalf("sharedFollowees statement template missing from generated table")
	}
	if got.PrimaryTextL10nKey != form.L10nKey {
		t.Fatalf("primaryTextL10nKey=%q want %q; text=%q", got.PrimaryTextL10nKey, form.L10nKey, got.PrimaryText)
	}
	if !strings.Contains(got.PrimaryText, "也关注了") || !strings.Contains(got.PrimaryText, "陆衡") {
		t.Fatalf("template-rendered primaryText drifted: %q", got.PrimaryText)
	}

	var rebuilt strings.Builder
	for _, span := range got.PrimarySpans {
		rebuilt.WriteString(span.Text)
	}
	if rebuilt.String() != got.PrimaryText {
		t.Fatalf("join(primarySpans) must equal primaryText: %q vs %q", rebuilt.String(), got.PrimaryText)
	}
}

func TestStatementTemplateCountedFallbackUsesRegistryCountedForm(t *testing.T) {
	// 容器对象名缺失时走 counted 降级句；模板与 l10nKey 必须来自 registry.counted。
	// 本断言停在 Explain 层：counted 句没有可点 object span，Feed 的 explicit_link
	// 展示合同会继续把它藏掉（§20.4 降级链末级），那是展示完备性的事，不是模板真相源的事。
	reason := IntersectionReasonView{
		IntersectionID:    "rel_shared_circle_counted",
		IntersectionClass: "fact",
		Dimension:         "relationship",
		ObjectKind:        "circle",
		ActionTargetID:    "circle_bucket",
		DisplayName:       "",
		Strength:          0.8,
		IntersectionPoints: []IntersectionPointView{
			{
				PointID: "p_circles", PointClass: "fact", Dimension: "relationship",
				SourceRef: "sharedCircle", Label: "共同圈子", Count: 4,
				SampleText: "林清越", Visibility: "public",
			},
		},
	}
	anchor := reason.IntersectionPoints[0]
	text := ExplainPrimaryText(reason, anchor)
	key := ExplainPrimaryTextL10nKey(reason, anchor)
	form := generated.IntersectionStatementFormByKind["sharedCircle"]
	if form.Counted.L10nKey == "" {
		t.Fatalf("sharedCircle counted template missing")
	}
	if key != form.Counted.L10nKey {
		t.Fatalf("counted l10nKey=%q want %q; text=%q", key, form.Counted.L10nKey, text)
	}
	if !strings.Contains(text, "4") || !strings.Contains(text, "共同圈子") {
		t.Fatalf("counted fallback must carry real anchor count: %q", text)
	}
}

func TestStatementTemplateSlotsClosedSet(t *testing.T) {
	allowed := map[string]struct{}{}
	for _, slot := range generated.IntersectionStatementSlots {
		allowed[slot] = struct{}{}
	}
	if len(allowed) == 0 {
		t.Fatalf("IntersectionStatementSlots empty")
	}
	for kind, form := range generated.IntersectionStatementFormByKind {
		for _, template := range []string{form.Template, form.Counted.Template} {
			for _, slot := range StatementTemplateSlots(template) {
				if _, ok := allowed[slot]; !ok {
					t.Fatalf("%s template uses slot %q outside closed set", kind, slot)
				}
			}
		}
		for name, variant := range form.Variants {
			for _, slot := range StatementTemplateSlots(variant.Template) {
				if _, ok := allowed[slot]; !ok {
					t.Fatalf("%s.%s template uses slot %q outside closed set", kind, name, slot)
				}
			}
		}
	}
}
