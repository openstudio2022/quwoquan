package publicweb

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"io"
	"mime"
	"net"
	"net/http"
	"strings"
	"time"

	application "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/publicweb"
)

const (
	defaultMaxResponseBytes int64 = 2 << 20
	defaultRequestTimeout         = 15 * time.Second
	defaultMaxRedirects           = 5
)

type Dialer interface {
	DialContext(context.Context, string, string) (net.Conn, error)
}

type FetchLimits struct {
	MaxResponseBytes int64
	RequestTimeout   time.Duration
	MaxRedirects     int
	UserAgent        string
}

func DefaultFetchLimits() FetchLimits {
	return FetchLimits{
		MaxResponseBytes: defaultMaxResponseBytes,
		RequestTimeout:   defaultRequestTimeout,
		MaxRedirects:     defaultMaxRedirects,
		UserAgent:        "QuwoquanAssistantPublicWeb/1.0",
	}
}

type Fetcher struct {
	policy NetworkPolicy
	client *http.Client
	limits FetchLimits
	now    func() time.Time
}

func NewFetcher(policy NetworkPolicy, limits FetchLimits) *Fetcher {
	transport := NewSecureTransport(policy, &net.Dialer{
		Timeout:   5 * time.Second,
		KeepAlive: 30 * time.Second,
	})
	return newFetcher(policy, &http.Client{Transport: transport}, limits)
}

// NewFetcherWithClient is a test seam for deterministic response simulation.
// Production composition must use NewFetcher so that the final connection is
// pinned to an address revalidated by NewSecureTransport.
func NewFetcherWithClient(
	policy NetworkPolicy,
	client *http.Client,
	limits FetchLimits,
) *Fetcher {
	if client == nil {
		panic("public web http client is required")
	}
	clone := *client
	return newFetcher(policy, &clone, limits)
}

func newFetcher(policy NetworkPolicy, client *http.Client, limits FetchLimits) *Fetcher {
	limits = resolvedLimits(limits)
	client.Timeout = limits.RequestTimeout
	return &Fetcher{policy: policy, client: client, limits: limits, now: time.Now}
}

func NewSecureTransport(policy NetworkPolicy, dialer Dialer) *http.Transport {
	return NewSecureTransportWithTLS(policy, dialer, nil)
}

// NewSecureTransportWithTLS supports a managed outbound trust store without
// weakening hostname verification or attaching client credentials.
func NewSecureTransportWithTLS(
	policy NetworkPolicy,
	dialer Dialer,
	tlsConfig *tls.Config,
) *http.Transport {
	if dialer == nil {
		panic("public web dialer is required")
	}
	resolvedTLS := &tls.Config{}
	if tlsConfig != nil {
		resolvedTLS = tlsConfig.Clone()
	}
	resolvedTLS.MinVersion = tls.VersionTLS12
	resolvedTLS.InsecureSkipVerify = false
	resolvedTLS.Certificates = nil
	resolvedTLS.GetClientCertificate = nil
	return &http.Transport{
		Proxy:              nil,
		DisableCompression: true,
		ForceAttemptHTTP2:  true,
		TLSClientConfig:    resolvedTLS,
		DialContext: func(ctx context.Context, network, address string) (net.Conn, error) {
			host, port, err := net.SplitHostPort(address)
			if err != nil || port != "443" {
				return nil, Rejection{Kind: RejectionPort, Value: address, Cause: err}
			}
			addresses, err := policy.ResolveHost(ctx, host)
			if err != nil {
				return nil, err
			}
			var failures []error
			for _, target := range addresses {
				connection, dialErr := dialer.DialContext(
					ctx,
					network,
					net.JoinHostPort(target.String(), port),
				)
				if dialErr == nil {
					return connection, nil
				}
				failures = append(failures, dialErr)
			}
			return nil, fmt.Errorf("public web dial failed: %w", errors.Join(failures...))
		},
	}
}

