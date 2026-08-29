package graphql

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
	"regexp"
	"strings"
	"unicode"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

const (
	InternalGraphQLPath    = "/internal/graphql"
	RequiredServiceSubject = "service:api-edge"
	RequiredServiceScope   = "content.post.graphql.read"
	contractGraphHeader    = "X-Contract-Graph-SHA256"
	maxRequestBytes        = 64 * 1024
	maxPostIDBytes         = 1024
	maxSemanticRows        = 30
	maxMediaRows           = 20
	maxArticleAssetRows    = 20
	maxArticleEntityRows   = 30
)

var canonicalDigestPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)

type persistedOperation struct {
	name        string
	operationID string
	hash        string
	rootField   string
	project     func(postports.PostDetailSlice) (any, error)
}

var persistedOperations = map[string]persistedOperation{
	"ContentPostDetailBase": {
		name:        "ContentPostDetailBase",
		operationID: "content.post.GetPost",
		hash:        "3a73f535735fcbb64f7de0db524e9dab2ca1f41d7f1fec91c68053dfde5bc80f",
		rootField:   "contentPostDetailBase",
		project:     projectContentPostDetailBase,
	},
	"ContentPostDetailSemantic": {
		name:        "ContentPostDetailSemantic",
		operationID: "content.post.GetPostSemantic",
		hash:        "b425b396c13494d91b0e970d0e9c2328d07d549c492bd76537dace26ea74aa04",
		rootField:   "contentPostDetailSemantic",
		project:     projectContentPostDetailSemantic,
	},
	"ContentPostDetailMedia": {
		name:        "ContentPostDetailMedia",
		operationID: "content.post.GetPostMedia",
		hash:        "2251d9dca6cc14a77ff40eb630223df0b432095a98c7bd3f9f72d2e8d0752c18",
		rootField:   "contentPostDetailMedia",
		project:     projectContentPostDetailMedia,
	},
	"ContentPostDetailArticleRenderAssets": {
		name:        "ContentPostDetailArticleRenderAssets",
		operationID: "content.post.GetPostArticleRenderAssets",
		hash:        "119359eb546ba50284ad676377ca69138129ca01d605688310292ca156848b38",
		rootField:   "contentPostDetailArticleRenderAssets",
		project:     projectContentPostDetailArticleRenderAssets,
	},
	"ContentPostDetailArticleEntities": {
		name:        "ContentPostDetailArticleEntities",
		operationID: "content.post.GetPostArticleEntities",
		hash:        "c9206041dca121c2df985c47f57601ccbc256047ade5e4496b2274fd9f9d02fa",
		rootField:   "contentPostDetailArticleEntities",
		project:     projectContentPostDetailArticleEntities,
	},
}

// PersistedOperationAuthoringBinding is the source-owned identity needed to
// prove that the checked-in YAML/document pair and the handler's executable
// dispatch table are the same closed set. It is consumed by the source-bound
// registry gate; request execution continues to use persistedOperations.
type PersistedOperationAuthoringBinding struct {
	OperationName        string
	CanonicalOperationID string
	SHA256Hash           string
	RootField            string
}

// ValidatePersistedOperationAuthoringBindings rejects a missing, extra, or
// drifted authoring binding. This keeps the gate on the same dispatch table as
// ServeHTTP instead of validating a second test-only runtime registry.
func ValidatePersistedOperationAuthoringBindings(bindings []PersistedOperationAuthoringBinding) error {
	if len(bindings) != len(persistedOperations) {
		return fmt.Errorf("content post persisted operation authoring count=%d runtime count=%d", len(bindings), len(persistedOperations))
	}
	seen := make(map[string]struct{}, len(bindings))
	for _, source := range bindings {
		if _, duplicate := seen[source.OperationName]; duplicate {
			return fmt.Errorf("content post persisted operation authoring duplicates %s", source.OperationName)
		}
		seen[source.OperationName] = struct{}{}
		runtimeBinding, exists := persistedOperations[source.OperationName]
		if !exists || runtimeBinding.name != source.OperationName ||
			runtimeBinding.operationID != source.CanonicalOperationID ||
			runtimeBinding.hash != source.SHA256Hash || runtimeBinding.rootField != source.RootField {
			return fmt.Errorf("content post persisted operation %s does not match its executable runtime binding", source.OperationName)
		}
	}
	return nil
}

type postQueryFacade interface {
	GetPost(context.Context, postports.PostDetailQuery) (postports.PostDetailSlice, error)
}

// InternalPersistedHandler is the ContentPost owner read transport used only
// by API Edge's signed persisted GraphQL bundle. Every operation is an exact
// object-owned hash; query text, mutation, online APQ and REST fallback are
// deliberately outside this transport.
type InternalPersistedHandler struct {
	query               postQueryFacade
	contractGraphSHA256 string
}

func NewInternalPersistedHandler(
	query *postapp.PostQueryFacade,
	contractGraphSHA256 string,
) (*InternalPersistedHandler, error) {
	contractGraphSHA256 = strings.TrimSpace(contractGraphSHA256)
	if query == nil {
		return nil, errors.New("content post internal GraphQL query facade is required")
	}
	if !canonicalDigestPattern.MatchString(contractGraphSHA256) {
		return nil, errors.New("content post internal GraphQL ContractGraph SHA-256 is invalid")
	}
	return &InternalPersistedHandler{query: query, contractGraphSHA256: contractGraphSHA256}, nil
}

