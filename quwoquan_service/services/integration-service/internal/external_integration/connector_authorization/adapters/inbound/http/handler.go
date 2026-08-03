package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	authorizationerrors "quwoquan_service/services/integration-service/generated/external_integration/connector_authorization"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/application"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/domain/model"
)

const (
	startOperation          = "integration.connector_authorization.StartConnectorAuthorization"
	getOperation            = "integration.connector_authorization.GetConnectorAuthorization"
	completeNativeOperation = "integration.connector_authorization.CompleteNativeConnectorAuthorization"
	completeOAuthOperation  = "integration.connector_authorization.CompleteOAuthConnectorAuthorization"
)

type Handler struct {
	commands *application.CommandFacade
	queries  *application.QueryFacade
}

func NewHandler(commands *application.CommandFacade, queries *application.QueryFacade) *Handler {
	return &Handler{commands: commands, queries: queries}
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	start := mustOperationDescriptor(startOperation)
	get := mustOperationDescriptor(getOperation)
	completeNative := mustOperationDescriptor(completeNativeOperation)
	completeOAuth := mustOperationDescriptor(completeOAuthOperation)
	mux.HandleFunc(start.Method+" "+start.PathTemplate, handler.handleStart)
	mux.HandleFunc(get.Method+" "+get.PathTemplate, handler.handleGet)
	mux.HandleFunc(completeNative.Method+" "+completeNative.PathTemplate, handler.handleCompleteNative)
	mux.HandleFunc(completeOAuth.Method+" "+completeOAuth.PathTemplate, handler.handleCompleteOAuth)
}

func (handler *Handler) handleStart(writer http.ResponseWriter, request *http.Request) {
	accountID, err := requireAccount(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	var body struct {
		ConnectorID           string   `json:"connectorId"`
		RequestedCapabilities []string `json:"requestedCapabilities"`
	}
	if err := decodeBody(writer, request, 64<<10, &body); err != nil {
		writeHTTPError(writer, request, authorizationerrors.AppErrorFromConnectorAuthorizationInvalidArgument(err.Error()))
		return
	}
	result, err := handler.commands.Start(request.Context(), model.StartInput{
		AccountID:             accountID,
		ConnectorID:           body.ConnectorID,
		RequestedCapabilities: body.RequestedCapabilities,
		IdempotencyKey:        strings.TrimSpace(request.Header.Get("Idempotency-Key")),
	})
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"authorization":   result.Authorization,
		"continuationRef": result.ContinuationRef,
		"replayed":        result.Replayed,
	})
}

func (handler *Handler) handleGet(writer http.ResponseWriter, request *http.Request) {
	accountID, err := requireAccount(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	authorization, err := handler.queries.Get(
		request.Context(),
		accountID,
		request.PathValue("authorizationId"),
	)
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, authorization)
}

