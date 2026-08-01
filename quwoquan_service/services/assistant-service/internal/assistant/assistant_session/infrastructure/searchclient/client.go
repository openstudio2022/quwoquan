package searchclient

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtsearch "quwoquan_service/runtime/search"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/tool"
)

const searchQueryOperationID = "search.search_index_view.Search"

// Client 把助手 app_search 工具绑定到 search-service 的 canonical SearchIndexView operation。
// 它只负责 transport 与 typed wire 映射，不实现第二套召回、排序或引用规则。
type Client struct {
	baseURL *url.URL
	http    *http.Client
	path    string
}

type searchRequest struct {
	Query       string         `json:"query"`
	Mode        string         `json:"mode"`
	ObjectTypes []string       `json:"objectTypes,omitempty"`
	Limit       int            `json:"limit"`
	Filters     *searchFilters `json:"filters,omitempty"`
}

type searchFilters struct {
	Tags      []string         `json:"tags,omitempty"`
	TimeRange *searchTimeRange `json:"timeRange,omitempty"`
}

type searchTimeRange struct {
	From string `json:"from,omitempty"`
	To   string `json:"to,omitempty"`
}

// New 创建 search-service typed egress client。
func New(baseURL string, httpClient *http.Client) (*Client, error) {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil {
		return nil, fmt.Errorf("parse search-service base url: %w", err)
	}
	if parsed.Scheme == "" || parsed.Host == "" {
		return nil, fmt.Errorf("search-service base url must be absolute")
	}
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 3 * time.Second}
	}
	path, err := operationPath()
	if err != nil {
		return nil, err
	}
	return &Client{baseURL: parsed, http: httpClient, path: path}, nil
}

// Handler 返回可直接登记到 assistant tool registry 的真实 app_search handler。
func (c *Client) Handler() toolpkg.Handler {
	return func(ctx context.Context, req toolpkg.Request) (toolpkg.Result, error) {
		query := resolveQuery(req.Input)
		if query == "" {
			return toolpkg.Result{}, fmt.Errorf("app_search query is required")
		}
		wire := searchRequest{
			Query:       query,
			Mode:        "result",
			ObjectTypes: resolveObjectTypes(req.Input),
			Limit:       resolveLimit(req.Input),
			Filters:     resolveFilters(req.Input),
		}
		response, err := c.search(ctx, wire)
		if err != nil {
			return toolpkg.Result{}, err
		}
		return toolpkg.Result{Output: toToolOutput(response)}, nil
	}
}

// Retrieve 调用 canonical SearchIndexView，并返回未经助手二次排序的 typed 结果。
func (c *Client) Retrieve(
	ctx context.Context,
	query string,
	objectTypes []string,
	limit int,
) (rtsearch.RetrieveResponse, error) {
	return c.search(ctx, searchRequest{
		Query:       strings.TrimSpace(query),
		Mode:        "result",
		ObjectTypes: objectTypes,
		Limit:       limit,
	})
}

func (c *Client) search(ctx context.Context, wire searchRequest) (rtsearch.RetrieveResponse, error) {
	payload, err := json.Marshal(wire)
	if err != nil {
		return rtsearch.RetrieveResponse{}, fmt.Errorf("encode search request: %w", err)
	}
	endpoint := c.baseURL.ResolveReference(&url.URL{Path: c.path})
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint.String(), bytes.NewReader(payload))
	if err != nil {
		return rtsearch.RetrieveResponse{}, fmt.Errorf("build search request: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := c.http.Do(request)
	if err != nil {
		return rtsearch.RetrieveResponse{}, fmt.Errorf("call search-service: %w", err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 2<<20))
	if err != nil {
		return rtsearch.RetrieveResponse{}, fmt.Errorf("read search-service response: %w", err)
	}
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return rtsearch.RetrieveResponse{}, fmt.Errorf(
			"search-service status=%d body=%s",
			response.StatusCode,
			strings.TrimSpace(string(body)),
		)
	}
	var result rtsearch.RetrieveResponse
	if err := json.Unmarshal(body, &result); err != nil {
		return rtsearch.RetrieveResponse{}, fmt.Errorf("decode search-service response: %w", err)
	}
	return result, nil
}

