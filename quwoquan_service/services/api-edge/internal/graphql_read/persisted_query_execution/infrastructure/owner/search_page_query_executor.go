package owner

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
	"strconv"
	"strings"
	"time"
	"unicode"

	rtauth "quwoquan_service/runtime/auth"
	rolloutapp "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
	rolloutdomain "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/domain"
	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/application"
	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/domain"
)

const (
	searchPageExecutorKey          = "search.searchIndexView.searchPage"
	searchPageCanonicalOperationID = "gateway.persisted_query_execution.SearchPage"
	searchPageOperationName        = "SearchPage"
	searchPageObjectID             = "gateway.persisted_query_execution"
	searchPageSHA256Hash           = "111b715594655786eba342c5cbebe7ea1338a9cf016ed0f35f54096802583478"
	searchOwnerScope               = "search.search_index_view.graphql.read"
	maxSearchOwnerResponseBytes    = 4 * 1024 * 1024
	maxSearchQueryBytes            = 1024
	maxSearchCursorBytes           = 4096
	maxSearchIdentityBytes         = 1024
	defaultSearchPageSize          = 20
	maximumSearchPageSize          = 20
)

var searchObjectTypeBindings = map[string]string{
	"CIRCLE":          "circle.circle",
	"CIRCLE_GROUP":    "circle.group",
	"CONTENT_POST":    "content.post",
	"ENTITY_HOMEPAGE": "entity.homepage",
	"LOCATION_PLACE":  "location.place",
	"USER_PROFILE":    "user.profile",
}

var searchContentTypeBindings = map[string]string{
	"ARTICLE": "article",
	"IMAGE":   "image",
	"VIDEO":   "video",
}

var searchContentTypeBindingsReverse = func() map[string]string {
	reverse := make(map[string]string, len(searchContentTypeBindings))
	for enumValue, canonical := range searchContentTypeBindings {
		reverse[canonical] = enumValue
	}
	return reverse
}()

func SearchOwnerReadScope() string { return searchOwnerScope }

// SearchObjectTypeBindings exposes the GraphQL-enum -> canonical objectType
// bindings so contract tests can pin them against the vocabulary the real
// search-service accepts (rtsearch.CloudSearchableObjectTypes). The historic
// break — the edge sending vocabulary the owner rejects while test stubs
// accepted it — must stay structurally impossible.
func SearchObjectTypeBindings() map[string]string {
	out := make(map[string]string, len(searchObjectTypeBindings))
	for enumValue, canonical := range searchObjectTypeBindings {
		out[enumValue] = canonical
	}
	return out
}

// SearchContentTypeBindings exposes the GraphQL-enum -> canonical contentType
// bindings for the same single-track contract tests.
func SearchContentTypeBindings() map[string]string {
	out := make(map[string]string, len(searchContentTypeBindings))
	for enumValue, canonical := range searchContentTypeBindings {
		out[enumValue] = canonical
	}
	return out
}

func ValidateSearchPageEntry(entry domain.Entry) error {
	if entry.OperationName != searchPageOperationName ||
		entry.SHA256Hash != searchPageSHA256Hash ||
		entry.CanonicalOperationID != searchPageCanonicalOperationID ||
		entry.OperationType != domain.OperationTypeQuery ||
		entry.ExecutorKey != searchPageExecutorKey ||
		len(entry.ObjectIDs) != 1 || entry.ObjectIDs[0] != searchPageObjectID {
		return errors.New("persisted query entry is not the exact gateway SearchPage binding")
	}
	return nil
}

type SearchPageQueryExecutor struct {
	stableOrigin        url.URL
	candidateOrigin     *url.URL
	client              *http.Client
	serviceCredentials  rtauth.ServiceAuthorizationProvider
	accountCredentials  rtauth.ServiceAccountAuthorizationProvider
	contractGraphSHA256 string
}

