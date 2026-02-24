package runtimeobservability

import (
	"bytes"
	"io"
	"net/http"
	"time"

	qconfig "quwoquan_service/runtime/config"
)

type HTTPClientFactoryConfig struct {
	RuntimeConfig qconfig.RuntimeConfigProvider
	ConfigPrefix  string
	Timeout      time.Duration
	MaxRetries   int
	RetryBackoff time.Duration
	RetryOnCodes map[int]struct{}
}

func DefaultHTTPClientFactoryConfig() HTTPClientFactoryConfig {
	return HTTPClientFactoryConfig{
		RuntimeConfig: qconfig.EnvRuntimeConfigProvider{},
	}
}

type retryRoundTripper struct {
	base       http.RoundTripper
	maxRetries int
	backoff    time.Duration
	retryCodes map[int]struct{}
}

func (r *retryRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	maxAttempts := r.maxRetries + 1
	var lastResp *http.Response
	var lastErr error

	for attempt := 0; attempt < maxAttempts; attempt++ {
		attemptReq, cloneErr := cloneRequestForRetry(req, attempt)
		if cloneErr != nil {
			return nil, cloneErr
		}

		resp, err := r.base.RoundTrip(attemptReq)
		lastResp = resp
		lastErr = err
		if !r.shouldRetry(resp, err, attempt, maxAttempts) {
			return resp, err
		}

		if resp != nil && resp.Body != nil {
			_ = resp.Body.Close()
		}
		time.Sleep(r.backoff * time.Duration(attempt+1))
	}
	return lastResp, lastErr
}

func (r *retryRoundTripper) shouldRetry(resp *http.Response, err error, attempt int, maxAttempts int) bool {
	if attempt >= maxAttempts-1 {
		return false
	}
	if err != nil {
		return true
	}
	if resp == nil {
		return false
	}
	_, ok := r.retryCodes[resp.StatusCode]
	return ok
}

func cloneRequestForRetry(req *http.Request, attempt int) (*http.Request, error) {
	if attempt == 0 {
		return req.Clone(req.Context()), nil
	}
	cloned := req.Clone(req.Context())
	if req.Body == nil {
		return cloned, nil
	}

	if req.GetBody != nil {
		body, err := req.GetBody()
		if err != nil {
			return nil, err
		}
		cloned.Body = body
		return cloned, nil
	}

	// Fallback for in-memory bodies: buffer once and rebuild.
	raw, err := io.ReadAll(req.Body)
	if err != nil {
		return nil, err
	}
	_ = req.Body.Close()
	req.Body = io.NopCloser(bytes.NewReader(raw))
	req.GetBody = func() (io.ReadCloser, error) {
		return io.NopCloser(bytes.NewReader(raw)), nil
	}
	cloned.Body, _ = req.GetBody()
	return cloned, nil
}

func NewObservedHTTPClient(
	baseTransport http.RoundTripper,
	factoryCfg HTTPClientFactoryConfig,
	logCfg HTTPClientMiddlewareConfig,
	ioLogger *IOAccessLogger,
	processLogger *ProcessTraceLogger,
	exceptionLogger *ExceptionLogger,
) *http.Client {
	if baseTransport == nil {
		baseTransport = http.DefaultTransport
	}
	resolveHTTPClientFactoryConfig(&factoryCfg)

	retryTransport := &retryRoundTripper{
		base:       baseTransport,
		maxRetries: factoryCfg.MaxRetries,
		backoff:    factoryCfg.RetryBackoff,
		retryCodes: factoryCfg.RetryOnCodes,
	}
	loggedTransport := NewLoggedRoundTripper(
		retryTransport,
		logCfg,
		ioLogger,
		processLogger,
		exceptionLogger,
	)
	return &http.Client{
		Timeout:   factoryCfg.Timeout,
		Transport: loggedTransport,
	}
}

func resolveHTTPClientFactoryConfig(cfg *HTTPClientFactoryConfig) {
	if cfg.RuntimeConfig == nil {
		cfg.RuntimeConfig = qconfig.EnvRuntimeConfigProvider{}
	}
	prefix := cfg.ConfigPrefix
	if prefix == "" {
		prefix = "sys.default.http_client"
	}

	if cfg.Timeout <= 0 {
		if v, ok := cfg.RuntimeConfig.GetDurationMs(prefix + ".timeout_ms"); ok {
			cfg.Timeout = v
		}
	}
	if cfg.RetryBackoff <= 0 {
		if v, ok := cfg.RuntimeConfig.GetDurationMs(prefix + ".retry_backoff_ms"); ok {
			cfg.RetryBackoff = v
		}
	}
	if cfg.MaxRetries == 0 {
		if v, ok := cfg.RuntimeConfig.GetInt(prefix + ".retry_max_attempts"); ok && v >= 0 {
			cfg.MaxRetries = v
		}
	}
	if cfg.RetryOnCodes == nil {
		if codes, ok := cfg.RuntimeConfig.GetIntList(prefix + ".retry_on_status_codes"); ok {
			m := make(map[int]struct{}, len(codes))
			for _, c := range codes {
				m[c] = struct{}{}
			}
			cfg.RetryOnCodes = m
		} else {
			// Safe minimal fallback when config missing: no status-code retries.
			cfg.RetryOnCodes = map[int]struct{}{}
		}
	}

	// Safe minimal behavior when config is absent: retry disabled.
	if cfg.RetryBackoff < 0 {
		cfg.RetryBackoff = 0
	}
	if cfg.MaxRetries < 0 {
		cfg.MaxRetries = 0
	}
	if cfg.Timeout < 0 {
		cfg.Timeout = 0
	}
}

