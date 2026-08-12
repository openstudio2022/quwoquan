package httpadapter

import (
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
)

type MinimumBuildObserver interface {
	ObserveMinimumBuild(platform, build, mode, reason string, wouldBlock bool)
}

func MinimumBuildForAuthenticatedClients(
	middleware func(http.Handler) http.Handler,
	next http.Handler,
) http.Handler {
	checked := middleware(next)
	return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		principal, ok := rtauth.PrincipalFromContext(request.Context())
		if ok && minimumBuildBypassPrincipal(principal) {
			next.ServeHTTP(response, request)
			return
		}
		checked.ServeHTTP(response, request)
	})
}

func minimumBuildBypassPrincipal(principal rtauth.Principal) bool {
	if strings.HasPrefix(strings.TrimSpace(principal.Actor.AccountID), "service:") {
		return true
	}
	for _, role := range principal.Roles {
		switch strings.ToLower(strings.TrimSpace(role)) {
		case "service", "operator", "admin":
			return true
		}
	}
	return false
}

func MinimumBuildMiddleware(
	policy application.MinimumBuildPolicy,
	exemptPaths map[string]struct{},
	observer MinimumBuildObserver,
) (func(http.Handler) http.Handler, error) {
	if err := policy.Validate(); err != nil {
		return nil, err
	}
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
			if _, exempt := exemptPaths[request.URL.Path]; exempt {
				next.ServeHTTP(response, request)
				return
			}
			platform := strings.TrimSpace(request.Header.Get("X-Client-Device-Platform"))
			build := strings.TrimSpace(request.Header.Get("X-Client-App-Build"))
			decision := policy.Decide(platform, build)
			if observer != nil {
				observer.ObserveMinimumBuild(platform, build, policy.Mode, decision.Reason, decision.WouldBlock)
			}
			if decision.Allowed {
				next.ServeHTTP(response, request)
				return
			}
			writeUpgradeRequired(response, request, decision.Reason)
		})
	}, nil
}

func writeUpgradeRequired(response http.ResponseWriter, request *http.Request, reason string) {
	code, _ := rterr.ParseCode("GATEWAY.USER.client_upgrade_required")
	errorValue := rterr.NewAppError(
		code,
		"当前版本已不受支持，请先完成更新",
		"minimum supported app build rejected request: "+reason,
	).WithMetadata("client_upgrade_required", http.StatusUpgradeRequired).
		WithRecoveryDirective("surface", "inlineCard", 0)
	rterr.WriteHTTPError(response, errorValue, rterr.HTTPWriteOptionsFromRequest(request))
}
