package http

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	descriptorerrors "quwoquan_service/services/assistant-service/generated/assistant/domain_reader_descriptor"
	"quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/application"
)

const (
	getDescriptorOperation   = "assistant.domain_reader_descriptor.GetDomainReaderDescriptor"
	listDescriptorsOperation = "assistant.domain_reader_descriptor.ListDomainReaderDescriptors"
)

// RouteDescriptors are injected from the generated ContractGraph registry by
// the composition root. The adapter never owns a duplicate route or security
// policy table.
type RouteDescriptors struct {
	Get  rtauth.OperationSecurityDescriptor
	List rtauth.OperationSecurityDescriptor
}

func NewRouteDescriptors(
	descriptors []rtauth.OperationSecurityDescriptor,
) (RouteDescriptors, error) {
	var routes RouteDescriptors
	for _, descriptor := range descriptors {
		switch descriptor.CanonicalOperationID {
		case getDescriptorOperation:
			if routes.Get.CanonicalOperationID != "" {
				return RouteDescriptors{}, fmt.Errorf("duplicate %s descriptor", getDescriptorOperation)
			}
			routes.Get = descriptor
		case listDescriptorsOperation:
			if routes.List.CanonicalOperationID != "" {
				return RouteDescriptors{}, fmt.Errorf("duplicate %s descriptor", listDescriptorsOperation)
			}
			routes.List = descriptor
		}
	}
	for _, descriptor := range []rtauth.OperationSecurityDescriptor{routes.Get, routes.List} {
		if descriptor.CanonicalOperationID == "" ||
			strings.TrimSpace(descriptor.ContractGraphSHA256) == "" ||
			strings.ToUpper(strings.TrimSpace(descriptor.Method)) != http.MethodGet ||
			strings.TrimSpace(descriptor.PathTemplate) == "" ||
			descriptor.CommercialStatus != "ready" ||
			descriptor.OperationKind != "query" ||
			descriptor.AuthMode != "required" ||
			descriptor.Principal != "service" ||
			!contains(descriptor.Scopes, "assistant.domain_reader.read") {
			return RouteDescriptors{}, fmt.Errorf("domain reader route descriptor is incomplete")
		}
	}
	return routes, nil
}

func contains(values []string, wanted string) bool {
	for _, value := range values {
		if strings.TrimSpace(value) == wanted {
			return true
		}
	}
	return false
}

type Handler struct {
	queries *application.QueryService
	routes  RouteDescriptors
}

func NewHandler(
	queries *application.QueryService,
	routes RouteDescriptors,
) (*Handler, error) {
	validated, err := NewRouteDescriptors([]rtauth.OperationSecurityDescriptor{
		routes.Get,
		routes.List,
	})
	if err != nil {
		return nil, err
	}
	if queries == nil {
		return nil, fmt.Errorf("domain reader query service is required")
	}
	return &Handler{queries: queries, routes: validated}, nil
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc(
		handler.routes.Get.Method+" "+handler.routes.Get.PathTemplate,
		handler.handleGetDescriptor,
	)
	mux.HandleFunc(
		handler.routes.List.Method+" "+handler.routes.List.PathTemplate,
		handler.handleListDescriptors,
	)
}

// Routes is useful for isolated API integration tests. Service composition may
// call RegisterRoutes on its already-authorized shared mux instead.
func (handler *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)
	return rtauth.RequireGeneratedOperationAuthorization(
		[]rtauth.OperationSecurityDescriptor{handler.routes.Get, handler.routes.List},
	)(mux)
}

func (handler *Handler) handleGetDescriptor(
	writer http.ResponseWriter,
	request *http.Request,
) {
	view, err := handler.queries.GetDescriptor(
		request.Context(),
		application.GetDescriptorQuery{
			DescriptorID: request.PathValue("descriptorId"),
		},
	)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	writeJSON(writer, http.StatusOK, view)
}

func (handler *Handler) handleListDescriptors(
	writer http.ResponseWriter,
	request *http.Request,
) {
	limit, err := parseLimit(request, 100)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	view, err := handler.queries.ListDescriptors(
		request.Context(),
		application.ListDescriptorsQuery{Limit: limit},
	)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	writeJSON(writer, http.StatusOK, view)
}

func parseLimit(request *http.Request, fallback int) (int, error) {
	values, present := request.URL.Query()["limit"]
	if !present {
		return fallback, nil
	}
	if len(values) != 1 || strings.TrimSpace(values[0]) == "" {
		return 0, descriptorerrors.AppErrorFromDomainReaderInvalidArgument(
			"limit must be provided exactly once when present",
		)
	}
	limit, err := strconv.Atoi(strings.TrimSpace(values[0]))
	if err != nil || limit <= 0 || limit > 100 {
		return 0, descriptorerrors.AppErrorFromDomainReaderInvalidArgument(
			"limit must be an integer between 1 and 100",
		)
	}
	return limit, nil
}

func writeJSON(writer http.ResponseWriter, status int, payload any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(payload)
}

func writeHTTPError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