func NewSearchPageQueryExecutor(
	stableOrigin *url.URL,
	candidateOrigin *url.URL,
	client *http.Client,
	contractGraphSHA256 string,
	serviceCredentials rtauth.ServiceAuthorizationProvider,
	accountCredentials rtauth.ServiceAccountAuthorizationProvider,
) (*SearchPageQueryExecutor, error) {
	stable, err := validateSearchOwnerOrigin("stable", stableOrigin)
	if err != nil {
		return nil, err
	}
	var candidate *url.URL
	if candidateOrigin != nil {
		candidate, err = validateSearchOwnerOrigin("candidate", candidateOrigin)
		if err != nil {
			return nil, err
		}
	}
	contractGraphSHA256 = strings.TrimSpace(contractGraphSHA256)
	if contractGraphSHA256 == "" {
		return nil, errors.New("SearchPage executor ContractGraph SHA-256 is required")
	}
	if serviceCredentials == nil || accountCredentials == nil {
		return nil, errors.New("SearchPage owner service and account credentials are required")
	}
	if client == nil {
		// 预算级联：GraphQL 入口给 SearchPage 2000ms，owner client 兜底不得高于
		// 该外层预算（历史 3s 倒挂会让外层已放弃、内层还在计算）。请求本身经
		// NewRequestWithContext 继承上游 deadline，此处只是失配保险。
		client = &http.Client{Timeout: 2 * time.Second}
	}
	clientCopy := *client
	clientCopy.CheckRedirect = func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }
	return &SearchPageQueryExecutor{
		stableOrigin: *stable, candidateOrigin: candidate, client: &clientCopy,
		serviceCredentials: serviceCredentials, accountCredentials: accountCredentials,
		contractGraphSHA256: contractGraphSHA256,
	}, nil
}

func (executor *SearchPageQueryExecutor) Execute(
	ctx context.Context,
	entry domain.Entry,
	variables map[string]any,
) (application.ExecutionResult, error) {
	if executor == nil {
		return application.ExecutionResult{}, errors.New("SearchPage executor is nil")
	}
	if err := ValidateSearchPageEntry(entry); err != nil {
		return application.ExecutionResult{}, err
	}
	input, err := decodeSearchPageInput(variables)
	if err != nil {
		return application.ExecutionResult{}, err
	}
	identity, err := searchRequestIdentityFromContext(ctx)
	if err != nil {
		return application.ExecutionResult{}, err
	}
	origin, err := executor.originForTarget(rolloutapp.TargetFromContext(ctx))
	if err != nil {
		return application.ExecutionResult{}, err
	}
	payload, err := json.Marshal(searchOwnerRequest{
		Query: input.query, Mode: "result", ObjectTypes: input.objectTypes,
		ContentTypes: input.contentTypes,
		Limit:        input.first, Cursor: input.after,
	})
	if err != nil {
		return application.ExecutionResult{}, fmt.Errorf("encode SearchPage owner request: %w", err)
	}
	endpoint := *origin
	endpoint.Path = "/search"
	endpoint.RawPath = ""
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint.String(), bytes.NewReader(payload))
	if err != nil {
		return application.ExecutionResult{}, fmt.Errorf("create SearchPage owner request: %w", err)
	}
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Contract-Graph-SHA256", executor.contractGraphSHA256)
	identity.apply(request.Header)
	authorization, err := executor.authorizationHeader(ctx, identity)
	if err != nil {
		return application.ExecutionResult{}, fmt.Errorf("sign SearchPage owner request: %w", err)
	}
	if !strings.HasPrefix(authorization, "Bearer ") || strings.TrimSpace(strings.TrimPrefix(authorization, "Bearer ")) == "" {
		return application.ExecutionResult{}, errors.New("SearchPage owner credentials returned an invalid authorization header")
	}
	request.Header.Set("Authorization", authorization)
	ownerResponse, err := executor.client.Do(request)
	if err != nil {
		return application.ExecutionResult{}, fmt.Errorf("execute SearchPage owner request: %w", err)
	}
	defer ownerResponse.Body.Close()
	if ownerResponse.StatusCode != http.StatusOK {
		return application.ExecutionResult{}, fmt.Errorf("SearchPage owner returned status %d", ownerResponse.StatusCode)
	}
	mediaType, _, err := mime.ParseMediaType(ownerResponse.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		return application.ExecutionResult{}, errors.New("SearchPage owner response must use application/json")
	}
	if ownerResponse.Header.Get("X-Contract-Graph-SHA256") != executor.contractGraphSHA256 {
		return application.ExecutionResult{}, errors.New("SearchPage owner response ContractGraph binding drifted")
	}
	body, err := io.ReadAll(io.LimitReader(ownerResponse.Body, maxSearchOwnerResponseBytes+1))
	if err != nil {
		return application.ExecutionResult{}, fmt.Errorf("read SearchPage owner response: %w", err)
	}
	if len(body) > maxSearchOwnerResponseBytes {
		return application.ExecutionResult{}, errors.New("SearchPage owner response exceeds size limit")
	}
	page, err := decodeSearchOwnerPage(body, input.first)
	if err != nil {
		return application.ExecutionResult{}, fmt.Errorf("decode SearchPage owner response: %w", err)
	}
	data, err := json.Marshal(map[string]any{"searchPage": page})
	if err != nil {
		return application.ExecutionResult{}, fmt.Errorf("encode SearchPage data: %w", err)
	}
	if len(data) > entry.Cost.MaxResponseBytes || len(data) > entry.CostPlan.MaxResponseBytes {
		return application.ExecutionResult{}, errors.New("SearchPage data exceeds signed response budget")
	}
	return application.ExecutionResult{Data: data, Usage: application.ExecutionUsage{
		OwnerCalls: 1, BatchKeys: 1, ResponseBytes: len(data),
	}}, nil
}

