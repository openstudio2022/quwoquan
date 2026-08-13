package searchclient

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"sync"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/retrievalplan"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
)

const (
	searchQueryOperationID      = "search.search_index_view.Search"
	searchRetrievalMode         = "retrieval"
	maxOwnerResponseBytes       = 4 << 20
	maxParallelOwnerSearchCalls = 4
	defaultRetrievalQueryLimit  = 10
)

type AuthorizationProvider interface {
	AuthorizationHeader(context.Context) (string, error)
}

// Client binds app_search to the one canonical SearchIndexView.Search owner
// operation. It owns transport and audience projection only; recall, ranking,
// filtering, facets, citations and cursor semantics stay in search-service.
type Client struct {
	baseURL             *url.URL
	http                *http.Client
	path                string
	authorization       AuthorizationProvider
	contractGraphDigest string
}

type searchRequest struct {
	Query       string   `json:"query"`
	Mode        string   `json:"mode"`
	ObjectTypes []string `json:"objectTypes,omitempty"`
	Limit       int      `json:"limit"`
	Cursor      string   `json:"cursor,omitempty"`
}

type ownerSearchResponse struct {
	SearchRequestID  string                `json:"searchRequestId"`
	InterpretedQuery ownerInterpretedQuery `json:"interpretedQuery"`
	Hits             []ownerSearchHit      `json:"hits"`
	Citations        []ownerSearchCitation `json:"citations"`
	Facets           []json.RawMessage     `json:"facets"`
	DegradeSignals   []json.RawMessage     `json:"degradeSignals"`
	Provenance       ownerSearchProvenance `json:"provenance"`
	NextCursor       string                `json:"nextCursor"`
}

type ownerInterpretedQuery struct {
	Normalized          string   `json:"normalized"`
	Tokens              []string `json:"tokens"`
	Variants            []string `json:"variants"`
	DetectedEntities    []string `json:"detectedEntities"`
	DetectedTags        []string `json:"detectedTags"`
	SelectedObjectTypes []string `json:"selectedObjectTypes"`
}

type ownerSearchHit struct {
	ObjectRef    string            `json:"objectRef"`
	ObjectType   string            `json:"objectType"`
	ContentType  string            `json:"contentType,omitempty"`
	Title        string            `json:"title"`
	Snippet      string            `json:"snippet,omitempty"`
	ThumbnailURL string            `json:"thumbnailUrl,omitempty"`
	Action       string            `json:"action,omitempty"`
	RankPosition int               `json:"rankPosition"`
	MatchedTerms []string          `json:"matchedTerms"`
	RankReasons  []json.RawMessage `json:"rankReasons"`
	Evidence     []json.RawMessage `json:"evidence"`
}

type ownerSearchCitation struct {
	CitationID  string `json:"citationId"`
	ObjectRef   string `json:"objectRef"`
	ObjectType  string `json:"objectType"`
	ContentType string `json:"contentType,omitempty"`
	Title       string `json:"title"`
	Snippet     string `json:"snippet,omitempty"`
	URL         string `json:"url,omitempty"`
	DeepLink    string `json:"deepLink,omitempty"`
}

type ownerSearchProvenance struct {
	Source      string    `json:"source"`
	GeneratedAt time.Time `json:"generatedAt"`
}

func New(
	baseURL string,
	httpClient *http.Client,
	authorization AuthorizationProvider,
	contractGraphDigest string,
) (*Client, error) {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil {
		return nil, fmt.Errorf("parse search-service base url: %w", err)
	}
	if parsed.Scheme == "" || parsed.Host == "" || parsed.User != nil ||
		parsed.RawQuery != "" || parsed.Fragment != "" {
		return nil, errors.New("search-service base url must be an absolute origin")
	}
	if authorization == nil {
		return nil, errors.New("search owner authorization is required")
	}
	contractGraphDigest = strings.TrimSpace(contractGraphDigest)
	if !canonicalSHA256(contractGraphDigest) {
		return nil, errors.New("search owner ContractGraph digest is required")
	}
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 3 * time.Second}
	}
	copyClient := *httpClient
	copyClient.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	path, err := operationPath()
	if err != nil {
		return nil, err
	}
	return &Client{
		baseURL: parsed, http: &copyClient, path: path,
		authorization: authorization, contractGraphDigest: contractGraphDigest,
	}, nil
}

