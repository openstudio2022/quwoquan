package auth

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// AccountSecuritySnapshot is the complete cross-service account-security
// contract. It intentionally excludes persona, profile, credential, device,
// enforcement-case, and all other identifying data.
type AccountSecuritySnapshot struct {
	AccountState string `json:"accountState"`
	AuthEpoch    int64  `json:"authEpoch"`
}

// AccountSecurityAuthority is the synchronous authority queried after an end
// user access JWT has passed cryptographic verification. A caller must treat
// every error as a deny; it must never retain or use a previous response.
type AccountSecurityAuthority interface {
	ReadAccountSecurity(
		ctx context.Context,
		accountID string,
	) (AccountSecuritySnapshot, error)
}

// AccountSecurityAuthorityHealthChecker is implemented by remote authorities
// that can prove their scoped service credential and backing authority read in
// a readiness check. Resource services register it in readiness rather than
// treating construction success as dependency health.
type AccountSecurityAuthorityHealthChecker interface {
	CheckAccountSecurityAuthority(ctx context.Context) error
}

var (
	// ErrAccountSecurityNotFound means the authority confirmed that the token
	// subject no longer has an account. It is deliberately separate from an
	// authority transport failure so middleware can return the canonical
	// terminal-account rejection instead of a transient error.
	ErrAccountSecurityNotFound = errors.New("account security subject not found")

	// ErrAccountSecurityUnavailable includes client credential failures,
	// timeouts, network failures, non-success responses, and invalid response
	// bodies. Its text is deliberately identifier-free for safe logs/metrics.
	ErrAccountSecurityUnavailable = errors.New("account security authority unavailable")
)

const (
	accountSecurityAuthorityPathPrefix = "/internal/user/accounts/"
	accountSecurityAuthorityHealthPath = "/internal/user/account-security/health"
)

type accountSecurityAuthorityCorrelationContextKey struct{}

type accountSecurityAuthorityCorrelation struct {
	requestID string
	traceID   string
}

// HTTPAccountSecurityAuthorityConfig binds the generated UserAccount internal
// read operation to a resource service. The caller must pass an explicitly
// configured short-timeout client and a scoped service credential provider;
// default clients and unauthenticated fallback are intentionally prohibited.
type HTTPAccountSecurityAuthorityConfig struct {
	BaseURL     string
	HTTPClient  *http.Client
	Credentials ServiceAuthorizationProvider
	Timeout     time.Duration
}

// HTTPAccountSecurityAuthority is the fail-closed remote implementation of
// AccountSecurityAuthority. It carries neither a subject cache nor a response
// cache because a cached active snapshot would re-open the post-close window.
type HTTPAccountSecurityAuthority struct {
	baseURL     *url.URL
	httpClient  *http.Client
	credentials ServiceAuthorizationProvider
	timeout     time.Duration
}

var _ AccountSecurityAuthority = (*HTTPAccountSecurityAuthority)(nil)
var _ AccountSecurityAuthorityHealthChecker = (*HTTPAccountSecurityAuthority)(nil)

func NewHTTPAccountSecurityAuthority(
	config HTTPAccountSecurityAuthorityConfig,
) (*HTTPAccountSecurityAuthority, error) {
	baseURL, err := parseInternalAuthorityBaseURL(config.BaseURL)
	if err != nil {
		return nil, err
	}
	if config.HTTPClient == nil {
		return nil, fmt.Errorf("account security authority HTTP client is required")
	}
	if config.Credentials == nil {
		return nil, fmt.Errorf("account security authority service credentials are required")
	}
	if config.Timeout <= 0 {
		return nil, fmt.Errorf("account security authority timeout must be positive")
	}
	// The scoped workload credential is valid only for the configured
	// authority origin. Never follow a redirect, which could otherwise relay
	// that credential to an unintended internal or external endpoint.
	httpClient := *config.HTTPClient
	httpClient.CheckRedirect = func(
		_ *http.Request,
		_ []*http.Request,
	) error {
		return http.ErrUseLastResponse
	}
	return &HTTPAccountSecurityAuthority{
		baseURL:     baseURL,
		httpClient:  &httpClient,
		credentials: config.Credentials,
		timeout:     config.Timeout,
	}, nil
}

