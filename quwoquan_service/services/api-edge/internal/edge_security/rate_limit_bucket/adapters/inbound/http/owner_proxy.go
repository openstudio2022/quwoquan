package httpadapter

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"sort"
	"strings"
	"sync"
	"time"

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
	BudgetAllowance      time.Duration
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
	if config.BudgetAllowance <= 0 {
		return nil, errors.New("api-edge owner proxy budget allowance is required")
	}
	transport := config.Transport
	if transport == nil {
		transport = http.DefaultTransport
	}
	transport = ownerProxyBudgetTransport{
		next: transport, allowance: config.BudgetAllowance,
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
		ErrorHandler: func(response http.ResponseWriter, request *http.Request, proxyErr error) {
			// The caller is already gone (client disconnect or HTTP server
			// shutdown). Emitting a retryable timeout would be unobservable to that
			// caller and would falsely inflate gateway timeout telemetry.
			if ownerProxyCallerCanceled(request) {
				return
			}
			failureKind := classifyOwnerProxyFailure(proxyErr)
			var errorValue *rterr.AppError
			switch failureKind {
			case ownerProxyFailureDeadline,
				ownerProxyFailureTransportTimeout:
				errorValue = gatewaygenerated.AppErrorFromUpstreamTimeout(
					"canonical owner proxy " + string(failureKind),
				)
			default:
				errorValue = gatewaygenerated.AppErrorFromUpstreamUnavailable(
					"canonical owner proxy " + string(failureKind),
				)
			}
			response.Header().Set("Retry-After", "1")
			errorValue.WithContextAttributes(rterr.RuntimeErrorContextAttribute{
				Key: "upstreamFailureKind", Value: string(failureKind),
			})
			rterr.WriteHTTPError(response, errorValue, rterr.HTTPWriteOptionsFromRequest(request))
		},
	}
	return proxy, nil
}

// ownerProxyBudgetTransport gives the public API Edge boundary an independent
// deadline. The generated descriptor still carries the owner's own operation
// budget and is forwarded unchanged; the edge transport adds only bounded
// response propagation allowance. Without detaching that inner deadline, both
// boundaries expire together and a valid owner response at the end of its SLO
// is nondeterministically rewritten as a gateway failure.
type ownerProxyBudgetTransport struct {
	next      http.RoundTripper
	allowance time.Duration
}

func (transport ownerProxyBudgetTransport) RoundTrip(
	request *http.Request,
) (*http.Response, error) {
	descriptor, ok := rtauth.OperationDescriptorFromContext(request.Context())
	if !ok || descriptor.TimeoutMilliseconds <= 0 {
		return nil, errors.New("api-edge owner proxy operation budget is unavailable")
	}
	cancellationParent, ok := ownerProxyCancellationContext(request.Context())
	if !ok {
		return nil, errors.New("api-edge owner proxy cancellation context is unavailable")
	}
	operationDeadline, ok := request.Context().Deadline()
	if !ok {
		return nil, errors.New("api-edge owner proxy operation deadline is unavailable")
	}
	outerDeadline := operationDeadline.Add(transport.allowance)
	if !outerDeadline.After(operationDeadline) {
		return nil, errors.New("api-edge owner proxy budget overflow")
	}

	// WithoutCancel retains authenticated principal, operation identity, trace
	// and rollout values while replacing only the owner's inner deadline. The
	// edge deadline is the original guard's absolute deadline + allowance, so
	// admission/rollout time is never granted again at RoundTrip. The captured
	// pre-guard parent restores real client/server cancellation.
	ctx, cancel := context.WithDeadline(
		context.WithoutCancel(request.Context()),
		outerDeadline,
	)
	stopParentCancellation := context.AfterFunc(cancellationParent, cancel)
	release := func() {
		stopParentCancellation()
		cancel()
	}
	response, err := transport.next.RoundTrip(request.WithContext(ctx))
	if err != nil {
		if response != nil && response.Body != nil {
			_ = response.Body.Close()
		}
		release()
		return response, err
	}
	if response == nil {
		release()
		return nil, errors.New("api-edge owner proxy transport returned no response")
	}
	if response.Body == nil {
		release()
		response.Body = http.NoBody
		return response, nil
	}
	// RoundTrip completes when response headers arrive; the deadline and parent
	// cancellation bridge must remain alive while ReverseProxy copies the body.
	response.Body = &ownerProxyDeadlineBody{
		ReadCloser: response.Body,
		release:    release,
	}
	return response, nil
}

type ownerProxyDeadlineBody struct {
	io.ReadCloser
	releaseOnce sync.Once
	release     func()
}

func (body *ownerProxyDeadlineBody) Read(buffer []byte) (int, error) {
	count, err := body.ReadCloser.Read(buffer)
	if err != nil {
		body.releaseResources()
	}
	return count, err
}

func (body *ownerProxyDeadlineBody) Close() error {
	defer body.releaseResources()
	return body.ReadCloser.Close()
}

func (body *ownerProxyDeadlineBody) releaseResources() {
	if body == nil {
		return
	}
	body.releaseOnce.Do(body.release)
}

type ownerProxyFailureKind string

const (
	ownerProxyFailureDeadline         ownerProxyFailureKind = "deadline_exceeded"
	ownerProxyFailureCanceled         ownerProxyFailureKind = "upstream_canceled"
	ownerProxyFailureTransportTimeout ownerProxyFailureKind = "transport_timeout"
	ownerProxyFailureUnavailable      ownerProxyFailureKind = "connection_unavailable"
)

func classifyOwnerProxyFailure(proxyErr error) ownerProxyFailureKind {
	// Inspect the transport's concrete cause only. request.Context() carries the
	// intentionally narrower owner-operation deadline and may already be done
	// while the independent edge transport is still valid; consulting it here
	// would overwrite a later concrete dial/refusal cause with stale timeout.
	if errors.Is(proxyErr, context.DeadlineExceeded) {
		return ownerProxyFailureDeadline
	}
	if errors.Is(proxyErr, context.Canceled) {
		return ownerProxyFailureCanceled
	}
	var networkError net.Error
	if errors.As(proxyErr, &networkError) && networkError.Timeout() {
		return ownerProxyFailureTransportTimeout
	}
	return ownerProxyFailureUnavailable
}

func ownerProxyCallerCanceled(request *http.Request) bool {
	if request == nil {
		return false
	}
	if parent, ok := ownerProxyCancellationContext(request.Context()); ok {
		return parent.Err() != nil
	}
	return errors.Is(request.Context().Err(), context.Canceled)
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