func (client *Client) Handler() toolpkg.Handler {
	return func(ctx context.Context, request toolpkg.Request) (toolpkg.Result, error) {
		plan, err := freezePlan(request)
		if err != nil {
			return toolpkg.Result{}, err
		}
		if request.ContractGraphDigest != client.contractGraphDigest {
			return toolpkg.Result{}, errors.New("app_search ContractGraph identity drifted")
		}
		if err := plan.Validate(); err != nil {
			return toolpkg.Result{}, err
		}
		responses, err := client.executePlan(ctx, plan)
		if err != nil {
			return toolpkg.Result{}, err
		}
		return toolpkg.Result{Output: toolOutput(plan, responses)}, nil
	}
}

func freezePlan(request toolpkg.Request) (retrievalplan.Plan, error) {
	primary := resolveString(request.Input["query"])
	if primary == "" {
		return retrievalplan.Plan{}, errors.New("app_search query is required")
	}
	queries := []retrievalplan.Query{{
		Dimension: "primary", Query: primary,
		ObjectTypes: SearchIndexEligibleObjectTypes(), Limit: defaultRetrievalQueryLimit,
	}}
	secondary, err := decodeSecondaryQueries(request.Input["searchQueries"])
	if err != nil {
		return retrievalplan.Plan{}, err
	}
	queries = append(queries, secondary...)
	goal := resolveString(request.Input["goal"])
	if goal == "" {
		goal = primary
	}
	criteria, err := decodeStringList(request.Input["evidenceCriteria"], "evidenceCriteria")
	if err != nil {
		return retrievalplan.Plan{}, err
	}
	if len(criteria) == 0 {
		criteria = []string{"至少一个可引用的站内检索结果"}
	}
	maximumQueries := len(queries)
	if value, found := request.Input["maximumQueries"]; found {
		maximumQueries, err = exactInteger(value)
		if err != nil {
			return retrievalplan.Plan{}, fmt.Errorf("app_search maximumQueries: %w", err)
		}
	}
	return retrievalplan.Freeze(retrievalplan.Input{
		Goal: goal, Queries: queries, EvidenceCriteria: criteria, MaximumQueries: maximumQueries,
		Identity: retrievalplan.Identity{
			RunID: request.RunID, TurnID: request.TurnID, ToolName: request.ToolName,
			ToolCatalogDigest:   request.ToolCatalogDigest,
			AccessPolicyDigest:  AssistantAccessPolicyDigest(),
			CandidateDigest:     request.RuntimeCandidateDigest,
			ContractGraphDigest: request.ContractGraphDigest,
			MaximumToolCalls:    request.MaximumToolCalls,
		},
	})
}

func decodeSecondaryQueries(value any) ([]retrievalplan.Query, error) {
	if value == nil {
		return nil, nil
	}
	items, ok := value.([]any)
	if !ok {
		return nil, errors.New("app_search searchQueries must be an array")
	}
	result := make([]retrievalplan.Query, 0, len(items))
	for index, item := range items {
		object, ok := item.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("app_search searchQueries[%d] must be an object", index)
		}
		objectTypes, err := requestedObjectTypes(object["objectTypes"])
		if err != nil {
			return nil, fmt.Errorf("app_search searchQueries[%d]: %w", index, err)
		}
		limit := defaultRetrievalQueryLimit
		if value, found := object["limit"]; found {
			limit, err = exactInteger(value)
			if err != nil {
				return nil, fmt.Errorf("app_search searchQueries[%d].limit: %w", index, err)
			}
		}
		result = append(result, retrievalplan.Query{
			Dimension: resolveString(object["dimension"]), Query: resolveString(object["query"]),
			ObjectTypes: objectTypes, Limit: limit,
		})
	}
	return result, nil
}

