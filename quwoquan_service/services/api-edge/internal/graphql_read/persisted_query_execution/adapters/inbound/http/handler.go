package httpadapter

import (
	"encoding/json"
	"errors"
	"io"
	"mime"
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	graphqlgenerated "quwoquan_service/services/api-edge/generated/graphql_read/persisted_query_execution"
	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/application"
)

const maxRequestBodyBytes = 72 * 1024

type Handler struct {
	service *application.Service
}

func NewHandler(service *application.Service) *Handler {
	if service == nil {
		panic("persisted GraphQL application service is required")
	}
	return &Handler{service: service}
}

type persistedQueryDescriptor struct {
	Version    int    `json:"version"`
	SHA256Hash string `json:"sha256Hash"`
}

type requestExtensions struct {
	PersistedQuery persistedQueryDescriptor `json:"persistedQuery"`
}

type graphQLRequest struct {
	Query         json.RawMessage   `json:"query,omitempty"`
	OperationName string            `json:"operationName,omitempty"`
	Variables     json.RawMessage   `json:"variables,omitempty"`
	Extensions    requestExtensions `json:"extensions"`
}

type graphQLResponse struct {
	Data json.RawMessage `json:"data"`
}

func (handler *Handler) ServeHTTP(response http.ResponseWriter, request *http.Request) {
	response.Header().Set("Cache-Control", "no-store")
	if request.Method != http.MethodPost {
		response.Header().Set("Allow", http.MethodPost)
		writeInvalid(response, request, "persisted GraphQL only accepts POST")
		return
	}
	mediaType, _, err := mime.ParseMediaType(request.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		writeInvalid(response, request, "persisted GraphQL requires application/json")
		return
	}
	wireRequest, err := decodeRequest(response, request)
	if err != nil {
		writeInvalid(response, request, "persisted GraphQL request decoding failed")
		return
	}
	if wireRequest.Query != nil {
		writeInvalid(response, request, "query text and APQ registration are forbidden")
		return
	}
	if wireRequest.Extensions.PersistedQuery.Version != 1 ||
		strings.TrimSpace(wireRequest.Extensions.PersistedQuery.SHA256Hash) == "" {
		writeInvalid(response, request, "persisted query extension version/hash is invalid")
		return
	}
	result, err := handler.service.Execute(request.Context(), application.QueryRequest{
		SHA256Hash:    wireRequest.Extensions.PersistedQuery.SHA256Hash,
		OperationName: wireRequest.OperationName,
		Variables:     wireRequest.Variables,
	})
	if err != nil {
		writeApplicationError(response, request, err)
		return
	}
	response.Header().Set("Content-Type", "application/json; charset=utf-8")
	response.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(response).Encode(graphQLResponse{Data: result.Data})
}

func decodeRequest(response http.ResponseWriter, request *http.Request) (graphQLRequest, error) {
	body := http.MaxBytesReader(response, request.Body, maxRequestBodyBytes)
	defer body.Close()
	decoder := json.NewDecoder(body)
	decoder.DisallowUnknownFields()
	var wireRequest graphQLRequest
	if err := decoder.Decode(&wireRequest); err != nil {
		return graphQLRequest{}, err
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return graphQLRequest{}, errors.New("request must contain exactly one JSON object")
	}
	return wireRequest, nil
}

func writeApplicationError(response http.ResponseWriter, request *http.Request, err error) {
	var appError *rterr.AppError
	switch {
	case errors.Is(err, application.ErrUnknownQuery):
		appError = graphqlgenerated.AppErrorFromPersistedQueryUnknown("persisted query hash not registered")
	case errors.Is(err, application.ErrForbidden):
		appError = graphqlgenerated.AppErrorFromGraphqlQueryForbidden("registry-bound authorization denied")
	case errors.Is(err, application.ErrOwnerUnavailable):
		appError = graphqlgenerated.AppErrorFromGraphqlOwnerUnavailable("registered owner executor unavailable")
	default:
		appError = graphqlgenerated.AppErrorFromGraphqlRequestInvalid("persisted query request rejected")
	}
	rterr.WriteHTTPError(response, appError, rterr.HTTPWriteOptionsFromRequest(request))
}

func writeInvalid(response http.ResponseWriter, request *http.Request, debugMessage string) {
	rterr.WriteHTTPError(
		response,
		graphqlgenerated.AppErrorFromGraphqlRequestInvalid(debugMessage),
		rterr.HTTPWriteOptionsFromRequest(request),
	)
}
