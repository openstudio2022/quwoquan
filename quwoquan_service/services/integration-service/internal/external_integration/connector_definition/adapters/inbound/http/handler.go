package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	definitionerrors "quwoquan_service/services/integration-service/generated/external_integration/connector_definition"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_definition/application"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
)

const (
	publishOperation = "integration.connector_definition.PublishConnectorDefinition"
	listOperation    = "integration.connector_definition.ListConnectorDefinitions"
	getOperation     = "integration.connector_definition.GetConnectorDefinition"
)

type Handler struct {
	commands *application.CommandFacade
	queries  *application.QueryFacade
}

func NewHandler(
	commands *application.CommandFacade,
	queries *application.QueryFacade,
) *Handler {
	return &Handler{commands: commands, queries: queries}
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	publish := mustOperationDescriptor(publishOperation)
	list := mustOperationDescriptor(listOperation)
	get := mustOperationDescriptor(getOperation)
	mux.HandleFunc(publish.Method+" "+publish.PathTemplate, handler.handlePublish)
	mux.HandleFunc(list.Method+" "+list.PathTemplate, handler.handleList)
	mux.HandleFunc(get.Method+" "+get.PathTemplate, handler.handleGet)
}

func (handler *Handler) handlePublish(writer http.ResponseWriter, request *http.Request) {
	var body model.Definition
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 96<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeHTTPError(writer, request, definitionerrors.AppErrorFromConnectorDefinitionInvalidArgument(err.Error()))
		return
	}
	body.ConnectorID = strings.TrimSpace(request.PathValue("connectorId"))
	result, err := handler.commands.Publish(request.Context(), model.PublishInput{
		Definition:     body,
		IdempotencyKey: strings.TrimSpace(request.Header.Get("Idempotency-Key")),
	})
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err, true))
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"definition": result.Definition,
		"replayed":   result.Replayed,
	})
}

func (handler *Handler) handleList(writer http.ResponseWriter, request *http.Request) {
	if err := requireAccount(request); err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	limit, err := parseLimit(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	items, err := handler.queries.List(
		request.Context(),
		strings.TrimSpace(request.URL.Query().Get("capability")),
		limit,
	)
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err, false))
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{"items": items})
}

func (handler *Handler) handleGet(writer http.ResponseWriter, request *http.Request) {
	if err := requireAccount(request); err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	definition, err := handler.queries.Get(
		request.Context(),
		strings.TrimSpace(request.PathValue("connectorId")),
	)
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err, false))
		return
	}
	writeJSON(writer, http.StatusOK, definition)
}

func requireAccount(request *http.Request) error {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if ok && strings.TrimSpace(principal.Actor.AccountID) != "" {
		return nil
	}
	return definitionerrors.AppErrorFromConnectorUnauthorized(
		"ConnectorDefinition query requires a verified account principal",
	)
}

func parseLimit(request *http.Request) (int, error) {
	raw := strings.TrimSpace(request.URL.Query().Get("limit"))
	if raw == "" {
		return 64, nil
	}
	limit, err := strconv.Atoi(raw)
	if err != nil || limit <= 0 || limit > 100 {
		return 0, definitionerrors.AppErrorFromConnectorInvalidArgument(
			"limit must be an integer between 1 and 100",
		)
	}
	return limit, nil
}

func mapDomainError(err error, publish bool) error {
	switch {
	case errors.Is(err, model.ErrInvalidArgument):
		if publish {
			return definitionerrors.AppErrorFromConnectorDefinitionInvalidArgument(err.Error())
		}
		return definitionerrors.AppErrorFromConnectorInvalidArgument(err.Error())
	case errors.Is(err, model.ErrNotFound):
		return definitionerrors.AppErrorFromConnectorDefinitionNotFound(err.Error())
	case errors.Is(err, model.ErrIdempotencyConflict):
		return definitionerrors.AppErrorFromConnectorDefinitionIdempotencyConflict(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return definitionerrors.AppErrorFromConnectorCatalogUnavailable(err.Error())
	}
}

func mustOperationDescriptor(canonicalOperationID string) rtauth.OperationSecurityDescriptor {
	for _, descriptor := range operationsecurity.ForDomain("integration") {
		if descriptor.CanonicalOperationID == canonicalOperationID {
			return descriptor
		}
	}
	panic("missing generated operation descriptor: " + canonicalOperationID)
}

func writeJSON(writer http.ResponseWriter, status int, payload any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(payload)
}

func writeHTTPError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