// SearchIndexEligibleObjectTypes intersects the assistant-readable projection
// with the canonical vocabulary the unified SearchIndexView can serve.
// web.document is owned by the web_search tool and integration.location_poi by
// the integration provider; sending either to POST /search would be
// structurally rejected.
func SearchIndexEligibleObjectTypes() []string {
	eligible := map[string]bool{}
	for _, objectType := range rtsearch.CloudSearchableObjectTypes {
		eligible[objectType] = true
	}
	result := make([]string, 0, len(rtsearch.CloudSearchableObjectTypes))
	for _, objectType := range AssistantReadableObjectTypes() {
		if eligible[objectType] {
			result = append(result, objectType)
		}
	}
	sort.Strings(result)
	return result
}

func requestedObjectTypes(value any) ([]string, error) {
	values, err := decodeStringList(value, "objectTypes")
	if err != nil {
		return nil, err
	}
	if len(values) == 0 {
		return SearchIndexEligibleObjectTypes(), nil
	}
	eligible := map[string]bool{}
	for _, objectType := range SearchIndexEligibleObjectTypes() {
		eligible[objectType] = true
	}
	for _, value := range values {
		if !assistantReadableObjectTypes[value] {
			return nil, fmt.Errorf("object type %q is not open to Assistant retrieval", value)
		}
		if !eligible[value] {
			return nil, fmt.Errorf("object type %q is not served by the unified search index", value)
		}
	}
	sort.Strings(values)
	return values, nil
}

func decodeStringList(value any, field string) ([]string, error) {
	if value == nil {
		return nil, nil
	}
	items, ok := value.([]any)
	if !ok {
		return nil, fmt.Errorf("app_search %s must be an array", field)
	}
	result := make([]string, 0, len(items))
	seen := map[string]struct{}{}
	for index, item := range items {
		text, ok := item.(string)
		text = strings.TrimSpace(text)
		if !ok || text == "" {
			return nil, fmt.Errorf("app_search %s[%d] must be a non-empty string", field, index)
		}
		if _, duplicated := seen[text]; duplicated {
			continue
		}
		seen[text] = struct{}{}
		result = append(result, text)
	}
	return result, nil
}

func (client *Client) executePlan(
	ctx context.Context,
	plan retrievalplan.Plan,
) ([]ownerSearchResponse, error) {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	responses := make([]ownerSearchResponse, len(plan.Queries))
	semaphore := make(chan struct{}, maxParallelOwnerSearchCalls)
	var wait sync.WaitGroup
	var firstErr error
	var errorMutex sync.Mutex
	for index, query := range plan.Queries {
		index, query := index, query
		wait.Add(1)
		go func() {
			defer wait.Done()
			select {
			case semaphore <- struct{}{}:
				defer func() { <-semaphore }()
			case <-ctx.Done():
				return
			}
			response, err := client.search(ctx, searchRequest{
				Query: query.Query, Mode: searchRetrievalMode,
				ObjectTypes: query.ObjectTypes, Limit: query.Limit,
			})
			if err != nil {
				errorMutex.Lock()
				if firstErr == nil {
					firstErr = fmt.Errorf("app_search query %q failed: %w", query.Dimension, err)
					cancel()
				}
				errorMutex.Unlock()
				return
			}
			responses[index] = response
		}()
	}
	wait.Wait()
	if firstErr != nil {
		return nil, firstErr
	}
	return responses, nil
}

