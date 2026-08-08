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
	invocationerrors "quwoquan_service/services/integration-service/generated/external_integration/connector_invocation"
	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/application"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/domain/model"
)

const (
	listOperation     = "integration.connector_invocation.ListConnectorInvocations"
	getOperation      = "integration.connector_invocation.GetConnectorInvocation"
	invokeOperation   = "integration.connector_invocation.InvokeConnectorCapability"
	continueOperation = "integration.connector_invocation.ContinueConnectorInvocation"
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
	invoke := mustOperationDescriptor(invokeOperation)
	continuation := mustOperationDescriptor(continueOperation)
	mux.HandleFunc(list.Method+" "+list.PathTemplate, handler.handleList)
	mux.HandleFunc(get.Method+" "+get.PathTemplate, handler.handleGet)
	mux.HandleFunc(invoke.Method+" "+invoke.PathTemplate, handler.handleInvoke)
	mux.HandleFunc(continuation.Method+" "+continuation.PathTemplate, handler.handleContinue)
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
	items, err := handler.queries.List(
		request.Context(), accountID,
		strings.TrimSpace(request.URL.Query().Get("connectionId")), limit,
	)
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
	invocation, err := handler.queries.Get(request.Context(), accountID, request.PathValue("invocationId"))
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, invocation)
}

func (handler *Handler) handleInvoke(writer http.ResponseWriter, request *http.Request) {
	authorization, err := trustedInvocationAuthorization(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	var body struct {
		ResolutionID    string `json:"resolutionId"`
		ConnectionID    string `json:"connectionId"`
		AssistantRunID  string `json:"assistantRunId"`
		Capability      string `json:"capability"`
		SurfaceKind     string `json:"surfaceKind"`
		InputDigest     string `json:"inputDigest"`
		PayloadRef      string `json:"payloadRef"`
		ConfirmationRef string `json:"confirmationRef"`
		PermitRef       string `json:"permitRef"`
		ContinuationRef string `json:"continuationRef"`
	}
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 96<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeHTTPError(writer, request, invocationerrors.AppErrorFromConnectorInvocationInvalidArgument(err.Error()))
		return
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		writeHTTPError(writer, request, invocationerrors.AppErrorFromConnectorInvocationInvalidArgument(
			"connector invocation request must contain one JSON object",
		))
		return
	}
	result, err := handler.commands.Accept(request.Context(), authorization, model.AcceptInput{
		ResolutionID: body.ResolutionID, ConnectionID: body.ConnectionID,
		AssistantRunID: body.AssistantRunID, Capability: body.Capability,
		SurfaceKind: body.SurfaceKind, InputDigest: body.InputDigest,
		PayloadRef: body.PayloadRef, ConfirmationRef: body.ConfirmationRef,
		PermitRef:       body.PermitRef,
		ContinuationRef: body.ContinuationRef,
		IdempotencyKey:  strings.TrimSpace(request.Header.Get("Idempotency-Key")),
	})
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusAccepted, map[string]any{
		"invocation": result.Invocation, "replayed": result.Replayed,
	})
}

func (handler *Handler) handleContinue(writer http.ResponseWriter, request *http.Request) {
	authorization, err := trustedInvocationAuthorization(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	var body struct {
		ConfirmationRef  string `json:"confirmationRef"`
		ContinuationRef  string `json:"continuationRef"`
		ExpectedRevision int64  `json:"expectedRevision"`
	}
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 64<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeHTTPError(writer, request, invocationerrors.AppErrorFromConnectorInvocationInvalidArgument(err.Error()))
		return
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		writeHTTPError(writer, request, invocationerrors.AppErrorFromConnectorInvocationInvalidArgument(
			"connector invocation continuation must contain one JSON object",
		))
		return
	}
	result, err := handler.commands.Continue(request.Context(), authorization, model.ContinueInput{
		InvocationID:    request.PathValue("invocationId"),
		ConfirmationRef: body.ConfirmationRef, ContinuationRef: body.ContinuationRef,
		ExpectedRevision: body.ExpectedRevision,
		IdempotencyKey:   strings.TrimSpace(request.Header.Get("Idempotency-Key")),
	})
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusAccepted, map[string]any{
		"invocation": result.Invocation, "replayed": result.Replayed,
	})
}