type searchPageInput struct {
	query        string
	first        int
	after        string
	objectTypes  []string
	contentTypes []string
}

func decodeSearchPageInput(variables map[string]any) (searchPageInput, error) {
	if len(variables) != 1 {
		return searchPageInput{}, errors.New("SearchPage requires exactly the input variable")
	}
	raw, ok := variables["input"].(map[string]any)
	if !ok || raw == nil {
		return searchPageInput{}, errors.New("SearchPage input must be an object")
	}
	allowed := map[string]bool{"query": true, "first": true, "after": true, "objectTypes": true, "contentTypes": true}
	for key := range raw {
		if !allowed[key] {
			return searchPageInput{}, fmt.Errorf("SearchPage input field %s is not registered", key)
		}
	}
	query, ok := raw["query"].(string)
	query = strings.TrimSpace(query)
	if !ok || query == "" || len(query) > maxSearchQueryBytes || containsControl(query) {
		return searchPageInput{}, errors.New("SearchPage query must be a non-blank bounded string")
	}
	first := defaultSearchPageSize
	if value, exists := raw["first"]; exists && value != nil {
		parsed, err := exactPositiveInt(value)
		if err != nil || parsed > maximumSearchPageSize {
			return searchPageInput{}, fmt.Errorf("SearchPage first must be within 1..%d", maximumSearchPageSize)
		}
		first = parsed
	}
	after := ""
	if value, exists := raw["after"]; exists && value != nil {
		var valid bool
		after, valid = value.(string)
		if !valid || after == "" || strings.TrimSpace(after) != after || len(after) > maxSearchCursorBytes || containsControl(after) {
			return searchPageInput{}, errors.New("SearchPage after must be an opaque bounded cursor")
		}
	}
	objectTypes, err := decodeSearchEnumList(raw["objectTypes"], "objectTypes", searchObjectTypeBindings)
	if err != nil {
		return searchPageInput{}, err
	}
	contentTypes, err := decodeSearchEnumList(raw["contentTypes"], "contentTypes", searchContentTypeBindings)
	if err != nil {
		return searchPageInput{}, err
	}
	return searchPageInput{
		query: query, first: first, after: after,
		objectTypes: objectTypes, contentTypes: contentTypes,
	}, nil
}

func decodeSearchEnumList(value any, label string, bindings map[string]string) ([]string, error) {
	if value == nil {
		return nil, nil
	}
	items, ok := value.([]any)
	if !ok || len(items) > len(bindings) {
		return nil, fmt.Errorf("SearchPage %s must be a bounded list", label)
	}
	seen := map[string]bool{}
	result := make([]string, 0, len(items))
	for _, item := range items {
		name, ok := item.(string)
		canonical, exists := bindings[name]
		if !ok || !exists || seen[canonical] {
			return nil, fmt.Errorf("SearchPage %s contains an unsupported or duplicate value", label)
		}
		seen[canonical] = true
		result = append(result, canonical)
	}
	return result, nil
}

