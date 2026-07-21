package publicsearch

import (
	"context"
	"fmt"
	htmlpkg "html"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/application"
)

type Config struct {
	SearchURL string
}

type Client struct {
	http      *http.Client
	searchURL *url.URL
}

func New(cfg Config, httpClient *http.Client) (*Client, error) {
	searchURL, err := url.Parse(strings.TrimSpace(cfg.SearchURL))
	if err != nil || searchURL.Scheme == "" || searchURL.Host == "" {
		return nil, fmt.Errorf("public search url must be absolute")
	}
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 8 * time.Second}
	}
	return &Client{http: httpClient, searchURL: searchURL}, nil
}

func (c *Client) Search(
	ctx context.Context,
	request application.ExternalSearchRequest,
) (application.ExternalSearchResult, error) {
	queries := uniqueQueries(request.Queries, request.Query)
	if len(queries) == 0 {
		return application.ExternalSearchResult{}, application.ProviderFailure{
			Capability: "public_search",
			Reason:     application.ProviderFailureInvalidResponse,
		}
	}
	references := make([]application.ExternalReference, 0, 5)
	for _, query := range queries {
		result, err := c.duckDuckGo(ctx, query)
		if err != nil {
			continue
		}
		references = mergeReferences(references, result.References, 5)
		if len(references) >= 5 {
			break
		}
	}
	if len(references) > 0 {
		return application.ExternalSearchResult{
			Summary:    summaryFromReferences(references),
			References: references,
		}, nil
	}
	return application.ExternalSearchResult{}, application.ProviderFailure{
		Capability: "public_search",
		Reason:     application.ProviderFailureUnavailable,
	}
}

func (c *Client) duckDuckGo(
	ctx context.Context,
	query string,
) (application.ExternalSearchResult, error) {
	endpoint := *c.searchURL
	parameters := endpoint.Query()
	parameters.Set("q", query)
	endpoint.RawQuery = parameters.Encode()
	body, status, err := c.get(ctx, endpoint.String(), "quwoquan-assistant/1.0")
	if err != nil {
		return application.ExternalSearchResult{}, err
	}
	if status < http.StatusOK || status >= http.StatusMultipleChoices {
		return application.ExternalSearchResult{}, application.ProviderFailure{
			Capability: "public_search",
			Reason:     application.ProviderFailureUnavailable,
		}
	}
	references := extractDuckDuckGoResults(string(body))
	if len(references) == 0 {
		return application.ExternalSearchResult{}, application.ProviderFailure{
			Capability: "public_search",
			Reason:     application.ProviderFailureInvalidResponse,
		}
	}
	return application.ExternalSearchResult{
		Summary:    summaryFromReferences(references),
		References: references,
	}, nil
}

func (c *Client) get(
	ctx context.Context,
	endpoint string,
	userAgent string,
) ([]byte, int, error) {
	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
		if err != nil {
			return nil, 0, application.ProviderFailure{
				Capability: "public_search",
				Reason:     application.ProviderFailureInvalidResponse,
			}
		}
		request.Header.Set("User-Agent", userAgent)
		response, err := c.http.Do(request)
		if err == nil {
			body, readErr := io.ReadAll(io.LimitReader(response.Body, 256*1024))
			_ = response.Body.Close()
			if readErr == nil && (response.StatusCode < 500 || attempt == 1) {
				return body, response.StatusCode, nil
			}
			lastErr = readErr
		} else {
			lastErr = err
		}
		if attempt == 0 {
			select {
			case <-ctx.Done():
				return nil, 0, providerFailure(ctx.Err())
			case <-time.After(100 * time.Millisecond):
			}
		}
	}
	return nil, 0, providerFailure(lastErr)
}

func providerFailure(err error) application.ProviderFailure {
	if err == context.DeadlineExceeded {
		return application.ProviderFailure{
			Capability: "public_search",
			Reason:     application.ProviderFailureTimeout,
		}
	}
	return application.ProviderFailure{
		Capability: "public_search",
		Reason:     application.ProviderFailureUnavailable,
	}
}

