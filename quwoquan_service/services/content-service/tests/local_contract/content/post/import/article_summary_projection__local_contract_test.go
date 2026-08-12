package releaseimport_test

import (
	"strings"
	"testing"
	"unicode/utf8"

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	releaseimport "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func TestImportedArticleSummaryProjectionOmitsFrontMatter(t *testing.T) {
	markdown := "---\ntitle: 路线标题\ntemplate: journal\nsummary: 只展示这段用户摘要\n---\n\n# 路线标题\n\n正文不应抢占显式摘要。"
	if got := releaseimport.ProjectImportedArticleSummary(markdown); got != "只展示这段用户摘要" {
		t.Fatalf("summary=%q", got)
	}
}

func TestImportedArticleSummaryProjectionFallsBackToFirstProseParagraph(t *testing.T) {
	markdown := "---\ntitle: 熊猫攻略\ntemplate: journal\n---\n\n# [熊猫基地](/entity/panda)攻略\n\n第一段 [路线建议](/route/one) 会成为首页摘要。\n\n第二段不进入摘要。"
	if got := releaseimport.ProjectImportedArticleSummary(markdown); got != "第一段 路线建议 会成为首页摘要。" {
		t.Fatalf("summary=%q", got)
	}
}

func TestImportedArticleSummaryProjectionStaysWithinPublicFieldLimit(t *testing.T) {
	markdown := "# 标题\n\n" + strings.Repeat("摘要", 180)
	got := releaseimport.ProjectImportedArticleSummary(markdown)
	if count := utf8.RuneCountInString(got); count != contentgenerated.PostPublicationSummaryMaxRunes {
		t.Fatalf(
			"summary rune count=%d, want %d",
			count,
			contentgenerated.PostPublicationSummaryMaxRunes,
		)
	}
	if !strings.HasSuffix(got, "…") {
		t.Fatalf("truncated summary must end with ellipsis: %q", got)
	}
}