func exactPositiveInt(value any) (int, error) {
	var raw string
	switch typed := value.(type) {
	case json.Number:
		raw = typed.String()
	case int:
		if typed > 0 {
			return typed, nil
		}
		return 0, errors.New("integer must be positive")
	default:
		return 0, errors.New("value must be an integer")
	}
	if strings.ContainsAny(raw, ".eE+-") || raw == "" {
		return 0, errors.New("value must be a positive integer")
	}
	parsed, err := strconv.Atoi(raw)
	if err != nil || parsed < 1 {
		return 0, errors.New("value must be a positive integer")
	}
	return parsed, nil
}

type searchRequestIdentity struct {
	accountID string
	sessionID string
}

func searchRequestIdentityFromContext(ctx context.Context) (searchRequestIdentity, error) {
	principal, hasPrincipal := rtauth.PrincipalFromContext(ctx)
	if hasPrincipal {
		accountID := strings.TrimSpace(principal.Actor.AccountID)
		if accountID != "" && !strings.HasPrefix(accountID, "service:") {
			if len(accountID) > maxSearchIdentityBytes || containsControl(accountID) {
				return searchRequestIdentity{}, errors.New("SearchPage account identity is invalid")
			}
			return searchRequestIdentity{accountID: accountID}, nil
		}
	}
	sessionID := strings.TrimSpace(application.SearchSessionID(ctx))
	if sessionID == "" || len(sessionID) > maxSearchIdentityBytes || containsControl(sessionID) {
		return searchRequestIdentity{}, errors.New("anonymous SearchPage requires a bounded session identity")
	}
	return searchRequestIdentity{sessionID: sessionID}, nil
}

func (identity searchRequestIdentity) apply(header http.Header) {
	if identity.sessionID != "" {
		header.Set("X-Session-Id", identity.sessionID)
	}
}

func (executor *SearchPageQueryExecutor) authorizationHeader(
	ctx context.Context,
	identity searchRequestIdentity,
) (string, error) {
	if identity.accountID != "" {
		return executor.accountCredentials.AuthorizationHeaderForAccount(ctx, identity.accountID)
	}
	return executor.serviceCredentials.AuthorizationHeader(ctx)
}

func containsControl(value string) bool {
	for _, character := range value {
		if unicode.IsControl(character) {
			return true
		}
	}
	return false
}

func validateSearchOwnerOrigin(name string, origin *url.URL) (*url.URL, error) {
	if origin == nil || (origin.Scheme != "http" && origin.Scheme != "https") || origin.Host == "" {
		return nil, fmt.Errorf("SearchPage %s origin must be an absolute HTTP(S) URL", name)
	}
	if origin.User != nil || origin.RawQuery != "" || origin.Fragment != "" || (origin.Path != "" && origin.Path != "/") {
		return nil, fmt.Errorf("SearchPage %s upstream must be an origin URL", name)
	}
	copy := *origin
	copy.Path = ""
	copy.RawPath = ""
	return &copy, nil
}

func (executor *SearchPageQueryExecutor) originForTarget(target rolloutdomain.Target) (*url.URL, error) {
	switch target {
	case rolloutdomain.TargetStable:
		return &executor.stableOrigin, nil
	case rolloutdomain.TargetCandidate:
		if executor.candidateOrigin == nil {
			return nil, errors.New("SearchPage candidate origin is not configured")
		}
		return executor.candidateOrigin, nil
	default:
		return nil, fmt.Errorf("unsupported SearchPage rollout target %q", target)
	}
}

type searchOwnerRequest struct {
	Query        string   `json:"query"`
	Mode         string   `json:"mode"`
	ObjectTypes  []string `json:"objectTypes,omitempty"`
	ContentTypes []string `json:"contentTypes,omitempty"`
	Limit        int      `json:"limit"`
	Cursor       string   `json:"cursor,omitempty"`
}
