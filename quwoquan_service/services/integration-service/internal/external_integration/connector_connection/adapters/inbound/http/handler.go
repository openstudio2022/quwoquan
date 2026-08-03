package http

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strconv"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	connectionerrors "quwoquan_service/services/integration-service/generated/external_integration/connector_connection"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_connection/application"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
)

const (
	listOperation              = "integration.connector_connection.ListConnectorConnections"
	getOperation               = "integration.connector_connection.GetConnectorConnection"
	createOperation            = "integration.connector_connection.CreateConnectorConnection"
	revokeOperation            = "integration.connector_connection.RevokeConnectorConnection"
	resolveCapabilityOperation = "integration.connector_connection.ResolveConnectorCapabilityGrant"
)

type Handler struct {
	commands *application.CommandFacade
	queries  *application.QueryFacade
}

func NewHandler(commands *application.CommandFacade, queries *application.QueryFacade) *Handler {
	return &Handler{commands: commands, queries: queries}
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	list := mustOperationDescriptor(listOperation)
	get := mustOperationDescriptor(getOperation)
	create := mustOperationDescriptor(createOperation)
	revoke := mustOperationDescriptor(revokeOperation)
	resolveCapability := mustOperationDescriptor(resolveCapabilityOperation)
	mux.HandleFunc(list.Method+" "+list.PathTemplate, handler.handleList)
	mux.HandleFunc(get.Method+" "+get.PathTemplate, handler.handleGet)
	mux.HandleFunc(create.Method+" "+create.PathTemplate, handler.handleCreate)
	mux.HandleFunc(revoke.Method+" "+revoke.PathTemplate, handler.handleRevoke)
	mux.HandleFunc(
		resolveCapability.Method+" "+resolveCapability.PathTemplate,
		handler.handleResolveCapability,
	)
}

func (handler *Handler) handleResolveCapability(
	writer http.ResponseWriter,
	request *http.Request,
) {
	var body struct {
		AccountID      string   `json:"accountId"`
		CapabilityKey  string   `json:"capabilityKey"`
		SurfaceKind    string   `json:"surfaceKind"`
		ConnectionRefs []string `json:"connectionRefs"`
	}
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 32<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeHTTPError(
			writer,
			request,
			connectionerrors.AppErrorFromConnectorConnectionInvalidArgument(err.Error()),
		)
		return
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		writeHTTPError(
			writer,
			request,
			connectionerrors.AppErrorFromConnectorConnectionInvalidArgument(
				"connector capability request must contain one JSON object",
			),
		)
		return
	}
	decision, err := handler.queries.ResolveCapability(
		request.Context(),
		model.ResolveCapabilityInput{
			AccountID:      body.AccountID,
			CapabilityKey:  body.CapabilityKey,
			SurfaceKind:    body.SurfaceKind,
			ConnectionRefs: body.ConnectionRefs,
		},
	)
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, decision)
}

func (handler *Handler) handleList(writer http.ResponseWriter, request *http.Request) {
	accountID, err := requireAccount(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	limit, err := parseLimit(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	items, err := handler.queries.List(request.Context(), accountID, limit)
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{"items": items})
}

func (handler *Handler) handleGet(writer http.ResponseWriter, request *http.Request) {
	accountID, err := requireAccount(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	connection, err := handler.queries.Get(request.Context(), accountID, request.PathValue("connectionId"))
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, connection)
}

func (handler *Handler) handleCreate(writer http.ResponseWriter, request *http.Request) {
	accountID, err := requireAccount(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	var body struct {
		ConnectorID           string   `json:"connectorId"`
		RequestedCapabilities []string `json:"requestedCapabilities"`
		GrantReceiptRef       string   `json:"grantReceiptRef"`
	}
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 64<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeHTTPError(writer, request, connectionerrors.AppErrorFromConnectorConnectionInvalidArgument(err.Error()))
		return
	}
	result, err := handler.commands.Create(request.Context(), model.CreateInput{
		AccountID: accountID, ConnectorID: body.ConnectorID,
		RequestedCapabilities: body.RequestedCapabilities,
		GrantReceiptRef:       body.GrantReceiptRef,
		IdempotencyKey:        strings.TrimSpace(request.Header.Get("Idempotency-Key")),
	})
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"connection": result.Connection, "replayed": result.Replayed,
	})
}

func (handler *Handler) handleRevoke(writer http.ResponseWriter, request *http.Request) {
	accountID, err := requireAccount(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	var body struct {
		ExpectedRevision int64 `json:"expectedRevision"`
	}
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 16<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeHTTPError(writer, request, connectionerrors.AppErrorFromConnectorConnectionInvalidArgument(err.Error()))
		return
	}
	result, err := handler.commands.Revoke(request.Context(), model.RevokeInput{
		AccountID: accountID, ConnectionID: request.PathValue("connectionId"),
		ExpectedRevision: body.ExpectedRevision,
		IdempotencyKey:   strings.TrimSpace(request.Header.Get("Idempotency-Key")),
	})
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"connection": result.Connection, "replayed": result.Replayed,
	})
}

func requireAccount(request *http.Request) (string, error) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if ok && strings.TrimSpace(principal.Actor.AccountID) != "" {
		return strings.TrimSpace(principal.Actor.AccountID), nil
	}
	return "", connectionerrors.AppErrorFromConnectorConnectionUnauthorized(
		"ConnectorConnection requires a verified account principal",
	)
}

func parseLimit(request *http.Request) (int, error) {
	raw := strings.TrimSpace(request.URL.Query().Get("limit"))
	if raw == "" {
		return 64, nil
	}
	limit, err := strconv.Atoi(raw)
	if err != nil || limit <= 0 || limit > 100 {
		return 0, connectionerrors.AppErrorFromConnectorConnectionInvalidArgument(
			"limit must be an integer between 1 and 100",
		)
	}
	return limit, nil
}

func mapDomainError(err error) error {
	switch {
	case errors.Is(err, model.ErrInvalidArgument):
		return connectionerrors.AppErrorFromConnectorConnectionInvalidArgument(err.Error())
	case errors.Is(err, model.ErrNotFound):
		return connectionerrors.AppErrorFromConnectorConnectionNotFound(err.Error())
	case errors.Is(err, model.ErrDefinitionNotFound):
		return connectionerrors.AppErrorFromConnectionConnectorDefinitionNotFound(err.Error())
	case errors.Is(err, model.ErrCapabilityDenied):
		return connectionerrors.AppErrorFromConnectorCapabilityDenied(err.Error())
	case errors.Is(err, model.ErrGrantReceiptInvalid):
		return connectionerrors.AppErrorFromConnectorGrantReceiptInvalid(err.Error())
	case errors.Is(err, model.ErrRevisionConflict):
		return connectionerrors.AppErrorFromConnectorConnectionRevisionConflict(err.Error())
	case errors.Is(err, model.ErrIdempotencyConflict):
		return connectionerrors.AppErrorFromConnectorConnectionIdempotencyConflict(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return connectionerrors.AppErrorFromConnectorConnectionUnavailable(err.Error())
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
