package recommendation

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"time"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rtgov "quwoquan_service/runtime/governance"
	rtrec "quwoquan_service/runtime/recommendation"
)

const recommendationScoringOperationID = "recommendation.model_release.ScoreRecommendationCandidates"

// HTTPModelServiceClient calls the generated ModelRelease scoring Reader operation.
// Includes one fast retry with backoff, circuit breaker, and request-level observability logging.
type HTTPModelServiceClient struct {
	baseURL      string
	path         string
	httpClient   *http.Client
	credentials  rtauth.ServiceAuthorizationProvider
	maxRetries   int
	retryBackoff time.Duration
	cb           *rtgov.CircuitBreaker
}

// NewHTTPModelServiceClient resolves method/path from generated ContractGraph descriptors.
// Includes one fast retry (20ms backoff) on transient failures, and a circuit breaker
// (5 failures → open for 10s) to avoid overwhelming a degraded model service.
func NewHTTPModelServiceClient(
	baseURL string,
	timeout time.Duration,
	credentials rtauth.ServiceAuthorizationProvider,
) (*HTTPModelServiceClient, error) {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return nil, fmt.Errorf("model client: valid base URL is required")
	}
	if credentials == nil {
		return nil, fmt.Errorf("model client: service credentials are required")
	}
	path := ""
	for _, descriptor := range operationsecurity.ForDomain("recommendation") {
		if descriptor.CanonicalOperationID != recommendationScoringOperationID {
			continue
		}
		if descriptor.Method != http.MethodPost ||
			descriptor.PathTemplate == "" ||
			strings.ContainsAny(descriptor.PathTemplate, "{}") {
			return nil, fmt.Errorf("model client: generated scoring descriptor is invalid")
		}
		path = descriptor.PathTemplate
		break
	}
	if path == "" {
		return nil, fmt.Errorf("model client: generated scoring descriptor is missing")
	}
	if timeout <= 0 {
		timeout = 50 * time.Millisecond
	}
	return &HTTPModelServiceClient{
		baseURL: strings.TrimRight(parsed.String(), "/"),
		path:    path,
		httpClient: &http.Client{
			Timeout: timeout,
		},
		credentials:  credentials,
		maxRetries:   1,
		retryBackoff: 20 * time.Millisecond,
		cb:           rtgov.NewCircuitBreaker(5, 10*time.Second, slog.Default()),
	}, nil
}

// Predict sends the request to rec-model-service /v1/score and returns the response.
func (c *HTTPModelServiceClient) Predict(ctx context.Context, req *rtrec.ModelPredictRequest) (*rtrec.ModelPredictResponse, error) {
	if !c.cb.Allow() {
		return nil, fmt.Errorf("model client: circuit breaker open")
	}

	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("model client: marshal request: %w", err)
	}

	start := time.Now()
	var lastErr error
	for attempt := 0; attempt <= c.maxRetries; attempt++ {
		if attempt > 0 {
			timer := time.NewTimer(c.retryBackoff)
			select {
			case <-ctx.Done():
				timer.Stop()
				return nil, ctx.Err()
			case <-timer.C:
			}
		}
		resp, err := c.doOnce(ctx, body)
		elapsed := time.Since(start)
		if err != nil {
			lastErr = err
			c.cb.RecordFailure()
			slog.Warn("rec-model predict attempt failed",
				"attempt", attempt+1,
				"elapsed_ms", elapsed.Milliseconds(),
				"error", err,
				"candidates", len(req.Candidates),
			)
			continue
		}
		c.cb.RecordSuccess()
		slog.Debug("rec-model predict ok",
			"attempt", attempt+1,
			"elapsed_ms", elapsed.Milliseconds(),
			"candidates", len(req.Candidates),
			"scored", len(resp.Scores),
		)
		return resp, nil
	}
	return nil, lastErr
}

func (c *HTTPModelServiceClient) doOnce(ctx context.Context, body []byte) (*rtrec.ModelPredictResponse, error) {
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+c.path, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("model client: new request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	authorization, err := c.credentials.AuthorizationHeader(ctx)
	if err != nil {
		return nil, fmt.Errorf("model client: service authorization: %w", err)
	}
	httpReq.Header.Set("Authorization", authorization)

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("model client: do request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("model client: status %d", resp.StatusCode)
	}

	var out rtrec.ModelPredictResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, fmt.Errorf("model client: decode response: %w", err)
	}
	return &out, nil
}
