// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
//
// API Edge owner proxy budget/error contract: the edge transport owns a wider
// deadline than the owner operation, preserves an owner's typed timeout, and
// never collapses timeout/cancellation into a connection-unavailable 503.
package local_contract

import (
	"context"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	httpadapter "quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/adapters/inbound/http"
)

type roundTripperFunc func(*http.Request) (*http.Response, error)

func (function roundTripperFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return function(request)
}

func TestDirectSearchProxyOwnsWiderDeadlineAndReturnsOwnerSuccess(t *testing.T) {
	t.Parallel()
	descriptor := generatedSearchDescriptor(t)
	if descriptor.TimeoutMilliseconds != 1500 {
		t.Fatalf("Search owner timeout = %dms, want 1500ms", descriptor.TimeoutMilliseconds)
	}
	var remaining time.Duration
	transport := roundTripperFunc(func(request *http.Request) (*http.Response, error) {
		deadline, ok := request.Context().Deadline()
		if !ok {
			t.Fatal("owner proxy outbound request has no edge deadline")
		}
		remaining = time.Until(deadline)
		return ownerResponse(request, http.StatusOK, `{"items":[]}`), nil
	})
	handler := newSearchProxyHandler(
		t,
		"http://search-owner.invalid",
		transport,
		descriptor,
		500*time.Millisecond,
	)

	recorder := executeSearchProxyRequest(handler, context.Background())
	if recorder.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200 (body=%s)", recorder.Code, recorder.Body.String())
	}
	// Allow scheduling noise while proving the outbound deadline is the
	// independent 1500ms + 500ms edge budget, not the inherited 1500ms owner
	// deadline that caused the production race.
	if remaining < 1850*time.Millisecond || remaining > 2050*time.Millisecond {
		t.Fatalf("edge deadline remaining = %s, want approximately 2s", remaining)
	}
}

func TestDirectSearchProxyUsesAbsoluteGuardDeadlineAfterAdmission(t *testing.T) {
	t.Parallel()
	descriptor := generatedSearchDescriptor(t)
	descriptor.TimeoutMilliseconds = 200
	var remaining time.Duration
	transport := roundTripperFunc(func(request *http.Request) (*http.Response, error) {
		deadline, ok := request.Context().Deadline()
		if !ok {
			t.Fatal("owner proxy outbound request has no edge deadline")
		}
		remaining = time.Until(deadline)
		return ownerResponse(request, http.StatusOK, `{"items":[]}`), nil
	})
	handler := newSearchProxyHandlerAfterAdmissionDelay(
		t,
		"http://search-owner.invalid",
		transport,
		descriptor,
		100*time.Millisecond,
		100*time.Millisecond,
	)

	recorder := executeSearchProxyRequest(handler, context.Background())
	if recorder.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200 (body=%s)", recorder.Code, recorder.Body.String())
	}
	// The absolute edge deadline is guard-start + 200ms owner + 100ms
	// allowance. Admission already consumed ~100ms, so RoundTrip must observe
	// only ~200ms remaining rather than reopening a fresh 300ms window.
	if remaining < 140*time.Millisecond || remaining > 240*time.Millisecond {
		t.Fatalf("remaining edge budget = %s, want approximately 200ms", remaining)
	}
}

func TestDirectSearchProxyKeepsDeadlineAliveUntilDelayedBodyEOF(t *testing.T) {
	t.Parallel()
	descriptor := generatedSearchDescriptor(t)
	descriptor.TimeoutMilliseconds = 100
	owner := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
		response.Header().Set("Content-Type", "application/json")
		response.WriteHeader(http.StatusOK)
		flusher, ok := response.(http.Flusher)
		if !ok {
			t.Error("httptest owner does not expose http.Flusher")
			return
		}
		flusher.Flush()
		time.Sleep(130 * time.Millisecond)
		_, _ = response.Write([]byte(`{"items":["delayed-body"]}`))
	}))
	defer owner.Close()
	handler := newSearchProxyHandler(
		t,
		owner.URL,
		nil,
		descriptor,
		150*time.Millisecond,
	)

	recorder := executeSearchProxyRequest(handler, context.Background())
	if recorder.Code != http.StatusOK ||
		!strings.Contains(recorder.Body.String(), "delayed-body") {
		t.Fatalf(
			"delayed body was canceled after headers: status=%d body=%q",
			recorder.Code,
			recorder.Body.String(),
		)
	}
}