func operationPath() (string, error) {
	for _, descriptor := range operationsecurity.ForDomain("search") {
		if descriptor.CanonicalOperationID == searchQueryOperationID {
			return descriptor.PathTemplate, nil
		}
	}
	return "", fmt.Errorf("generated descriptor %q is missing", searchQueryOperationID)
}

func resolveQuery(input map[string]any) string {
	if value, ok := input["query"].(string); ok && strings.TrimSpace(value) != "" {
		return strings.TrimSpace(value)
	}
	terms := toStringSlice(input["terms"])
	if len(terms) == 0 {
		terms = toStringSlice(input["names"])
	}
	return strings.Join(terms, " ")
}

func resolveObjectTypes(input map[string]any) []string {
	targets := toStringSlice(input["targets"])
	if len(targets) > 0 {
		return targets
	}
	return toStringSlice(input["objectTypes"])
}

func resolveLimit(input map[string]any) int {
	switch value := input["limit"].(type) {
	case int:
		if value > 0 && value <= 50 {
			return value
		}
	case float64:
		limit := int(value)
		if limit > 0 && limit <= 50 {
			return limit
		}
	}
	return 10
}

func resolveFilters(input map[string]any) *searchFilters {
	tags := toStringSlice(input["tags"])
	var timeRange *searchTimeRange
	if raw, ok := input["timeRange"].(map[string]any); ok {
		from, _ := raw["from"].(string)
		to, _ := raw["to"].(string)
		from = strings.TrimSpace(from)
		to = strings.TrimSpace(to)
		if from != "" || to != "" {
			timeRange = &searchTimeRange{From: from, To: to}
		}
	}
	if len(tags) == 0 && timeRange == nil {
		return nil
	}
	return &searchFilters{Tags: tags, TimeRange: timeRange}
}

func toToolOutput(response rtsearch.RetrieveResponse) map[string]any {
	results := make([]map[string]any, 0, len(response.Hits))
	titles := make([]string, 0, len(response.Hits))
	for _, hit := range response.Hits {
		results = append(results, map[string]any{
			"target":             string(hit.Target),
			"objectId":           hit.ObjectID,
			"title":              hit.Title,
			"snippet":            hit.Snippet,
			"score":              hit.Score,
			"matchedTerms":       hit.MatchedTerms,
			"matchedTags":        hit.MatchedTags,
			"payload":            hit.Payload,
			"connectionState":    hit.ConnectionState,
			"intersectionReason": hit.IntersectionReason,
			"rankReasons":        hit.RankReasons,
			"rankPosition":       hit.RankPosition,
		})
		if strings.TrimSpace(hit.Title) != "" && len(titles) < 3 {
			titles = append(titles, strings.TrimSpace(hit.Title))
		}
	}
	citations := make([]map[string]any, 0, len(response.Citations))
	for _, citation := range response.Citations {
		citations = append(citations, map[string]any{
			"citationId":   citation.CitationID,
			"objectType":   citation.ObjectType,
			"objectId":     citation.ObjectID,
			"title":        citation.Title,
			"contentType":  citation.ContentType,
			"snippet":      citation.Snippet,
			"url":          citation.URL,
			"deepLink":     citation.DeepLink,
			"badgeLabel":   citation.BadgeLabel,
			"sourceDomain": citation.SourceDomain,
			"score":        citation.Score,
		})
	}
	summary := "未检索到匹配结果"
	if len(titles) > 0 {
		summary = strings.Join(titles, "；")
	}
	return map[string]any{
		"provider":  response.Provenance.Provider,
		"summary":   summary,
		"results":   results,
		"citations": citations,
		"provenance": map[string]any{
			"provider":    response.Provenance.Provider,
			"generatedAt": response.Provenance.GeneratedAt.Format(time.RFC3339Nano),
		},
	}
}

func toStringSlice(value any) []string {
	switch typed := value.(type) {
	case []string:
		result := make([]string, 0, len(typed))
		for _, item := range typed {
			if trimmed := strings.TrimSpace(item); trimmed != "" {
				result = append(result, trimmed)
			}
		}
		return result
	case []any:
		result := make([]string, 0, len(typed))
		for _, item := range typed {
			if text, ok := item.(string); ok && strings.TrimSpace(text) != "" {
				result = append(result, strings.TrimSpace(text))
			}
		}
		return result
	default:
		return nil
	}
}
