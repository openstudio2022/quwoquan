package http

import (
	"context"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	httpcodec "quwoquan_service/runtime/httpcodec"
	"quwoquan_service/runtime/operation"
	registrationgenerated "quwoquan_service/services/user-service/generated/account/device_registration"
	"quwoquan_service/services/user-service/generated/account/user_account"
	registrationapp "quwoquan_service/services/user-service/internal/account/device_registration/application"
	registrationmodel "quwoquan_service/services/user-service/internal/account/device_registration/domain/model"
)

type upsertDevicePushEndpointWire struct {
	Token      string `json:"token"`
	AppVersion string `json:"appVersion"`
}

type invalidateDevicePushEndpointWire struct {
	Reason string `json:"reason"`
}

type Handler struct {
	commands *registrationapp.CommandFacade
	queries  *registrationapp.QueryFacade
}

func NewHandler(commands *registrationapp.CommandFacade, queries *registrationapp.QueryFacade) *Handler {
	if commands == nil || queries == nil {
		panic("DeviceRegistration HTTP handler requires command and query facades")
	}
	return &Handler{commands: commands, queries: queries}
}

func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc(
		"PUT "+registrationgenerated.UpsertDevicePushEndpointPathTemplate,
		h.handleUpsertDevicePushEndpoint,
	)
	mux.HandleFunc(
		"DELETE "+registrationgenerated.RemoveDevicePushEndpointPathTemplate,
		h.handleRemoveDevicePushEndpoint,
	)
	mux.HandleFunc(
		"GET "+registrationgenerated.ResolveIncomingCallPushDestinationsPathTemplate,
		h.handleResolveIncomingCallPushDestinations,
	)
	mux.HandleFunc(
		"GET "+registrationgenerated.ResolvePushEndpointSecretPathTemplate,
		h.handleResolvePushEndpointSecret,
	)
	mux.HandleFunc(
		"POST "+registrationgenerated.InvalidateDevicePushEndpointPathTemplate,
		h.handleInvalidateDevicePushEndpoint,
	)
}

