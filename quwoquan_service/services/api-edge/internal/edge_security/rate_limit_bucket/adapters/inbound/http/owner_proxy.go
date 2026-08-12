package httpadapter

import (
	"errors"
	"fmt"
	"net/http"
	"net/http/httputil"
	"net/url"
	"sort"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	gatewaygenerated "quwoquan_service/services/api-edge/generated/edge_security/rate_limit_bucket"
	rolloutapp "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
	rolloutdomain "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/domain"
)

type OwnerRoute struct {
	OperationPrefix string
	Upstream        *url.URL
}

type OwnerProxyConfig struct {
	Routes               []OwnerRoute
	CandidateRoutes      []OwnerRoute
	Transport            http.RoundTripper
	TrustedNetworkHeader string
	ContractGraphSHA256  string
}

func NewOwnerProxy(config OwnerProxyConfig) (http.Handler, error) {
	if len(config.Routes) == 0 {
		return nil, errors.New("api-edge owner routes are required")
	}
	routes, err := validatedOwnerRoutes(config.Routes)
	if err != nil {
		return nil, err
	}
	candidateRoutes, err := validatedOwnerRoutes(config.CandidateRoutes)
	if err != nil {
		return nil, fmt.Errorf("candidate owner routes: %w", err)
	}
	if len(config.CandidateRoutes) == 0 {
		candidateRoutes = nil
	}
	transport := config.Transport
	if transport == nil {
		transport = http.DefaultTransport
	}
	trustedHeader := strings.TrimSpace(config.TrustedNetworkHeader)
	contractGraphSHA256 := strings.TrimSpace(config.ContractGraphSHA256)
	proxy := &httputil.ReverseProxy{
		Transport: transport,
		Rewrite: func(proxyRequest *httputil.ProxyRequest) {
			descriptor, _ := rtauth.OperationDescriptorFromContext(proxyRequest.In.Context())
			selectedRoutes := routes
			if rolloutapp.TargetFromContext(proxyRequest.In.Context()) == rolloutdomain.TargetCandidate {
				selectedRoutes = candidateRoutes
			}
			upstream := ownerUpstream(selectedRoutes, descriptor.CanonicalOperationID)
			if upstream == nil {
				proxyRequest.Out.URL.Scheme = "http"
				proxyRequest.Out.URL.Host = "invalid.api-edge-owner"
				return
			}
			proxyRequest.SetURL(upstream)
			proxyRequest.SetXForwarded()
			if trustedHeader != "" {
				proxyRequest.Out.Header.Del(trustedHeader)
			}
			restoreVerifiedCredential(proxyRequest.Out)
			if contractGraphSHA256 != "" {
				proxyRequest.Out.Header.Set("X-Contract-Graph-SHA256", contractGraphSHA256)
			}
		},
		ErrorHandler: func(response http.ResponseWriter, request *http.Request, _ error) {
			response.Header().Set("Retry-After", "1")
			errorValue := gatewaygenerated.AppErrorFromUpstreamUnavailable(
				"canonical owner proxy failed",
			).WithRecoveryDirective("retry", "snackbar", 1)
			rterr.WriteHTTPError(response, errorValue, rterr.HTTPWriteOptionsFromRequest(request))
		},
	}
	return proxy, nil
}

func validatedOwnerRoutes(input []OwnerRoute) ([]OwnerRoute, error) {
	if len(input) == 0 {
		return nil, nil
	}
	routes := append([]OwnerRoute(nil), input...)
	seen := map[string]struct{}{}
	for index := range routes {
		routes[index].OperationPrefix = strings.TrimSpace(routes[index].OperationPrefix)
		if routes[index].OperationPrefix == "" || routes[index].Upstream == nil ||
			routes[index].Upstream.Scheme == "" || routes[index].Upstream.Host == "" {
			return nil, errors.New("api-edge owner route requires operation prefix and absolute upstream")
		}
		if routes[index].Upstream.User != nil || routes[index].Upstream.RawQuery != "" ||
			routes[index].Upstream.Fragment != "" ||
			(routes[index].Upstream.Path != "" && routes[index].Upstream.Path != "/") {
			return nil, errors.New("api-edge owner upstream must be an origin URL")
		}
		if _, exists := seen[routes[index].OperationPrefix]; exists {
			return nil, errors.New("duplicate api-edge owner operation prefix")
		}
		seen[routes[index].OperationPrefix] = struct{}{}
	}
	sort.Slice(routes, func(left, right int) bool {
		return len(routes[left].OperationPrefix) > len(routes[right].OperationPrefix)
	})
	return routes, nil
}

func ownerUpstream(routes []OwnerRoute, operationID string) *url.URL {
	operationID = strings.TrimSpace(operationID)
	for _, route := range routes {
		if strings.HasPrefix(operationID, route.OperationPrefix) {
			return route.Upstream
		}
	}
	return nil
}
