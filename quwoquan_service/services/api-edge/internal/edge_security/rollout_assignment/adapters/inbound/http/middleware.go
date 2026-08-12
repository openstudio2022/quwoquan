package httpadapter

import (
	"errors"
	"net"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
)

const (
	clientRegionHeader  = "X-Client-Region-Code"
	clientCarrierHeader = "X-Client-Carrier"
)

type NetworkAttributes = application.NetworkAttributes
type NetworkAttributeResolver = application.NetworkAttributeResolver

func Middleware(
	evaluator *application.Evaluator,
	resolver NetworkAttributeResolver,
	trustedNetworkHeader string,
	observer application.Observer,
) func(http.Handler) http.Handler {
	if evaluator == nil {
		panic("rollout evaluator is required")
	}
	trustedNetworkHeader = strings.TrimSpace(trustedNetworkHeader)
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
			// Client values are never trusted.  The edge rebuilds both attributes
			// from the Caddy-overwritten source IP or uses explicit unknown.
			request.Header.Del(clientRegionHeader)
			request.Header.Del(clientCarrierHeader)
			attributes := NetworkAttributes{Region: "unknown", Carrier: "unknown"}
			if resolver != nil {
				if clientIP := parseTrustedIP(request.Header.Get(trustedNetworkHeader)); clientIP != nil {
					attributes = resolver.Resolve(clientIP)
				}
			}
			attributes.Region = normalizedAttribute(attributes.Region)
			attributes.Carrier = normalizedAttribute(attributes.Carrier)
			request.Header.Set(clientRegionHeader, attributes.Region)
			request.Header.Set(clientCarrierHeader, attributes.Carrier)

			principal, _ := rtauth.PrincipalFromContext(request.Context())
			subject := application.Subject{
				DeviceActorID: principal.Actor.DeviceActorID,
				AccountID:     principal.Actor.AccountID,
				Platform:      request.Header.Get("X-Client-Device-Platform"),
				AppVersion:    request.Header.Get("X-Client-App-Version"),
				AppBuild:      request.Header.Get("X-Client-App-Build"),
				Region:        attributes.Region,
				Carrier:       attributes.Carrier,
			}
			decision, err := evaluator.Decide(request.Context(), subject)
			if err != nil {
				reason := "evaluation_failure"
				if errors.Is(err, application.ErrAssignmentStateUnavailable) {
					reason = "assignment_store_failure"
				}
				observeDecision(observer, evaluator.Stage(), "unavailable", subject, reason)
				writeRolloutUnavailable(response, request, err.Error())
				return
			}
			observeDecision(observer, evaluator.Stage(), string(decision.Target), subject, decision.Reason)
			ctx := application.WithTarget(request.Context(), decision.Target)
			next.ServeHTTP(response, request.WithContext(ctx))
		})
	}
}

func observeDecision(
	observer application.Observer,
	stage string,
	target string,
	subject application.Subject,
	reason string,
) {
	if observer == nil {
		return
	}
	observer.ObserveDecision(application.DecisionObservation{
		Stage: stage, Target: target, Platform: subject.Platform,
		AppVersion: subject.AppVersion, AppBuild: subject.AppBuild,
		Region: subject.Region, Carrier: subject.Carrier, Reason: reason,
	})
}

func parseTrustedIP(value string) net.IP {
	value = strings.TrimSpace(value)
	if host, _, err := net.SplitHostPort(value); err == nil {
		value = host
	}
	return net.ParseIP(value)
}

func normalizedAttribute(value string) string {
	if value = strings.TrimSpace(value); value != "" {
		return value
	}
	return "unknown"
}

func writeRolloutUnavailable(
	response http.ResponseWriter,
	request *http.Request,
	debugMessage string,
) {
	code, _ := rterr.ParseCode("GATEWAY.MIDDLEWARE.rollout_state_unavailable")
	errorValue := rterr.NewAppError(
		code,
		"发布路由暂不可用，请稍后重试",
		debugMessage,
	).WithMetadata("rollout_state_unavailable", http.StatusServiceUnavailable).
		WithRecoveryDirective("retry", "snackbar", 1)
	rterr.WriteHTTPError(response, errorValue, rterr.HTTPWriteOptionsFromRequest(request))
}