func (h *Handler) handleUpsertDevicePushEndpoint(
	w http.ResponseWriter,
	r *http.Request,
) {
	ctx, ok := trustedAccountOperationContext(
		w,
		r,
		registrationgenerated.UpsertDevicePushEndpointCanonicalOperation,
	)
	if !ok {
		return
	}
	var wire upsertDevicePushEndpointWire
	if err := decodeStrictJSON(r, &wire); err != nil {
		writeHTTPError(w, r, registrationgenerated.AppErrorFromDevicePushInvalidToken(
			"invalid push endpoint upsert request",
		))
		return
	}
	result, err := h.commands.UpsertDevicePushEndpoint(
		ctx,
		registrationapp.UpsertDevicePushEndpointCommand{
			DeviceID: strings.TrimSpace(r.PathValue("deviceId")),
			Kind: registrationmodel.EndpointKind(
				strings.TrimSpace(r.PathValue("endpointKind")),
			),
			Token:      []byte(wire.Token),
			AppVersion: wire.AppVersion,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) handleRemoveDevicePushEndpoint(
	w http.ResponseWriter,
	r *http.Request,
) {
	ctx, ok := trustedAccountOperationContext(
		w,
		r,
		registrationgenerated.RemoveDevicePushEndpointCanonicalOperation,
	)
	if !ok {
		return
	}
	result, err := h.commands.RemoveDevicePushEndpoint(
		ctx,
		registrationapp.RemoveDevicePushEndpointCommand{
			DeviceID: strings.TrimSpace(r.PathValue("deviceId")),
			Kind: registrationmodel.EndpointKind(
				strings.TrimSpace(r.PathValue("endpointKind")),
			),
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) handleResolveIncomingCallPushDestinations(
	w http.ResponseWriter,
	r *http.Request,
) {
	ctx, ok := trustedServiceOperationContext(
		w,
		r,
		registrationgenerated.ResolveIncomingCallPushDestinationsCanonicalOperation,
		registrationapp.PushDestinationReadScope,
		"",
	)
	if !ok {
		return
	}
	result, err := h.queries.ResolveIncomingCallPushDestinations(
		ctx,
		strings.TrimSpace(r.PathValue("personaId")),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) handleResolvePushEndpointSecret(
	w http.ResponseWriter,
	r *http.Request,
) {
	setSecretResponseHeaders(w)
	ctx, ok := trustedServiceOperationContext(
		w,
		r,
		registrationgenerated.ResolvePushEndpointSecretCanonicalOperation,
		registrationapp.PushEndpointSecretReadScope,
		registrationapp.IntegrationServicePrincipal,
	)
	if !ok {
		return
	}
	result, err := h.queries.ResolvePushEndpointSecret(
		ctx,
		strings.TrimSpace(r.PathValue("endpointRef")),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) handleInvalidateDevicePushEndpoint(
	w http.ResponseWriter,
	r *http.Request,
) {
	ctx, ok := trustedServiceOperationContext(
		w,
		r,
		registrationgenerated.InvalidateDevicePushEndpointCanonicalOperation,
		registrationapp.PushEndpointInvalidateScope,
		registrationapp.IntegrationServicePrincipal,
	)
	if !ok {
		return
	}
	var wire invalidateDevicePushEndpointWire
	if err := decodeStrictJSON(r, &wire); err != nil {
		writeHTTPError(
			w,
			r,
			registrationgenerated.AppErrorFromDevicePushInvalidInvalidationReason(
				"invalid push endpoint invalidation request",
			),
		)
		return
	}
	result, err := h.commands.InvalidateDevicePushEndpoint(
		ctx,
		registrationapp.InvalidateDevicePushEndpointCommand{
			EndpointRef: strings.TrimSpace(r.PathValue("endpointRef")),
			Reason:      wire.Reason,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func trustedAccountOperationContext(
	w http.ResponseWriter,
	r *http.Request,
	expectedOperation string,
) (context.Context, bool) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok ||
		principal.TokenType != rtauth.TokenTypeAccess ||
		containsGrant(principal.Roles, "service") ||
		strings.TrimSpace(principal.Actor.AccountID) == "" {
		writeHTTPError(w, r, generated.AppErrorFromUnauthorized(
			"trusted account principal is required",
		))
		return nil, false
	}
	return trustedOperationContext(r, principal, expectedOperation), true
}

func trustedServiceOperationContext(
	w http.ResponseWriter,
	r *http.Request,
	expectedOperation string,
	requiredScope string,
	requiredAccountID string,
) (context.Context, bool) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		writeHTTPError(w, r, generated.AppErrorFromUnauthorized(
			"trusted service principal is required",
		))
		return nil, false
	}
	if !containsGrant(principal.Roles, "service") ||
		!containsGrant(strings.Fields(principal.Scope), requiredScope) {
		writeHTTPError(w, r, generated.AppErrorFromForbidden(
			"service principal lacks the required operation scope",
		))
		return nil, false
	}
	if requiredAccountID != "" &&
		strings.TrimSpace(principal.Actor.AccountID) != requiredAccountID {
		writeHTTPError(w, r, generated.AppErrorFromForbidden(
			"service principal is not allowed to execute this operation",
		))
		return nil, false
	}
	return trustedOperationContext(r, principal, expectedOperation), true
}

func trustedOperationContext(
	r *http.Request,
	principal rtauth.Principal,
	expectedOperation string,
) context.Context {
	invocation, ok := operation.FromContext(r.Context())
	if !ok {
		invocation = operation.Context{}
	}
	invocation.OperationID = expectedOperation
	invocation.Actor = principal.Actor
	return operation.WithContext(r.Context(), invocation)
}

func containsGrant(values []string, expected string) bool {
	for _, value := range values {
		if strings.TrimSpace(value) == expected {
			return true
		}
	}
	return false
}

func setSecretResponseHeaders(w http.ResponseWriter) {
	w.Header().Set("Cache-Control", "no-store, max-age=0")
	w.Header().Set("Pragma", "no-cache")
	w.Header().Set("X-Content-Type-Options", "nosniff")
}

func decodeStrictJSON(r *http.Request, target any) error {
	return httpcodec.DecodeStrictJSON(r, target)
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	httpcodec.WriteJSON(w, status, payload, "device_registration")
}