func (client *Client) search(ctx context.Context, wire searchRequest) (ownerSearchResponse, error) {
	payload, err := json.Marshal(wire)
	if err != nil {
		return ownerSearchResponse{}, fmt.Errorf("encode search owner request: %w", err)
	}
	endpoint := client.baseURL.ResolveReference(&url.URL{Path: client.path})
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint.String(), bytes.NewReader(payload))
	if err != nil {
		return ownerSearchResponse{}, fmt.Errorf("build search owner request: %w", err)
	}
	authorization, err := client.authorization.AuthorizationHeader(ctx)
	if err != nil {
		return ownerSearchResponse{}, fmt.Errorf("sign search owner request: %w", err)
	}
	if !strings.HasPrefix(authorization, "Bearer ") || strings.TrimSpace(strings.TrimPrefix(authorization, "Bearer ")) == "" {
		return ownerSearchResponse{}, errors.New("search owner authorization is invalid")
	}
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Contract-Graph-SHA256", client.contractGraphDigest)
	response, err := client.http.Do(request)
	if err != nil {
		return ownerSearchResponse{}, fmt.Errorf("call search owner: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return ownerSearchResponse{}, fmt.Errorf("search owner status=%d", response.StatusCode)
	}
	mediaType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		return ownerSearchResponse{}, errors.New("search owner response must use application/json")
	}
	if response.Header.Get("X-Contract-Graph-SHA256") != client.contractGraphDigest {
		return ownerSearchResponse{}, errors.New("search owner ContractGraph identity drifted")
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, maxOwnerResponseBytes+1))
	if err != nil {
		return ownerSearchResponse{}, fmt.Errorf("read search owner response: %w", err)
	}
	if len(body) > maxOwnerResponseBytes {
		return ownerSearchResponse{}, errors.New("search owner response exceeds size limit")
	}
	var result ownerSearchResponse
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&result); err != nil {
		return ownerSearchResponse{}, fmt.Errorf("decode search owner response: %w", err)
	}
	if decoder.Decode(&struct{}{}) != io.EOF {
		return ownerSearchResponse{}, errors.New("search owner response has trailing JSON")
	}
	if err := validateOwnerResponse(result); err != nil {
		return ownerSearchResponse{}, err
	}
	return result, nil
}

func validateOwnerResponse(response ownerSearchResponse) error {
	if strings.TrimSpace(response.Provenance.Source) != "search_index_view" || response.Provenance.GeneratedAt.IsZero() {
		return errors.New("search owner provenance is invalid")
	}
	for index, hit := range response.Hits {
		if strings.TrimSpace(hit.ObjectRef) == "" || strings.TrimSpace(hit.ObjectType) == "" ||
			strings.TrimSpace(hit.Title) == "" || !assistantReadableObjectTypes[hit.ObjectType] {
			return fmt.Errorf("search owner hit[%d] is not assistant-readable", index)
		}
	}
	for index, citation := range response.Citations {
		if strings.TrimSpace(citation.CitationID) == "" || strings.TrimSpace(citation.ObjectRef) == "" ||
			strings.TrimSpace(citation.ObjectType) == "" || !assistantCitableObjectTypes[citation.ObjectType] {
			return fmt.Errorf("search owner citation[%d] is not assistant-citable", index)
		}
	}
	return nil
}

