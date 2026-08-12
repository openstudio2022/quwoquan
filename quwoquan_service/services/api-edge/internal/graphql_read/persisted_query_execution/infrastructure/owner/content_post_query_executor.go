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
	contentPostExecutorKey = "content.post.getPost"
	contentPostObjectID    = "content.post"
	maxOwnerResponseBytes  = 4 * 1024 * 1024
	maxPostIDBytes         = 1024
	contentPostOwnerScope  = "content.post.graphql.read"
)

type contentBundleBinding struct {
	operationName        string
	canonicalOperationID string
	hash                 string
	rootField            string
	contentTypes         map[string]struct{}
	response             objectSpec
}

var contentBundleBindings = map[string]contentBundleBinding{
	"ContentPostDetailBase": newContentBundleBinding(
		"ContentPostDetailBase", "content.post.GetPost", "3c1481366f84401aa2d89280925d5943bf040f7c94cf757fb5cc219f00a7f71b",
		"contentPostDetailBase", []string{"article", "image", "micro", "video"}, baseResponseSpec(),
	),
	"ContentPostDetailSemantic": newContentBundleBinding(
		"ContentPostDetailSemantic", "content.post.GetPostSemantic", "b425b396c13494d91b0e970d0e9c2328d07d549c492bd76537dace26ea74aa04",
		"contentPostDetailSemantic", []string{"article", "image", "micro", "video"}, semanticResponseSpec(),
	),
	"ContentPostDetailMedia": newContentBundleBinding(
		"ContentPostDetailMedia", "content.post.GetPostMedia", "2251d9dca6cc14a77ff40eb630223df0b432095a98c7bd3f9f72d2e8d0752c18",
		"contentPostDetailMedia", []string{"image", "video"}, mediaResponseSpec(),
	),
	"ContentPostDetailArticleRenderAssets": newContentBundleBinding(
		"ContentPostDetailArticleRenderAssets", "content.post.GetPostArticleRenderAssets", "119359eb546ba50284ad676377ca69138129ca01d605688310292ca156848b38",
		"contentPostDetailArticleRenderAssets", []string{"article"}, articleRenderAssetsResponseSpec(),
	),
	"ContentPostDetailArticleEntities": newContentBundleBinding(
		"ContentPostDetailArticleEntities", "content.post.GetPostArticleEntities", "c9206041dca121c2df985c47f57601ccbc256047ade5e4496b2274fd9f9d02fa",
		"contentPostDetailArticleEntities", []string{"article"}, articleEntitiesResponseSpec(),
	),
}

func newContentBundleBinding(
	operationName, canonicalOperationID, hash, rootField string,
	contentTypes []string,
	response objectSpec,
) contentBundleBinding {
	allowed := make(map[string]struct{}, len(contentTypes))
	for _, contentType := range contentTypes {
		allowed[contentType] = struct{}{}
	}
	return contentBundleBinding{operationName: operationName, canonicalOperationID: canonicalOperationID, hash: hash, rootField: rootField,
		contentTypes: allowed, response: response}
}

func ContentPostOwnerReadScope() string { return contentPostOwnerScope }

// ValidateContentPostBundleEntry binds API Edge authorization and owner
// execution to the same operation/hash/object truth.
func ValidateContentPostBundleEntry(entry domain.Entry) error {
	_, err := validateEntry(entry)
	return err
}

// ContentPostQueryExecutor executes one signed member of the object-owned
// ContentPostDetail bundle. The owner response is recursively checked against
// that operation's exact GraphQL selection before it can cross API Edge.
type ContentPostQueryExecutor struct {
	stableOrigin        url.URL
	candidateOrigin     *url.URL
	client              *http.Client
	credentials         rtauth.ServiceAuthorizationProvider
	contractGraphSHA256 string
}