func TestDirectSearchProxyPreservesOwnerTypedTimeoutAfterInnerDeadline(t *testing.T) {
	t.Parallel()
	descriptor := generatedSearchDescriptor(t)
	// Scale the same nested-budget relationship down for a focused test. The
	// owner returns its canonical timeout after the 100ms inner deadline but
	// before API Edge's 250ms transport deadline.
	descriptor.TimeoutMilliseconds = 100
	owner := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
		time.Sleep(120 * time.Millisecond)
		response.Header().Set("Content-Type", "application/json")
		response.WriteHeader(http.StatusServiceUnavailable)
		_, _ = response.Write([]byte(`{"code":"SEARCH.MIDDLEWARE.unavailable"}`))
	}))
	defer owner.Close()
	handler := newSearchProxyHandler(
		t,
		owner.URL,
		nil,
		descriptor,
		150*time.Millisecond,
	)

	recorder := executeSearchProxyRequest(handler, context.Background())
	if recorder.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want owner 503 (body=%s)", recorder.Code, recorder.Body.String())
	}
	var body struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode owner timeout body %q: %v", recorder.Body.String(), err)
	}
	if body.Code != "SEARCH.MIDDLEWARE.unavailable" {
		t.Fatalf("owner first cause was rewritten: code=%s", body.Code)
	}
}

func TestOwnerProxyDeadlineAndCancellationUseTypedTimeout(t *testing.T) {
	t.Parallel()
	descriptor := generatedSearchDescriptor(t)
	descriptor.TimeoutMilliseconds = 20
	waitForCancellation := roundTripperFunc(func(request *http.Request) (*http.Response, error) {
		<-request.Context().Done()
		return nil, request.Context().Err()
	})

	t.Run("edge deadline", func(t *testing.T) {
		handler := newSearchProxyHandler(
			t,
			"http://search-owner.invalid",
			waitForCancellation,
			descriptor,
			20*time.Millisecond,
		)
		recorder := executeSearchProxyRequest(handler, context.Background())
		assertGatewayProxyError(
			t,
			recorder,
			http.StatusGatewayTimeout,
			"GATEWAY.MIDDLEWARE.upstream_timeout",
			"deadline_exceeded",
		)
	})

	t.Run("client cancellation", func(t *testing.T) {
		handler := newSearchProxyHandler(
			t,
			"http://search-owner.invalid",
			waitForCancellation,
			descriptor,
			20*time.Millisecond,
		)
		ctx, cancel := context.WithCancel(context.Background())
		cancel()
		recorder := executeSearchProxyRequest(handler, ctx)
		assertCanceledRequestWritesNoRetryableGatewayError(t, recorder)
	})

	t.Run("live request upstream cancellation", func(t *testing.T) {
		cancelAtOwner := roundTripperFunc(func(*http.Request) (*http.Response, error) {
			return nil, context.Canceled
		})
		handler := newSearchProxyHandler(
			t,
			"http://search-owner.invalid",
			cancelAtOwner,
			descriptor,
			20*time.Millisecond,
		)
		recorder := executeSearchProxyRequest(handler, context.Background())
		assertGatewayProxyError(
			t,
			recorder,
			http.StatusServiceUnavailable,
			"GATEWAY.MIDDLEWARE.upstream_unavailable",
			"upstream_canceled",
		)
	})
}

func TestOwnerProxyTrueConnectionRefusalUsesUpstreamUnavailable(t *testing.T) {
	t.Parallel()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("reserve refusal address: %v", err)
	}
	origin := "http://" + listener.Addr().String()
	if err := listener.Close(); err != nil {
		t.Fatalf("close refusal listener: %v", err)
	}
	descriptor := generatedSearchDescriptor(t)
	descriptor.TimeoutMilliseconds = 200
	handler := newSearchProxyHandler(
		t,
		origin,
		&http.Transport{DisableKeepAlives: true},
		descriptor,
		100*time.Millisecond,
	)

	recorder := executeSearchProxyRequest(handler, context.Background())
	assertGatewayProxyError(
		t,
		recorder,
		http.StatusServiceUnavailable,
		"GATEWAY.MIDDLEWARE.upstream_unavailable",
		"connection_unavailable",
	)
}

