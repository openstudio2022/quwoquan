package post

import (
	"crypto/sha256"
	"encoding/hex"
	"regexp"
	"strings"

	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
)

func (s *PostService) syncArticleMarkdownSnapshot(post *postmodel.Post) {
	if post == nil || strings.TrimSpace(post.ContentType) != "article" {
		return
	}
	markdown := strings.TrimSpace(post.ArticleMarkdown)
	if markdown == "" {
		return
	}
	if strings.TrimSpace(post.MarkdownDialect) == "" {
		post.MarkdownDialect = "qwq-rich-md"
	}
	post.ArticleMarkdownDigest = markdownDigest(markdown)
	frontMatter, body := splitArticleMarkdownFrontMatter(markdown)
	if title := strings.TrimSpace(asString(frontMatter["title"])); title != "" {
		post.Title = title
	} else if strings.TrimSpace(post.Title) == "" {
		post.Title = firstMarkdownHeading(body)
	}
	if summary := strings.TrimSpace(asString(frontMatter["summary"])); summary != "" {
		post.Summary = summary
	}
	post.Body = markdownPlainText(body)
	if cover := strings.TrimSpace(asString(frontMatter["coverImage"])); cover != "" {
		post.CoverUrl = cover
	}
	if template := strings.TrimSpace(asString(frontMatter["template"])); template != "" {
		post.ArticleTemplate = template
	}
	if fontPreset := strings.TrimSpace(asString(frontMatter["fontPreset"])); fontPreset != "" {
		post.ArticleFontPreset = fontPreset
	}
	if len(post.ArticleRenderProfile) > 0 {
		if template := strings.TrimSpace(asString(post.ArticleRenderProfile["template"])); template != "" {
			post.ArticleTemplate = template
		}
		if fontPreset := strings.TrimSpace(asString(post.ArticleRenderProfile["fontPreset"])); fontPreset != "" {
			post.ArticleFontPreset = fontPreset
		}
	}
	post.MediaUrls = markdownAssetURIs(markdown)
}

func markdownDigest(markdown string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(markdown)))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func splitArticleMarkdownFrontMatter(markdown string) (map[string]any, string) {
	normalized := strings.ReplaceAll(markdown, "\r\n", "\n")
	if !strings.HasPrefix(normalized, "---\n") {
		return nil, normalized
	}
	end := strings.Index(normalized[4:], "\n---")
	if end < 0 {
		return nil, normalized
	}
	raw := normalized[4 : 4+end]
	body := strings.TrimLeft(normalized[4+end+len("\n---"):], "\n")
	return parseSimpleFrontMatter(raw), body
}

func parseSimpleFrontMatter(raw string) map[string]any {
	result := map[string]any{}
	var currentListKey string
	for _, line := range strings.Split(raw, "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			continue
		}
		if strings.HasPrefix(trimmed, "- ") && currentListKey != "" {
			result[currentListKey] = append(asStringSlice(result[currentListKey]), strings.TrimSpace(strings.TrimPrefix(trimmed, "- ")))
			continue
		}
		parts := strings.SplitN(trimmed, ":", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		value := strings.TrimSpace(parts[1])
		if value == "" {
			currentListKey = key
			result[key] = []string{}
			continue
		}
		currentListKey = ""
		result[key] = strings.Trim(value, `"'`)
	}
	return result
}

func firstMarkdownHeading(body string) string {
	for _, line := range strings.Split(body, "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "# ") {
			return strings.TrimSpace(strings.TrimPrefix(trimmed, "# "))
		}
	}
	return ""
}

func markdownPlainText(body string) string {
	lines := []string{}
	inFence := false
	for _, line := range strings.Split(body, "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "```") {
			inFence = !inFence
			continue
		}
		if inFence || trimmed == "" || strings.HasPrefix(trimmed, ":::") {
			continue
		}
		if strings.HasPrefix(trimmed, "#") {
			continue
		}
		if strings.HasPrefix(trimmed, "asset://") || strings.HasPrefix(trimmed, "![") {
			continue
		}
		lines = append(lines, strings.TrimPrefix(trimmed, "> "))
	}
	return strings.Join(lines, "\n")
}

func markdownAssetURIs(markdown string) []string {
	matches := regexp.MustCompile(`asset://[A-Za-z0-9_\-./]+`).FindAllString(markdown, -1)
	seen := map[string]bool{}
	result := []string{}
	for _, match := range matches {
		if !seen[match] {
			seen[match] = true
			result = append(result, match)
		}
	}
	return result
}