func (handler *Handler) handleCompleteNative(writer http.ResponseWriter, request *http.Request) {
	accountID, err := requireAccount(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	var body struct {
		ExpectedRevision    int64  `json:"expectedRevision"`
		NativeGrantProofRef string `json:"nativeGrantProofRef"`
	}
	if err := decodeBody(writer, request, 64<<10, &body); err != nil {
		writeHTTPError(writer, request, authorizationerrors.AppErrorFromConnectorAuthorizationInvalidArgument(err.Error()))
		return
	}
	result, err := handler.commands.CompleteNative(request.Context(), model.CompleteInput{
		AccountID:        accountID,
		AuthorizationID:  request.PathValue("authorizationId"),
		ExpectedRevision: body.ExpectedRevision,
		ProofRef:         body.NativeGrantProofRef,
		IdempotencyKey:   strings.TrimSpace(request.Header.Get("Idempotency-Key")),
	})
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeGrantReceipt(writer, result)
}

func (handler *Handler) handleCompleteOAuth(writer http.ResponseWriter, request *http.Request) {
	var body struct {
		ExpectedRevision int64  `json:"expectedRevision"`
		OAuthCallbackRef string `json:"oauthCallbackRef"`
	}
	if err := decodeBody(writer, request, 64<<10, &body); err != nil {
		writeHTTPError(writer, request, authorizationerrors.AppErrorFromConnectorAuthorizationInvalidArgument(err.Error()))
		return
	}
	result, err := handler.commands.CompleteOAuth(request.Context(), model.CompleteInput{
		AuthorizationID:  request.PathValue("authorizationId"),
		ExpectedRevision: body.ExpectedRevision,
		ProofRef:         body.OAuthCallbackRef,
		IdempotencyKey:   strings.TrimSpace(request.Header.Get("Idempotency-Key")),
	})
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeGrantReceipt(writer, result)
}

func writeGrantReceipt(writer http.ResponseWriter, result model.MutationResult) {
	writeJSON(writer, http.StatusOK, map[string]any{
		"authorization":   result.Authorization,
		"grantReceiptRef": result.GrantReceiptRef,
		"replayed":        result.Replayed,
	})
}

func requireAccount(request *http.Request) (string, error) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if ok && strings.TrimSpace(principal.Actor.AccountID) != "" {
		return strings.TrimSpace(principal.Actor.AccountID), nil
	}
	return "", authorizationerrors.AppErrorFromConnectorAuthorizationUnauthorized(
		"ConnectorAuthorization requires a verified account principal",
	)
}

func decodeBody(writer http.ResponseWriter, request *http.Request, limit int64, target any) error {
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, limit))
	decoder.DisallowUnknownFields()
	return decoder.Decode(target)
}

func mapDomainError(err error) error {
	switch {
	case errors.Is(err, model.ErrInvalidArgument):
		return authorizationerrors.AppErrorFromConnectorAuthorizationInvalidArgument(err.Error())
	case errors.Is(err, model.ErrNotFound):
		return authorizationerrors.AppErrorFromConnectorAuthorizationNotFound(err.Error())
	case errors.Is(err, model.ErrUnauthorized):
		return authorizationerrors.AppErrorFromConnectorAuthorizationUnauthorized(err.Error())
	case errors.Is(err, model.ErrDefinitionNotFound):
		return authorizationerrors.AppErrorFromAuthorizationConnectorDefinitionNotFound(err.Error())
	case errors.Is(err, model.ErrCapabilityDenied):
		return authorizationerrors.AppErrorFromConnectorAuthorizationCapabilityDenied(err.Error())
	case errors.Is(err, model.ErrModeUnsupported):
		return authorizationerrors.AppErrorFromConnectorAuthorizationModeUnsupported(err.Error())
	case errors.Is(err, model.ErrModeMismatch):
		return authorizationerrors.AppErrorFromConnectorAuthorizationModeMismatch(err.Error())
	case errors.Is(err, model.ErrExpired):
		return authorizationerrors.AppErrorFromConnectorAuthorizationExpired(err.Error())
	case errors.Is(err, model.ErrNativeProofInvalid):
		return authorizationerrors.AppErrorFromConnectorNativeGrantProofInvalid(err.Error())
	case errors.Is(err, model.ErrOAuthCallbackInvalid):
		return authorizationerrors.AppErrorFromConnectorOAuthCallbackInvalid(err.Error())
	case errors.Is(err, model.ErrRevisionConflict):
		return authorizationerrors.AppErrorFromConnectorAuthorizationRevisionConflict(err.Error())
	case errors.Is(err, model.ErrIdempotencyConflict):
		return authorizationerrors.AppErrorFromConnectorAuthorizationIdempotencyConflict(err.Error())
	case errors.Is(err, model.ErrProviderUnavailable):
		return authorizationerrors.AppErrorFromConnectorAuthorizationProviderUnavailable(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return authorizationerrors.AppErrorFromConnectorAuthorizationUnavailable(err.Error())
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
