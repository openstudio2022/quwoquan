package http

import (
	"context"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/user-service/generated/account/user_account"
)

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