func trustedInvocationAuthorization(
	request *http.Request,
) (grantapp.TrustedRuntimeAuthorization, error) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if !ok || principal.TokenType != rtauth.TokenTypeAccess ||
		strings.TrimSpace(principal.Subject) == "" ||
		strings.TrimSpace(principal.Subject) != strings.TrimSpace(principal.Actor.AccountID) ||
		strings.TrimSpace(principal.ServiceActorID) != "assistant-service" ||
		!containsString(principal.Roles, "service") ||
		!containsString(strings.Fields(principal.Scope), "integration.connector_invocation.write") {
		return grantapp.TrustedRuntimeAuthorization{},
			invocationerrors.AppErrorFromConnectorInvocationUnauthorized(
				"connector invocation requires a signed account subject and allowed service actor",
			)
	}
	authorization, err := grantapp.NewTrustedRuntimeAuthorization(
		principal.Subject,
		principal.ServiceActorID,
	)
	if err != nil {
		return grantapp.TrustedRuntimeAuthorization{},
			invocationerrors.AppErrorFromConnectorInvocationUnauthorized(err.Error())
	}
	return authorization, nil
}

func containsString(values []string, expected string) bool {
	for _, value := range values {
		if strings.TrimSpace(value) == expected {
			return true
		}
	}
	return false
}

func requireAccount(request *http.Request) (string, error) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if ok && strings.TrimSpace(principal.Actor.AccountID) != "" {
		return strings.TrimSpace(principal.Actor.AccountID), nil
	}
	return "", invocationerrors.AppErrorFromConnectorInvocationUnauthorized(
		"ConnectorInvocation query requires a verified account principal",
	)
}

func parseLimit(request *http.Request) (int, error) {
	raw := strings.TrimSpace(request.URL.Query().Get("limit"))
	if raw == "" {
		return 64, nil
	}
	limit, err := strconv.Atoi(raw)
	if err != nil || limit <= 0 || limit > 100 {
		return 0, invocationerrors.AppErrorFromConnectorInvocationInvalidArgument(
			"limit must be an integer between 1 and 100",
		)
	}
	return limit, nil
}

func mapDomainError(err error) error {
	switch {
	case errors.Is(err, model.ErrInvalidArgument):
		return invocationerrors.AppErrorFromConnectorInvocationInvalidArgument(err.Error())
	case errors.Is(err, model.ErrNotFound):
		return invocationerrors.AppErrorFromConnectorInvocationNotFound(err.Error())
	case errors.Is(err, model.ErrConnectionNotFound):
		return invocationerrors.AppErrorFromInvocationConnectorConnectionNotFound(err.Error())
	case errors.Is(err, model.ErrConnectionInactive):
		return invocationerrors.AppErrorFromConnectorConnectionInactive(err.Error())
	case errors.Is(err, model.ErrCapabilityDenied):
		return invocationerrors.AppErrorFromInvocationConnectorCapabilityDenied(err.Error())
	case errors.Is(err, model.ErrConfirmationRequired):
		return invocationerrors.AppErrorFromConnectorConfirmationRequired(err.Error())
	case errors.Is(err, model.ErrRevisionConflict):
		return invocationerrors.AppErrorFromConnectorInvocationRevisionConflict(err.Error())
	case errors.Is(err, model.ErrIdempotencyConflict):
		return invocationerrors.AppErrorFromConnectorInvocationIdempotencyConflict(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return invocationerrors.AppErrorFromConnectorInvocationUnavailable(err.Error())
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