func (handler *InternalPersistedHandler) ServeHTTP(
	response http.ResponseWriter,
	request *http.Request,
) {
	if handler == nil || handler.query == nil {
		writeError(response, request, contentgenerated.AppErrorFromInternalError(
			"content post internal GraphQL handler is not configured",
		))
		return
	}
	if request.Method != http.MethodPost || request.URL.Path != InternalGraphQLPath {
		writeError(response, request, contentgenerated.AppErrorFromInvalidArgument(
			"internal GraphQL transport only accepts POST /internal/graphql",
		))
		return
	}
	mediaType, _, err := mime.ParseMediaType(request.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		writeError(response, request, contentgenerated.AppErrorFromInvalidArgument(
			"internal GraphQL request must use application/json",
		))
		return
	}
	principal, ok := trustedAPIEdgePrincipal(request.Context())
	if !ok {
		writeError(response, request, contentgenerated.AppErrorFromUnauthorized(
			"exact trusted api-edge service principal and scope are required",
		))
		return
	}
	if request.Header.Get(contractGraphHeader) != handler.contractGraphSHA256 {
		writeError(response, request, contentgenerated.AppErrorFromInvalidArgument(
			"internal GraphQL ContractGraph binding does not match runtime",
		))
		return
	}
	payload, err := decodePersistedRequest(request.Body)
	if err != nil {
		writeError(response, request, contentgenerated.AppErrorFromInvalidArgument(err.Error()))
		return
	}
	binding, err := payload.validate()
	if err != nil {
		writeError(response, request, contentgenerated.AppErrorFromInvalidArgument(err.Error()))
		return
	}
	invocation, _ := operation.FromContext(request.Context())
	invocation.OperationID = binding.operationID
	invocation.Actor = principal.Actor
	detail, err := handler.query.GetPost(
		operation.WithContext(request.Context(), invocation),
		postports.NewPostDetailQuery(
			postports.NewPostID(payload.Variables.PostID),
			postports.ViewerContext{},
		),
	)
	if err != nil {
		writeError(response, request, err)
		return
	}
	projected, err := binding.project(detail)
	if err != nil {
		writeError(response, request, contentgenerated.AppErrorFromInternalError(err.Error()))
		return
	}
	response.Header().Set("Content-Type", "application/json; charset=utf-8")
	response.Header().Set(contractGraphHeader, handler.contractGraphSHA256)
	response.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(response).Encode(map[string]any{
		"data": map[string]any{binding.rootField: projected},
	})
}

type persistedRequest struct {
	OperationName string              `json:"operationName"`
	Variables     persistedVariables  `json:"variables"`
	Extensions    persistedExtensions `json:"extensions"`
}

type persistedVariables struct {
	PostID string `json:"postId"`
}
type persistedExtensions struct {
	PersistedQuery persistedDescriptor `json:"persistedQuery"`
}
type persistedDescriptor struct {
	Version    int    `json:"version"`
	SHA256Hash string `json:"sha256Hash"`
}

func decodePersistedRequest(body io.Reader) (persistedRequest, error) {
	encoded, err := io.ReadAll(io.LimitReader(body, maxRequestBytes+1))
	if err != nil {
		return persistedRequest{}, fmt.Errorf("read persisted GraphQL request: %w", err)
	}
	if len(encoded) > maxRequestBytes {
		return persistedRequest{}, errors.New("persisted GraphQL request exceeds size limit")
	}
	decoder := json.NewDecoder(bytes.NewReader(encoded))
	decoder.DisallowUnknownFields()
	var payload persistedRequest
	if err := decoder.Decode(&payload); err != nil {
		return persistedRequest{}, fmt.Errorf("decode exact persisted GraphQL request: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return persistedRequest{}, errors.New("persisted GraphQL request must contain one JSON object")
	}
	return payload, nil
}

func (request persistedRequest) validate() (persistedOperation, error) {
	binding, ok := persistedOperations[request.OperationName]
	if !ok {
		return persistedOperation{}, errors.New("persisted GraphQL operationName is not in the content.post detail bundle")
	}
	if request.Extensions.PersistedQuery.Version != 1 || request.Extensions.PersistedQuery.SHA256Hash != binding.hash {
		return persistedOperation{}, errors.New("persisted GraphQL hash is not the exact content.post.GetPost bundle binding")
	}
	postID := request.Variables.PostID
	if postID == "" || strings.TrimSpace(postID) != postID || len(postID) > maxPostIDBytes {
		return persistedOperation{}, errors.New("persisted GraphQL postId must be a non-blank bounded string")
	}
	for _, value := range postID {
		if unicode.IsControl(value) {
			return persistedOperation{}, errors.New("persisted GraphQL postId contains control characters")
		}
	}
	return binding, nil
}

func trustedAPIEdgePrincipal(ctx context.Context) (rtauth.Principal, bool) {
	principal, ok := rtauth.PrincipalFromContext(ctx)
	if !ok || strings.TrimSpace(principal.Subject) != RequiredServiceSubject ||
		!contains(principal.Roles, "service") || !contains(strings.Fields(principal.Scope), RequiredServiceScope) {
		return rtauth.Principal{}, false
	}
	return principal, true
}

func contains(values []string, expected string) bool {
	for _, value := range values {
		if strings.TrimSpace(value) == expected {
			return true
		}
	}
	return false
}

func writeError(response http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(response, err, rterr.HTTPWriteOptionsFromRequest(request))
}