func newSearchProxyHandler(
	t *testing.T,
	originValue string,
	transport http.RoundTripper,
	descriptor rtauth.OperationSecurityDescriptor,
	allowance time.Duration,
) http.Handler {
	return newSearchProxyHandlerAfterAdmissionDelay(
		t, originValue, transport, descriptor, allowance, 0,
	)
}

func newSearchProxyHandlerAfterAdmissionDelay(
	t *testing.T,
	originValue string,
	transport http.RoundTripper,
	descriptor rtauth.OperationSecurityDescriptor,
	allowance time.Duration,
	admissionDelay time.Duration,
) http.Handler {
	t.Helper()
	origin, err := url.Parse(originValue)
	if err != nil {
		t.Fatalf("parse owner origin: %v", err)
	}
	proxy, err := httpadapter.NewOwnerProxy(httpadapter.OwnerProxyConfig{
		Routes: []httpadapter.OwnerRoute{{
			OperationPrefix: "search.", Upstream: origin,
		}},
		Transport:       transport,
		BudgetAllowance: allowance,
	})
	if err != nil {
		t.Fatalf("build owner proxy: %v", err)
	}
	var ownerHandler http.Handler = proxy
	if admissionDelay > 0 {
		ownerHandler = http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
			time.Sleep(admissionDelay)
			proxy.ServeHTTP(response, request)
		})
	}
	guarded := rtauth.RequireGeneratedOperationAuthorization(
		[]rtauth.OperationSecurityDescriptor{descriptor},
	)(ownerHandler)
	return httpadapter.PreserveCredentialTransport(guarded)
}

func assertCanceledRequestWritesNoRetryableGatewayError(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
) {
	t.Helper()
	if retry := recorder.Header().Get("Retry-After"); retry != "" {
		t.Fatalf("canceled request Retry-After = %q, want no retry instruction", retry)
	}
	if recorder.Body.Len() != 0 {
		t.Fatalf("canceled request wrote a gateway error: %s", recorder.Body.String())
	}
	if contentType := recorder.Header().Get("Content-Type"); contentType != "" {
		t.Fatalf("canceled request Content-Type = %q, want no response emission", contentType)
	}
}

func generatedSearchDescriptor(t *testing.T) rtauth.OperationSecurityDescriptor {
	t.Helper()
	for _, descriptor := range operationsecurity.ForDomain("search") {
		if descriptor.CanonicalOperationID == "search.search_index_view.Search" {
			return descriptor
		}
	}
	t.Fatal("generated Search operation descriptor is missing")
	return rtauth.OperationSecurityDescriptor{}
}

func executeSearchProxyRequest(handler http.Handler, ctx context.Context) *httptest.ResponseRecorder {
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(
		http.MethodPost,
		"http://api-edge.local/search",
		strings.NewReader(`{"query":"startup"}`),
	).WithContext(ctx)
	request.Header.Set("Content-Type", "application/json")
	handler.ServeHTTP(recorder, request)
	return recorder
}

func ownerResponse(request *http.Request, status int, body string) *http.Response {
	return &http.Response{
		StatusCode: status,
		Status:     http.StatusText(status),
		Header:     http.Header{"Content-Type": []string{"application/json"}},
		Body:       io.NopCloser(strings.NewReader(body)),
		Request:    request,
	}
}

func assertGatewayProxyError(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
	status int,
	code string,
	failureKind string,
) {
	t.Helper()
	if recorder.Code != status {
		t.Fatalf("status = %d, want %d (body=%s)", recorder.Code, status, recorder.Body.String())
	}
	if retry := recorder.Header().Get("Retry-After"); retry != "1" {
		t.Fatalf("Retry-After = %q, want 1", retry)
	}
	var body struct {
		Code    string `json:"code"`
		Context struct {
			Attributes []struct {
				Key   string `json:"key"`
				Value string `json:"value"`
			} `json:"attributes"`
		} `json:"context"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode proxy error body %q: %v", recorder.Body.String(), err)
	}
	if body.Code != code {
		t.Fatalf("code = %s, want %s", body.Code, code)
	}
	for _, attribute := range body.Context.Attributes {
		if attribute.Key == "upstreamFailureKind" && attribute.Value == failureKind {
			return
		}
	}
	t.Fatalf("typed first cause %s missing from context: %+v", failureKind, body.Context.Attributes)
}