func NewContentPostQueryExecutor(
	stableOrigin *url.URL,
	candidateOrigin *url.URL,
	client *http.Client,
	contractGraphSHA256 string,
	credentials rtauth.ServiceAuthorizationProvider,
) (*ContentPostQueryExecutor, error) {
	stable, err := validateOwnerOrigin("stable", stableOrigin)
	if err != nil {
		return nil, err
	}
	var candidate *url.URL
	if candidateOrigin != nil {
		candidate, err = validateOwnerOrigin("candidate", candidateOrigin)
		if err != nil {
			return nil, err
		}
	}
	contractGraphSHA256 = strings.TrimSpace(contractGraphSHA256)
	if contractGraphSHA256 == "" {
		return nil, errors.New("content post executor ContractGraph SHA-256 is required")
	}
	if client == nil {
		client = &http.Client{Timeout: 3 * time.Second}
	}
	if credentials == nil {
		return nil, errors.New("content post owner service credentials are required")
	}
	clientCopy := *client
	clientCopy.CheckRedirect = func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }
	return &ContentPostQueryExecutor{stableOrigin: *stable, candidateOrigin: candidate,
		client: &clientCopy, credentials: credentials, contractGraphSHA256: contractGraphSHA256}, nil
}

func (executor *ContentPostQueryExecutor) Execute(
	ctx context.Context,
	entry domain.Entry,
	variables map[string]any,
) (application.ExecutionResult, error) {
	if executor == nil {
		return application.ExecutionResult{}, errors.New("content post executor is nil")
	}
	binding, err := validateEntry(entry)
	if err != nil {
		return application.ExecutionResult{}, err
	}
	postID, err := validateVariables(variables)
	if err != nil {
		return application.ExecutionResult{}, err
	}
	origin, err := executor.originForTarget(rolloutapp.TargetFromContext(ctx))
	if err != nil {
		return application.ExecutionResult{}, err
	}
	payload, err := json.Marshal(internalPersistedRequest{
		OperationName: entry.OperationName,
		Variables:     map[string]any{"postId": postID},
		Extensions: internalPersistedExtensions{PersistedQuery: internalPersistedDescriptor{
			Version: 1, SHA256Hash: entry.SHA256Hash,
		}},
	})
	if err != nil {
		return application.ExecutionResult{}, fmt.Errorf("encode content post owner request: %w", err)
	}
	endpoint := ownerGraphQLURL(origin)
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint.String(), bytes.NewReader(payload))
	if err != nil {
		return application.ExecutionResult{}, fmt.Errorf("create content post owner request: %w", err)
	}
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Contract-Graph-SHA256", executor.contractGraphSHA256)
	authorization, err := executor.credentials.AuthorizationHeader(ctx)
	if err != nil {
		return application.ExecutionResult{}, fmt.Errorf("sign content post owner request: %w", err)
	}
	if !strings.HasPrefix(authorization, "Bearer ") || strings.TrimSpace(strings.TrimPrefix(authorization, "Bearer ")) == "" {
		return application.ExecutionResult{}, errors.New("content post owner credentials returned an invalid authorization header")
	}
	request.Header.Set("Authorization", authorization)
	ownerResponse, err := executor.client.Do(request)
	if err != nil {
		return application.ExecutionResult{}, fmt.Errorf("execute content post owner request: %w", err)
	}
	defer ownerResponse.Body.Close()
	if ownerResponse.StatusCode != http.StatusOK {
		return application.ExecutionResult{}, fmt.Errorf("content post owner returned status %d", ownerResponse.StatusCode)
	}
	mediaType, _, err := mime.ParseMediaType(ownerResponse.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		return application.ExecutionResult{}, errors.New("content post owner response must use application/json")
	}
	body, err := io.ReadAll(io.LimitReader(ownerResponse.Body, maxOwnerResponseBytes+1))
	if err != nil {
		return application.ExecutionResult{}, fmt.Errorf("read content post owner response: %w", err)
	}
	if len(body) > maxOwnerResponseBytes {
		return application.ExecutionResult{}, errors.New("content post owner response exceeds size limit")
	}
	if ownerResponse.Header.Get("X-Contract-Graph-SHA256") != executor.contractGraphSHA256 {
		return application.ExecutionResult{}, errors.New("content post owner response ContractGraph binding drifted")
	}
	detail, err := decodeOwnerGraphQLData(body, binding)
	if err != nil {
		return application.ExecutionResult{}, fmt.Errorf("decode content post owner GraphQL data: %w", err)
	}
	if detail["postId"] != postID {
		return application.ExecutionResult{}, errors.New("owner response postId does not match requested postId")
	}
	contentType, ok := detail["contentType"].(string)
	if !ok {
		return application.ExecutionResult{}, errors.New("owner response contentType is invalid")
	}
	if _, ok := binding.contentTypes[contentType]; !ok {
		return application.ExecutionResult{}, fmt.Errorf("bundle slice %s does not apply to contentType=%s", binding.operationName, contentType)
	}
	data, err := json.Marshal(map[string]any{binding.rootField: detail})
	if err != nil {
		return application.ExecutionResult{}, fmt.Errorf("encode content post GraphQL data: %w", err)
	}
	return application.ExecutionResult{Data: data, Usage: application.ExecutionUsage{
		OwnerCalls: 1, BatchKeys: 1, ResponseBytes: len(data),
	}}, nil
}

