package http

import (
	"context"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	registrationapp "quwoquan_service/services/user-service/internal/application/account/device_registration"
	registrationmodel "quwoquan_service/services/user-service/internal/domain/account/device_registration/model"
	"quwoquan_service/services/user-service/internal/generated"
)

type upsertDevicePushEndpointWire struct {
	Token      string `json:"token"`
	AppVersion string `json:"appVersion"`
}

type invalidateDevicePushEndpointWire struct {
	Reason string `json:"reason"`
}

func (h *UserHandler) registerDeviceRegistrationRoutes(mux *http.ServeMux) {
	mux.HandleFunc(
		"PUT "+generated.UpsertDevicePushEndpointPathTemplate,
		h.handleUpsertDevicePushEndpoint,
	)
	mux.HandleFunc(
		"DELETE "+generated.RemoveDevicePushEndpointPathTemplate,
		h.handleRemoveDevicePushEndpoint,
	)
	mux.HandleFunc(
		"GET "+generated.ResolveIncomingCallPushDestinationsPathTemplate,
		h.handleResolveIncomingCallPushDestinations,
	)
	mux.HandleFunc(
		"GET "+generated.ResolvePushEndpointSecretPathTemplate,
		h.handleResolvePushEndpointSecret,
	)
	mux.HandleFunc(
		"POST "+generated.InvalidateDevicePushEndpointPathTemplate,
		h.handleInvalidateDevicePushEndpoint,
	)
}

func (h *UserHandler) handleUpsertDevicePushEndpoint(
	w http.ResponseWriter,
	r *http.Request,
) {
	ctx, ok := trustedAccountOperationContext(
		w,
		r,
		generated.UpsertDevicePushEndpointCanonicalOperation,
	)
	if !ok {
		return
	}
	var wire upsertDevicePushEndpointWire
	if err := decodeStrictJSON(r, &wire); err != nil {
		writeHTTPError(w, r, generated.AppErrorFromDevicePushInvalidToken(
			"invalid push endpoint upsert request",
		))
		return
	}
	result, err := h.deviceRegistrationCommands.UpsertDevicePushEndpoint(
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

func (h *UserHandler) handleRemoveDevicePushEndpoint(
	w http.ResponseWriter,
	r *http.Request,
) {
	ctx, ok := trustedAccountOperationContext(
		w,
		r,
		generated.RemoveDevicePushEndpointCanonicalOperation,
	)
	if !ok {
		return
	}
	result, err := h.deviceRegistrationCommands.RemoveDevicePushEndpoint(
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

func (h *UserHandler) handleResolveIncomingCallPushDestinations(
	w http.ResponseWriter,
	r *http.Request,
) {
	ctx, ok := trustedServiceOperationContext(
		w,
		r,
		generated.ResolveIncomingCallPushDestinationsCanonicalOperation,
		registrationapp.PushDestinationReadScope,
		"",
	)
	if !ok {
		return
	}
	result, err := h.deviceRegistrationQueries.ResolveIncomingCallPushDestinations(
		ctx,
		strings.TrimSpace(r.PathValue("personaId")),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleResolvePushEndpointSecret(
	w http.ResponseWriter,
	r *http.Request,
) {
	setSecretResponseHeaders(w)
	ctx, ok := trustedServiceOperationContext(
		w,
		r,
		generated.ResolvePushEndpointSecretCanonicalOperation,
		registrationapp.PushEndpointSecretReadScope,
		registrationapp.IntegrationServicePrincipal,
	)
	if !ok {
		return
	}
	result, err := h.deviceRegistrationQueries.ResolvePushEndpointSecret(
		ctx,
		strings.TrimSpace(r.PathValue("endpointRef")),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleInvalidateDevicePushEndpoint(
	w http.ResponseWriter,
	r *http.Request,
) {
	ctx, ok := trustedServiceOperationContext(
		w,
		r,
		generated.InvalidateDevicePushEndpointCanonicalOperation,
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
			generated.AppErrorFromDevicePushInvalidInvalidationReason(
				"invalid push endpoint invalidation request",
			),
		)
		return
	}
	result, err := h.deviceRegistrationCommands.InvalidateDevicePushEndpoint(
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
			"service principal lacks the required push endpoint scope",
		))
		return nil, false
	}
	if requiredAccountID != "" &&
		strings.TrimSpace(principal.Actor.AccountID) != requiredAccountID {
		writeHTTPError(w, r, generated.AppErrorFromForbidden(
			"service principal is not allowed to access push endpoint secrets",
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