func (authority *HTTPAccountSecurityAuthority) ReadAccountSecurity(
	ctx context.Context,
	accountID string,
) (AccountSecuritySnapshot, error) {
	if authority == nil || authority.baseURL == nil ||
		authority.httpClient == nil || authority.credentials == nil ||
		authority.timeout <= 0 {
		return AccountSecuritySnapshot{}, ErrAccountSecurityUnavailable
	}
	normalizedAccountID := strings.TrimSpace(accountID)
	if normalizedAccountID == "" {
		return AccountSecuritySnapshot{}, ErrAccountSecurityUnavailable
	}
	requestContext, cancel := context.WithTimeout(ctx, authority.timeout)
	defer cancel()

	authorization, err := authority.credentials.AuthorizationHeader(requestContext)
	if err != nil || strings.TrimSpace(authorization) == "" {
		return AccountSecuritySnapshot{}, ErrAccountSecurityUnavailable
	}

	target := *authority.baseURL
	target.Path = accountSecurityAuthorityPathPrefix + normalizedAccountID + "/security"
	target.RawPath = accountSecurityAuthorityPathPrefix +
		url.PathEscape(normalizedAccountID) + "/security"
	request, err := http.NewRequestWithContext(
		requestContext,
		http.MethodGet,
		target.String(),
		nil,
	)
	if err != nil {
		return AccountSecuritySnapshot{}, ErrAccountSecurityUnavailable
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Cache-Control", "no-store")
	applyAccountSecurityAuthorityCorrelation(request.Header, requestContext)

	response, err := authority.httpClient.Do(request)
	if err != nil {
		return AccountSecuritySnapshot{}, ErrAccountSecurityUnavailable
	}
	defer response.Body.Close()

	switch response.StatusCode {
	case http.StatusOK:
		snapshot, decodeErr := decodeAccountSecuritySnapshot(response.Body)
		if decodeErr != nil {
			return AccountSecuritySnapshot{}, ErrAccountSecurityUnavailable
		}
		return snapshot, nil
	case http.StatusNotFound:
		// Consume only a bounded body and never propagate its content; user
		// service error responses may carry request/trace metadata.
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
		return AccountSecuritySnapshot{}, ErrAccountSecurityNotFound
	default:
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
		return AccountSecuritySnapshot{}, ErrAccountSecurityUnavailable
	}
}

// CheckAccountSecurityAuthority validates the caller's service principal,
// required scope, route binding, and backing UserAccount read without carrying
// an end-user subject. It is safe to expose through readiness telemetry because
// it returns no account data.
func (authority *HTTPAccountSecurityAuthority) CheckAccountSecurityAuthority(
	ctx context.Context,
) error {
	if authority == nil || authority.baseURL == nil ||
		authority.httpClient == nil || authority.credentials == nil ||
		authority.timeout <= 0 {
		return ErrAccountSecurityUnavailable
	}
	requestContext, cancel := context.WithTimeout(ctx, authority.timeout)
	defer cancel()
	authorization, err := authority.credentials.AuthorizationHeader(requestContext)
	if err != nil || strings.TrimSpace(authorization) == "" {
		return ErrAccountSecurityUnavailable
	}
	target := *authority.baseURL
	target.Path = accountSecurityAuthorityHealthPath
	target.RawPath = ""
	request, err := http.NewRequestWithContext(
		requestContext,
		http.MethodGet,
		target.String(),
		nil,
	)
	if err != nil {
		return ErrAccountSecurityUnavailable
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Cache-Control", "no-store")
	applyAccountSecurityAuthorityCorrelation(request.Header, requestContext)
	response, err := authority.httpClient.Do(request)
	if err != nil {
		return ErrAccountSecurityUnavailable
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
		return ErrAccountSecurityUnavailable
	}
	var health struct {
		Status string `json:"status"`
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, 4096))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&health); err != nil ||
		strings.TrimSpace(health.Status) != "ok" {
		return ErrAccountSecurityUnavailable
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return ErrAccountSecurityUnavailable
	}
	return nil
}

func parseInternalAuthorityBaseURL(raw string) (*url.URL, error) {
	value := strings.TrimRight(strings.TrimSpace(raw), "/")
	if value == "" {
		return nil, fmt.Errorf("account security authority base URL is required")
	}
	parsed, err := url.Parse(value)
	if err != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") ||
		parsed.Host == "" ||
		parsed.User != nil ||
		parsed.RawQuery != "" ||
		parsed.Fragment != "" ||
		parsed.Path != "" {
		return nil, fmt.Errorf(
			"account security authority base URL must be an absolute http(s) origin without credentials, path, query, or fragment",
		)
	}
	return parsed, nil
}

func withAccountSecurityAuthorityCorrelation(
	ctx context.Context,
	headers http.Header,
) context.Context {
	if headers == nil {
		return ctx
	}
	correlation := accountSecurityAuthorityCorrelation{
		requestID: strings.TrimSpace(headers.Get("X-Request-Id")),
		traceID:   strings.TrimSpace(headers.Get("X-Trace-Id")),
	}
	if correlation.traceID == "" {
		correlation.traceID = correlation.requestID
	}
	if correlation.requestID == "" && correlation.traceID == "" {
		return ctx
	}
	return context.WithValue(
		ctx,
		accountSecurityAuthorityCorrelationContextKey{},
		correlation,
	)
}

func applyAccountSecurityAuthorityCorrelation(
	headers http.Header,
	ctx context.Context,
) {
	correlation, ok := ctx.Value(
		accountSecurityAuthorityCorrelationContextKey{},
	).(accountSecurityAuthorityCorrelation)
	if !ok {
		return
	}
	if correlation.requestID != "" {
		headers.Set("X-Request-Id", correlation.requestID)
	}
	if correlation.traceID != "" {
		headers.Set("X-Trace-Id", correlation.traceID)
	}
}

func decodeAccountSecuritySnapshot(
	body io.Reader,
) (AccountSecuritySnapshot, error) {
	var snapshot AccountSecuritySnapshot
	decoder := json.NewDecoder(io.LimitReader(body, 4096))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&snapshot); err != nil {
		return AccountSecuritySnapshot{}, err
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return AccountSecuritySnapshot{}, errors.New("unexpected account security response payload")
	}
	if strings.TrimSpace(snapshot.AccountState) == "" || snapshot.AuthEpoch <= 0 {
		return AccountSecuritySnapshot{}, errors.New("invalid account security response")
	}
	return snapshot, nil
}
