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
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
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
	Query       string   `json:"query"`
	Mode        string   `json:"mode"`
	ObjectTypes []string `json:"objectTypes,omitempty"`
	Limit       int      `json:"limit"`
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
			Query: query,
			Mode:  "result",
			Limit: 10,
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
	return ""
}

func toToolOutput(response rtsearch.RetrieveResponse) map[string]any {
	results := make([]map[string]any, 0, len(response.Hits))
	titles := make([]string, 0, len(response.Hits))
	emergedTagRefs := make([]string, 0)
	seenTagRefs := map[string]bool{}
	targetIDs := make([]string, 0, len(response.Hits))
	seenTargetIDs := map[string]bool{}
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
		if objectID := strings.TrimSpace(hit.ObjectID); objectID != "" &&
			!seenTargetIDs[objectID] {
			seenTargetIDs[objectID] = true
			targetIDs = append(targetIDs, objectID)
		}
		for _, value := range append(
			append([]string(nil), hit.MatchedTags...),
			searchHitTaxonomyValues(hit.Payload)...,
		) {
			tagRef := canonicalTopicTagRef(value)
			if tagRef == "" || seenTagRefs[tagRef] {
				continue
			}
			seenTagRefs[tagRef] = true
			emergedTagRefs = append(emergedTagRefs, tagRef)
		}
	}
	citations := make([]map[string]any, 0, len(response.Citations))
	sourceIDs := make([]string, 0, len(response.Citations))
	seenSourceIDs := map[string]bool{}
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
		if citationID := strings.TrimSpace(citation.CitationID); citationID != "" &&
			!seenSourceIDs[citationID] {
			seenSourceIDs[citationID] = true
			sourceIDs = append(sourceIDs, citationID)
		}
	}
	summary := "未检索到匹配结果"
	status := "insufficient"
	evidenceSufficient := false
	replanRequired := true
	reason := "canonical_search_no_hits"
	if len(results) > 0 {
		if len(titles) > 0 {
			summary = strings.Join(titles, "；")
		} else {
			summary = fmt.Sprintf("检索到 %d 个匹配结果", len(results))
		}
		status = "accepted"
		evidenceSufficient = true
		replanRequired = false
		reason = "canonical_search_hits"
	}
	return map[string]any{
		"provider":       response.Provenance.Provider,
		"summary":        summary,
		"results":        results,
		"citations":      citations,
		"emergedTagRefs": emergedTagRefs,
		"provenance": map[string]any{
			"provider":    response.Provenance.Provider,
			"generatedAt": response.Provenance.GeneratedAt.Format(time.RFC3339Nano),
		},
		"evidenceAssessment": map[string]any{
			"status":             status,
			"evidenceSufficient": evidenceSufficient,
			"replanRequired":     replanRequired,
			"reason":             reason,
			"targetIds":          targetIDs,
			"documentIds":        []string{},
			"artifactRefs":       []string{},
			"sourceIds":          sourceIDs,
		},
	}
}

func searchHitTaxonomyValues(payload map[string]any) []string {
	if payload == nil {
		return nil
	}
	values := make([]string, 0, 2)
	for _, key := range []string{"categoryId", "subCategory"} {
		if value := strings.TrimSpace(fmt.Sprint(payload[key])); value != "" &&
			value != "<nil>" {
			values = append(values, value)
		}
	}
	return values
}

func canonicalTopicTagRef(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return ""
	}
	if strings.Contains(value, "/") {
		return value
	}
	return "Topic/" + value
}
