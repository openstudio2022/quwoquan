package main

import (
	"context"
	"fmt"
	htmlpkg "html"
	"io"
	"log"
	"net/http"
	"net/url"
	"regexp"
	"strings"

	"quwoquan_service/services/assistant-service/internal/application/tool"
)

func executeDuckDuckGoQueries(ctx context.Context, client *http.Client, queries []string) (string, []map[string]any, bool, error) {
	if len(queries) == 0 {
		return "", nil, false, fmt.Errorf("search query is required")
	}
	allRefs := []map[string]any{}
	lastErr := error(nil)
	for _, query := range queries {
		if strings.TrimSpace(query) == "" {
			continue
		}
		summary, refs, err := duckDuckGoHTMLSearch(ctx, client, query)
		if err != nil {
			lastErr = err
			continue
		}
		allRefs = mergeSearchReferences(allRefs, refs)
		if len(allRefs) >= 5 {
			break
		}
		_ = summary
	}
	if len(allRefs) == 0 {
		if lastErr == nil {
			lastErr = fmt.Errorf("empty_summary")
		}
		return "", nil, false, lastErr
	}
	return rebuildSearchOutcomeFromRefs("", allRefs), allRefs, true, nil
}

func rebuildSearchOutcomeFromRefs(fallbackSummary string, refs []map[string]any) string {
	parts := []string{}
	for _, ref := range refs {
		snippet := strings.TrimSpace(fmt.Sprint(ref["snippet"]))
		if snippet == "" || snippet == "<nil>" {
			snippet = strings.TrimSpace(fmt.Sprint(ref["title"]))
		}
		if snippet == "" || snippet == "<nil>" {
			continue
		}
		parts = append(parts, snippet)
		if len(parts) >= 5 {
			break
		}
	}
	if len(parts) == 0 {
		return truncateRunes(strings.TrimSpace(fallbackSummary), 500)
	}
	return truncateRunes(strings.Join(parts, "；"), 500)
}

func mergeSearchReferences(existing []map[string]any, incoming []map[string]any) []map[string]any {
	merged := append([]map[string]any{}, existing...)
	seen := map[string]bool{}
	for _, ref := range merged {
		key := strings.TrimSpace(fmt.Sprint(ref["url"]))
		if key == "" || key == "<nil>" {
			key = strings.TrimSpace(fmt.Sprint(ref["title"])) + "|" + strings.TrimSpace(fmt.Sprint(ref["source"]))
		}
		if key != "" && key != "|" {
			seen[key] = true
		}
	}
	for _, ref := range incoming {
		if len(merged) >= 5 {
			break
		}
		key := strings.TrimSpace(fmt.Sprint(ref["url"]))
		if key == "" || key == "<nil>" {
			key = strings.TrimSpace(fmt.Sprint(ref["title"])) + "|" + strings.TrimSpace(fmt.Sprint(ref["source"]))
		}
		if key == "" || key == "|" || seen[key] {
			continue
		}
		seen[key] = true
		merged = append(merged, ref)
	}
	return merged
}

func searchToolResult(toolName string, provider string, summary string, refs []map[string]any, reliable bool) tool.Result {
	if toolName == "app_search" {
		return tool.Result{Output: map[string]any{
			"provider": provider,
			"summary":  summary,
			"results":  refs,
			"reliable": reliable,
		}}
	}
	return tool.Result{Output: map[string]any{
		"provider":   provider,
		"summary":    summary,
		"references": refs,
		"reliable":   reliable,
	}}
}

func duckDuckGoHTMLSearch(ctx context.Context, client *http.Client, query string) (string, []map[string]any, error) {
	if query == "" {
		return "", nil, fmt.Errorf("search query is required")
	}
	endpoint := "https://duckduckgo.com/html/?q=" + url.QueryEscape(query)
	log.Printf("assistant duckduckgo request query=%q", query)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return "", nil, err
	}
	req.Header.Set("User-Agent", "quwoquan-assistant-beta/1.0")
	resp, err := client.Do(req)
	if err != nil {
		return "", nil, err
	}
	defer resp.Body.Close()
	log.Printf("assistant duckduckgo response query=%q status=%d", query, resp.StatusCode)
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", nil, fmt.Errorf("duckduckgo status=%d", resp.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, 256*1024))
	if err != nil {
		return "", nil, err
	}
	summary, refs := extractDuckDuckGoResults(string(body))
	if summary == "" {
		log.Printf("assistant duckduckgo fallback query=%q reason=empty_summary", query)
		return "", nil, fmt.Errorf("empty_summary")
	}
	log.Printf("assistant duckduckgo parsed query=%q refs=%d summaryLen=%d", query, len(refs), len([]rune(summary)))
	return summary, refs, nil
}

func stripHTML(raw string) string {
	var out strings.Builder
	inTag := false
	for _, r := range raw {
		switch r {
		case '<':
			inTag = true
		case '>':
			inTag = false
			out.WriteRune(' ')
		default:
			if !inTag {
				out.WriteRune(r)
			}
		}
	}
	return out.String()
}

var (
	duckDuckGoResultPattern  = regexp.MustCompile(`(?is)<a([^>]*class="[^"]*result__a[^"]*"[^>]*)>(.*?)</a>`)
	duckDuckGoHrefPattern    = regexp.MustCompile(`(?is)href="([^"]+)"`)
	duckDuckGoSnippetPattern = regexp.MustCompile(`(?is)<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|<div[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>`)
)