var (
	resultPattern  = regexp.MustCompile(`(?is)<a([^>]*class="[^"]*result__a[^"]*"[^>]*)>(.*?)</a>`)
	hrefPattern    = regexp.MustCompile(`(?is)href="([^"]+)"`)
	snippetPattern = regexp.MustCompile(`(?is)<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|<div[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>`)
)

func extractDuckDuckGoResults(raw string) []application.ExternalReference {
	results := resultPattern.FindAllStringSubmatch(raw, 5)
	snippets := snippetPattern.FindAllStringSubmatch(raw, 5)
	references := make([]application.ExternalReference, 0, len(results))
	for index, result := range results {
		title := cleanText(result[2])
		href := ""
		if match := hrefPattern.FindStringSubmatch(result[1]); len(match) > 1 {
			href = normalizeDuckDuckGoHref(match[1])
		}
		snippet := ""
		if index < len(snippets) {
			for _, candidate := range snippets[index][1:] {
				if cleaned := cleanText(candidate); cleaned != "" {
					snippet = cleaned
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
		source := sourceHost(href)
		if source == "" {
			source = "public_web"
		}
		references = append(references, application.ExternalReference{
			Title:   title,
			URL:     href,
			Source:  source,
			Snippet: snippet,
			Rank:    len(references) + 1,
		})
	}
	return references
}

func uniqueQueries(values []string, fallback string) []string {
	queries := make([]string, 0, len(values)+1)
	seen := make(map[string]struct{})
	for _, value := range append(values, fallback) {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		queries = append(queries, value)
	}
	return queries
}

func mergeReferences(
	existing []application.ExternalReference,
	incoming []application.ExternalReference,
	limit int,
) []application.ExternalReference {
	seen := make(map[string]struct{}, len(existing))
	for _, reference := range existing {
		seen[reference.URL+"|"+reference.Title+"|"+reference.Source] = struct{}{}
	}
	for _, reference := range incoming {
		if len(existing) >= limit {
			break
		}
		key := reference.URL + "|" + reference.Title + "|" + reference.Source
		if _, ok := seen[key]; ok {
			continue
		}
		reference.Rank = len(existing) + 1
		seen[key] = struct{}{}
		existing = append(existing, reference)
	}
	return existing
}

func summaryFromReferences(references []application.ExternalReference) string {
	parts := make([]string, 0, len(references))
	for _, reference := range references {
		if reference.Snippet != "" {
			parts = append(parts, reference.Snippet)
		}
	}
	return truncate(strings.Join(parts, "；"), 500)
}

func cleanText(raw string) string {
	var out strings.Builder
	inTag := false
	for _, runeValue := range raw {
		switch runeValue {
		case '<':
			inTag = true
		case '>':
			inTag = false
			out.WriteRune(' ')
		default:
			if !inTag {
				out.WriteRune(runeValue)
			}
		}
	}
	return strings.TrimSpace(strings.Join(strings.Fields(htmlpkg.UnescapeString(out.String())), " "))
}

func normalizeDuckDuckGoHref(raw string) string {
	href := strings.TrimSpace(htmlpkg.UnescapeString(raw))
	parsed, err := url.Parse(href)
	if err != nil {
		return href
	}
	if redirect := strings.TrimSpace(parsed.Query().Get("uddg")); redirect != "" {
		if decoded, err := url.QueryUnescape(redirect); err == nil {
			return decoded
		}
	}
	return href
}

func sourceHost(raw string) string {
	parsed, err := url.Parse(raw)
	if err != nil {
		return ""
	}
	return strings.ToLower(strings.TrimSpace(parsed.Hostname()))
}

func truncate(value string, maximum int) string {
	runes := []rune(value)
	if len(runes) <= maximum {
		return value
	}
	return string(runes[:maximum])
}
