package releaseimport

import (
	"regexp"
	"strings"
	"unicode/utf8"

	"gopkg.in/yaml.v3"

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
)

var markdownInlineLinkPattern = regexp.MustCompile(`\[([^\]]+)\]\([^\)]+\)`)

// ProjectImportedArticleSummary projects article.md into the public feed summary.
// The complete Markdown remains in body/articleMarkdown for the detail reader;
// front matter and the article digest must never become user-visible excerpts.
func ProjectImportedArticleSummary(markdown string) string {
	frontMatter, body := splitArticleFrontMatter(markdown)
	var metadata struct {
		Summary string `yaml:"summary"`
	}
	if frontMatter != "" && yaml.Unmarshal([]byte(frontMatter), &metadata) == nil {
		if summary := strings.TrimSpace(metadata.Summary); summary != "" {
			return truncateArticleSummary(summary)
		}
	}
	return truncateArticleSummary(firstArticleProseParagraph(body))
}

func splitArticleFrontMatter(markdown string) (frontMatter string, body string) {
	normalized := strings.TrimPrefix(
		strings.ReplaceAll(markdown, "\r\n", "\n"),
		"\ufeff",
	)
	lines := strings.Split(normalized, "\n")
	if len(lines) == 0 || strings.TrimSpace(lines[0]) != "---" {
		return "", normalized
	}
	for index := 1; index < len(lines); index++ {
		if strings.TrimSpace(lines[index]) != "---" {
			continue
		}
		return strings.Join(lines[1:index], "\n"), strings.Join(lines[index+1:], "\n")
	}
	// An unterminated header is malformed article source, not visible prose.
	return "", ""
}

func firstArticleProseParagraph(markdown string) string {
	paragraph := make([]string, 0, 4)
	inDirective := false
	for _, rawLine := range strings.Split(markdown, "\n") {
		line := strings.TrimSpace(rawLine)
		if strings.HasPrefix(line, ":::") {
			inDirective = !inDirective
			continue
		}
		if inDirective || strings.HasPrefix(line, "asset://") {
			continue
		}
		if line == "" {
			if len(paragraph) > 0 {
				break
			}
			continue
		}
		if strings.HasPrefix(line, "#") {
			continue
		}
		paragraph = append(paragraph, line)
	}
	plain := strings.Join(paragraph, " ")
	plain = markdownInlineLinkPattern.ReplaceAllString(plain, "$1")
	plain = strings.NewReplacer("**", "", "__", "", "`", "").Replace(plain)
	return strings.Join(strings.Fields(plain), " ")
}

func truncateArticleSummary(summary string) string {
	summary = strings.Join(strings.Fields(strings.TrimSpace(summary)), " ")
	if utf8.RuneCountInString(summary) <= contentgenerated.PostPublicationSummaryMaxRunes {
		return summary
	}
	runes := []rune(summary)
	return string(runes[:contentgenerated.PostPublicationSummaryMaxRunes-1]) + "…"
}