func (f *Fetcher) Fetch(ctx context.Context, request application.NetworkRequest) (application.NetworkResult, error) {
	method := strings.ToUpper(strings.TrimSpace(request.Method))
	if method == "" {
		method = http.MethodGet
	}
	if method != http.MethodGet && method != http.MethodHead {
		return application.NetworkResult{}, rejectedTarget(
			Rejection{Kind: RejectionResponse, Value: method},
		)
	}
	target, _, err := f.policy.ResolveURL(ctx, request.URL)
	if err != nil {
		return application.NetworkResult{}, classifyFetchFailure(err)
	}
	redirectChain := make([]string, 0, f.limits.MaxRedirects)
	client := *f.client
	client.CheckRedirect = func(next *http.Request, via []*http.Request) error {
		if len(via) > f.limits.MaxRedirects {
			return Rejection{Kind: RejectionRedirect, Value: next.URL.String()}
		}
		validated, _, resolveErr := f.policy.ResolveURL(next.Context(), next.URL.String())
		if resolveErr != nil {
			return resolveErr
		}
		next.URL = validated
		setSafeHeaders(next.Header, f.limits.UserAgent)
		redirectChain = append(redirectChain, validated.String())
		return nil
	}
	httpRequest, err := http.NewRequestWithContext(ctx, method, target.String(), nil)
	if err != nil {
		return application.NetworkResult{}, rejectedTarget(
			Rejection{Kind: RejectionInvalidURL, Value: request.URL, Cause: err},
		)
	}
	setSafeHeaders(httpRequest.Header, f.limits.UserAgent)
	response, err := client.Do(httpRequest)
	if err != nil {
		return application.NetworkResult{}, classifyFetchFailure(err)
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
		rejection := Rejection{Kind: RejectionResponse, Value: response.Status}
		if response.StatusCode == http.StatusTooManyRequests || response.StatusCode >= 500 {
			return application.NetworkResult{}, unavailableFetch(rejection)
		}
		return application.NetworkResult{}, rejectedTarget(rejection)
	}
	if coding := strings.TrimSpace(response.Header.Get("Content-Encoding")); coding != "" && !strings.EqualFold(coding, "identity") {
		return application.NetworkResult{}, rejectedTarget(
			Rejection{Kind: RejectionContentCoding, Value: coding},
		)
	}
	contentType := response.Header.Get("Content-Type")
	if !allowedContentType(contentType) {
		return application.NetworkResult{}, rejectedTarget(
			Rejection{Kind: RejectionContentType, Value: contentType},
		)
	}
	limit := f.limits.MaxResponseBytes
	if request.MaxBytes > 0 && request.MaxBytes < limit {
		limit = request.MaxBytes
	}
	if response.ContentLength > limit {
		return application.NetworkResult{}, rejectedTarget(
			Rejection{Kind: RejectionContentSize, Value: fmt.Sprint(response.ContentLength)},
		)
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, limit+1))
	if err != nil {
		return application.NetworkResult{}, unavailableFetch(err)
	}
	if int64(len(body)) > limit {
		return application.NetworkResult{}, rejectedTarget(
			Rejection{Kind: RejectionContentSize, Value: fmt.Sprint(len(body))},
		)
	}
	return application.NetworkResult{
		FinalURL:      response.Request.URL.String(),
		RedirectChain: redirectChain,
		ContentType:   contentType,
		Body:          body,
		FetchedAt:     f.now().UTC(),
	}, nil
}

func classifyFetchFailure(err error) error {
	var rejection Rejection
	if errors.As(err, &rejection) {
		if rejection.Kind == RejectionResolution && rejection.Cause != nil {
			return unavailableFetch(err)
		}
		return rejectedTarget(err)
	}
	return unavailableFetch(err)
}

func rejectedTarget(cause error) error {
	return fmt.Errorf("%w: %w", application.ErrTargetRejected, cause)
}

func unavailableFetch(cause error) error {
	return fmt.Errorf("%w: %w", application.ErrFetchUnavailable, cause)
}

func resolvedLimits(limits FetchLimits) FetchLimits {
	if limits.MaxResponseBytes <= 0 {
		limits.MaxResponseBytes = defaultMaxResponseBytes
	}
	if limits.RequestTimeout <= 0 {
		limits.RequestTimeout = defaultRequestTimeout
	}
	if limits.MaxRedirects <= 0 {
		limits.MaxRedirects = defaultMaxRedirects
	}
	if strings.TrimSpace(limits.UserAgent) == "" {
		limits.UserAgent = "QuwoquanAssistantPublicWeb/1.0"
	}
	return limits
}

func setSafeHeaders(header http.Header, userAgent string) {
	for key := range header {
		header.Del(key)
	}
	header.Set("Accept", "text/html, application/xhtml+xml, text/plain;q=0.9")
	header.Set("Accept-Encoding", "identity")
	header.Set("User-Agent", userAgent)
}

func allowedContentType(raw string) bool {
	mediaType, _, err := mime.ParseMediaType(raw)
	if err != nil {
		return false
	}
	switch strings.ToLower(mediaType) {
	case "text/html", "application/xhtml+xml", "text/plain":
		return true
	default:
		return false
	}
}