func extractDuckDuckGoResults(raw string) (string, []map[string]any) {
	results := duckDuckGoResultPattern.FindAllStringSubmatch(raw, 5)
	snippets := duckDuckGoSnippetPattern.FindAllStringSubmatch(raw, 3)
	refs := []map[string]any{}
	parts := []string{}
	for i, resultMatch := range results {
		title := cleanSearchText(resultMatch[2])
		href := ""
		if hrefMatch := duckDuckGoHrefPattern.FindStringSubmatch(resultMatch[1]); len(hrefMatch) > 1 {
			href = normalizeDuckDuckGoHref(hrefMatch[1])
		}
		snippet := ""
		if i < len(snippets) {
			for _, candidate := range snippets[i][1:] {
				if strings.TrimSpace(candidate) != "" {
					snippet = cleanSearchText(candidate)
					break
				}
			}
		}
		if title == "" && snippet == "" {
			continue
		}
		if snippet == "" {
			snippet = title
		}
		parts = append(parts, snippet)
		source := "duckduckgo_html"
		if host := sourceHostFromURL(href); host != "" {
			source = host
		}
		refs = append(refs, map[string]any{
			"title":   title,
			"url":     href,
			"source":  source,
			"snippet": snippet,
		})
	}
	summary := strings.Join(parts, "；")
	summary = truncateRunes(summary, 500)
	return summary, refs
}

func truncateRunes(s string, maxRunes int) string {
	runes := []rune(s)
	if len(runes) <= maxRunes {
		return s
	}
	return string(runes[:maxRunes])
}

func cleanSearchText(raw string) string {
	text := htmlpkg.UnescapeString(stripHTML(raw))
	text = strings.Join(strings.Fields(text), " ")
	return strings.TrimSpace(text)
}

func acceptedReferencesFromObservation(observation map[string]any) []map[string]any {
	if observation == nil {
		return nil
	}
	retrievalProcessing, ok := observation["retrievalProcessing"].(map[string]any)
	if !ok {
		return nil
	}
	switch items := retrievalProcessing["acceptedReferences"].(type) {
	case []map[string]any:
		return items
	case []any:
		refs := []map[string]any{}
		for _, item := range items {
			entry, ok := item.(map[string]any)
			if ok {
				refs = append(refs, entry)
			}
		}
		return refs
	default:
		return nil
	}
}

func ensureKnowledgeSourcesSection(markdown string, refs []map[string]any) string {
	trimmed := strings.TrimSpace(markdown)
	if trimmed == "" || len(refs) == 0 || strings.Contains(trimmed, "知识来源") {
		return trimmed
	}
	lines := []string{trimmed, "", "## 知识来源"}
	for _, ref := range refs {
		title := strings.TrimSpace(fmt.Sprint(ref["title"]))
		urlValue := strings.TrimSpace(fmt.Sprint(ref["url"]))
		source := strings.TrimSpace(fmt.Sprint(ref["source"]))
		if title == "" && source == "" {
			continue
		}
		label := title
		if label == "" {
			label = source
		}
		if urlValue != "" && urlValue != "<nil>" {
			lines = append(lines, fmt.Sprintf("- [%s](%s)", label, urlValue))
			continue
		}
		lines = append(lines, fmt.Sprintf("- %s", label))
	}
	return strings.Join(lines, "\n")
}

func stripKnowledgeSourcesSection(markdown string) string {
	trimmed := strings.TrimSpace(markdown)
	if trimmed == "" {
		return trimmed
	}
	marker := "\n## 知识来源"
	if index := strings.Index(trimmed, marker); index >= 0 {
		return strings.TrimSpace(trimmed[:index])
	}
	if strings.HasPrefix(trimmed, "## 知识来源") {
		return ""
	}
	return trimmed
}

func normalizeDuckDuckGoHref(raw string) string {
	href := strings.TrimSpace(htmlpkg.UnescapeString(raw))
	if href == "" {
		return ""
	}
	if strings.HasPrefix(href, "//") {
		href = "https:" + href
	}
	if strings.HasPrefix(href, "/") {
		href = "https://duckduckgo.com" + href
	}
	parsed, err := url.Parse(href)
	if err != nil {
		return href
	}
	if uddg := strings.TrimSpace(parsed.Query().Get("uddg")); uddg != "" {
		if decoded, err := url.QueryUnescape(uddg); err == nil {
			return decoded
		}
		return uddg
	}
	return href
}

func sourceHostFromURL(raw string) string {
	if strings.TrimSpace(raw) == "" {
		return ""
	}
	parsed, err := url.Parse(raw)
	if err != nil {
		return ""
	}
	return strings.ToLower(strings.TrimSpace(parsed.Hostname()))
}

func deterministicSearchFallback(query string) string {
	return fmt.Sprintf("已围绕“%s”尝试检索，但外部搜索未返回可靠结构化摘要；请基于用户问题与已有上下文回答，明确不确定性，不虚构实时事实。", query)
}

func deterministicSearchFallbackResult(query string, reason string) (string, []map[string]any) {
	summary := deterministicSearchFallback(query)
	_ = reason
	return summary, []map[string]any{}
}

func inputString(input map[string]any, key string) string {
	value := strings.TrimSpace(fmt.Sprint(input[key]))
	if value == "<nil>" {
		return ""
	}
	return value
}