func toolOutput(plan retrievalplan.Plan, responses []ownerSearchResponse) map[string]any {
	buckets := make([]any, 0, len(responses))
	citations := make([]any, 0)
	targetRefs := make([]string, 0)
	sourceIDs := make([]string, 0)
	titles := make([]string, 0, 3)
	seenTargets := map[string]struct{}{}
	seenCitations := map[string]struct{}{}
	for index, response := range responses {
		hits := make([]any, 0, len(response.Hits))
		for _, hit := range response.Hits {
			hits = append(hits, map[string]any{
				"objectRef": hit.ObjectRef, "objectType": hit.ObjectType,
				"contentType": hit.ContentType, "title": hit.Title, "snippet": hit.Snippet,
			})
			if _, found := seenTargets[hit.ObjectRef]; !found {
				seenTargets[hit.ObjectRef] = struct{}{}
				targetRefs = append(targetRefs, hit.ObjectRef)
			}
			if len(titles) < 3 && strings.TrimSpace(hit.Title) != "" {
				titles = append(titles, strings.TrimSpace(hit.Title))
			}
		}
		buckets = append(buckets, map[string]any{
			"dimension": plan.Queries[index].Dimension, "query": plan.Queries[index].Query,
			"hits": hits, "nextCursor": response.NextCursor,
		})
		for _, citation := range response.Citations {
			key := citation.CitationID + "\x00" + citation.ObjectRef
			if _, found := seenCitations[key]; found {
				continue
			}
			seenCitations[key] = struct{}{}
			citations = append(citations, map[string]any{
				"citationId": citation.CitationID, "objectRef": citation.ObjectRef,
				"objectType": citation.ObjectType, "contentType": citation.ContentType,
				"title": citation.Title, "snippet": citation.Snippet,
				"url": citation.URL, "deepLink": citation.DeepLink,
			})
			sourceIDs = append(sourceIDs, citation.CitationID)
		}
	}
	sufficient := len(targetRefs) > 0
	status, reason, summary := "insufficient", "canonical_search_no_hits", "未检索到匹配结果"
	if sufficient {
		status, reason = "accepted", "canonical_search_hits"
		summary = strings.Join(titles, "；")
		if summary == "" {
			summary = fmt.Sprintf("检索到 %d 个匹配结果", len(targetRefs))
		}
	}
	planValue := map[string]any{}
	encodedPlan, _ := json.Marshal(plan)
	_ = json.Unmarshal(encodedPlan, &planValue)
	lastGeneratedAt := ""
	if len(responses) > 0 {
		lastGeneratedAt = responses[len(responses)-1].Provenance.GeneratedAt.Format(time.RFC3339Nano)
	}
	return map[string]any{
		"summary": summary, "resultBuckets": buckets, "citations": citations,
		"emergedTagRefs": []string{}, "retrievalPlan": planValue,
		"provenance": map[string]any{
			"canonicalOperationId": searchQueryOperationID, "planDigest": plan.Digest,
			"candidateDigest":     plan.Identity.CandidateDigest,
			"contractGraphDigest": plan.Identity.ContractGraphDigest,
			"source":              "search_index_view", "generatedAt": lastGeneratedAt,
		},
		"evidenceAssessment": map[string]any{
			"status": status, "evidenceSufficient": sufficient,
			"replanRequired": !sufficient, "reason": reason,
			"targetIds": targetRefs, "documentIds": []string{},
			"artifactRefs": []string{}, "sourceIds": sourceIDs,
		},
	}
}

func operationPath() (string, error) {
	for _, descriptor := range operationsecurity.ForDomain("search") {
		if descriptor.CanonicalOperationID == searchQueryOperationID {
			return descriptor.PathTemplate, nil
		}
	}
	return "", fmt.Errorf("generated descriptor %q is missing", searchQueryOperationID)
}

func resolveString(value any) string {
	text, _ := value.(string)
	return strings.TrimSpace(text)
}

func exactInteger(value any) (int, error) {
	switch typed := value.(type) {
	case int:
		return typed, nil
	case int64:
		return int(typed), nil
	case float64:
		integer := int(typed)
		if float64(integer) == typed {
			return integer, nil
		}
	case json.Number:
		integer, err := typed.Int64()
		return int(integer), err
	}
	return 0, errors.New("must be an exact integer")
}

func canonicalSHA256(value string) bool {
	value = strings.TrimSpace(value)
	if len(value) != 71 || !strings.HasPrefix(value, "sha256:") {
		return false
	}
	for _, character := range strings.TrimPrefix(value, "sha256:") {
		if !strings.ContainsRune("0123456789abcdef", character) {
			return false
		}
	}
	return true
}
