package httpadapter

import (
	"errors"
	"fmt"
	"net"
	"net/http"
	"strconv"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	gatewaygenerated "quwoquan_service/services/api-edge/generated/edge_security/rate_limit_bucket"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/application"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/domain"
)

type SubjectResolver struct {
	TrustedNetworkHeader string
}

func (resolver SubjectResolver) Resolve(request *http.Request) (domain.Subject, error) {
	if request == nil {
		return domain.Subject{}, errors.New("admission request is required")
	}
	if principal, ok := rtauth.PrincipalFromContext(request.Context()); ok {
		if personaID := strings.TrimSpace(principal.Actor.PersonaID); personaID != "" {
			return domain.Subject{Kind: "persona", ID: personaID}, nil
		}
		if accountID := strings.TrimSpace(principal.Actor.AccountID); accountID != "" {
			kind := "account"
			if strings.HasPrefix(accountID, "service:") {
				kind = "service"
			} else if len(principal.Roles) != 0 {
				kind = "operator"
			}
			return domain.Subject{Kind: kind, ID: accountID}, nil
		}
		if deviceID := strings.TrimSpace(principal.Actor.DeviceActorID); deviceID != "" {
			return domain.Subject{Kind: "device", ID: deviceID}, nil
		}
		return domain.Subject{}, errors.New("verified principal has no admission subject")
	}
	header := strings.TrimSpace(resolver.TrustedNetworkHeader)
	if header == "" {
		return domain.Subject{}, errors.New("trusted network subject header is required")
	}
	networkSubject := strings.TrimSpace(request.Header.Get(header))
	if networkSubject == "" {
		return domain.Subject{}, errors.New("trusted network subject is missing")
	}
	if host, _, err := net.SplitHostPort(networkSubject); err == nil {
		networkSubject = host
	}
	if parsed := net.ParseIP(networkSubject); parsed == nil {
		return domain.Subject{}, errors.New("trusted network subject must be an IP address")
	}
	return domain.Subject{Kind: "network", ID: networkSubject}, nil
}

func AdmissionMiddleware(
	service *application.Service,
	resolver SubjectResolver,
) func(http.Handler) http.Handler {
	if service == nil {
		panic("api-edge admission service is required")
	}
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
			descriptor, ok := rtauth.OperationDescriptorFromContext(request.Context())
			if !ok {
				writeStateUnavailable(response, request, time.Second, "generated operation descriptor missing")
				return
			}
			subject, err := resolver.Resolve(request)
			if err != nil {
				writeStateUnavailable(response, request, time.Second, "trusted subject resolution failed")
				return
			}
			decision, err := service.Admit(request.Context(), subject, descriptor)
			if err != nil {
				if errors.Is(err, application.ErrSharedStateUnavailable) {
					writeStateUnavailable(response, request, decision.RetryAfter, "shared admission state unavailable")
					return
				}
				writeStateUnavailable(response, request, time.Second, "admission policy rejected request")
				return
			}
			if !decision.Allowed {
				seconds := retryAfterSeconds(decision.RetryAfter)
				response.Header().Set("Retry-After", strconv.Itoa(seconds))
				errorValue := gatewaygenerated.AppErrorFromRateLimited(
					"shared admission quota exhausted",
				).WithRecoveryDirective("retry", "snackbar", seconds)
				rterr.WriteHTTPError(response, errorValue, rterr.HTTPWriteOptionsFromRequest(request))
				return
			}
			next.ServeHTTP(response, request)
		})
	}
}

func writeStateUnavailable(
	response http.ResponseWriter,
	request *http.Request,
	retryAfter time.Duration,
	debugMessage string,
) {
	seconds := retryAfterSeconds(retryAfter)
	response.Header().Set("Retry-After", strconv.Itoa(seconds))
	errorValue := gatewaygenerated.AppErrorFromRateLimitStateUnavailable(
		debugMessage,
	).WithRecoveryDirective("retry", "snackbar", seconds)
	rterr.WriteHTTPError(response, errorValue, rterr.HTTPWriteOptionsFromRequest(request))
}

func retryAfterSeconds(duration time.Duration) int {
	if duration <= 0 {
		return 1
	}
	seconds := int((duration + time.Second - 1) / time.Second)
	if seconds < 1 {
		return 1
	}
	if seconds > int(domain.MaxWindow/time.Second) {
		panic(fmt.Sprintf("retry-after %d exceeds domain maximum", seconds))
	}
	return seconds
}