type internalPersistedRequest struct {
	OperationName string                      `json:"operationName"`
	Variables     map[string]any              `json:"variables"`
	Extensions    internalPersistedExtensions `json:"extensions"`
}
type internalPersistedExtensions struct {
	PersistedQuery internalPersistedDescriptor `json:"persistedQuery"`
}
type internalPersistedDescriptor struct {
	Version    int    `json:"version"`
	SHA256Hash string `json:"sha256Hash"`
}

func validateOwnerOrigin(name string, origin *url.URL) (*url.URL, error) {
	if origin == nil || (origin.Scheme != "http" && origin.Scheme != "https") || origin.Host == "" {
		return nil, fmt.Errorf("content post %s origin must be an absolute HTTP(S) URL", name)
	}
	if origin.User != nil || origin.RawQuery != "" || origin.Fragment != "" || (origin.Path != "" && origin.Path != "/") {
		return nil, fmt.Errorf("content post %s upstream must be an origin URL", name)
	}
	copy := *origin
	copy.Path = ""
	copy.RawPath = ""
	return &copy, nil
}

func (executor *ContentPostQueryExecutor) originForTarget(target rolloutdomain.Target) (*url.URL, error) {
	switch target {
	case rolloutdomain.TargetStable:
		return &executor.stableOrigin, nil
	case rolloutdomain.TargetCandidate:
		if executor.candidateOrigin == nil {
			return nil, errors.New("content post candidate origin is not configured")
		}
		return executor.candidateOrigin, nil
	default:
		return nil, fmt.Errorf("unsupported content post rollout target %q", target)
	}
}

func validateEntry(entry domain.Entry) (contentBundleBinding, error) {
	binding, ok := contentBundleBindings[entry.OperationName]
	if !ok || entry.SHA256Hash != binding.hash || entry.ExecutorKey != contentPostExecutorKey ||
		entry.OperationType != domain.OperationTypeQuery || entry.CanonicalOperationID != binding.canonicalOperationID ||
		len(entry.ObjectIDs) != 1 || entry.ObjectIDs[0] != contentPostObjectID {
		return contentBundleBinding{}, errors.New("persisted query entry is not an exact content.post GetPost bundle binding")
	}
	return binding, nil
}

func validateVariables(variables map[string]any) (string, error) {
	if len(variables) != 1 {
		return "", errors.New("content post query requires exactly the postId variable")
	}
	postID, ok := variables["postId"].(string)
	if !ok || postID == "" || strings.TrimSpace(postID) != postID || len(postID) > maxPostIDBytes {
		return "", errors.New("content post query postId must be a non-blank bounded string")
	}
	for _, value := range postID {
		if unicode.IsControl(value) {
			return "", errors.New("content post query postId contains control characters")
		}
	}
	return postID, nil
}

func ownerGraphQLURL(origin *url.URL) url.URL {
	endpoint := *origin
	endpoint.Path = "/internal/graphql"
	endpoint.RawPath = ""
	return endpoint
}
