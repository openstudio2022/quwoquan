package recommendation

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	rtgov "quwoquan_service/runtime/governance"
	rtrec "quwoquan_service/runtime/recommendation"
)

// HTTPModelServiceClient implements rtrec.ModelServiceClient by calling rec-model-service POST /v1/score.
// Includes one fast retry with backoff, circuit breaker, and request-level observability logging.
type HTTPModelServiceClient struct {
	baseURL      string
	httpClient   *http.Client
	maxRetries   int
	retryBackoff time.Duration
	cb           *rtgov.CircuitBreaker
}

// NewHTTPModelServiceClient creates a client that POSTs to baseURL/v1/score with the given timeout.
// Includes one fast retry (20ms backoff) on transient failures, and a circuit breaker
// (5 failures → open for 10s) to avoid overwhelming a degraded model service.
func NewHTTPModelServiceClient(baseURL string, timeout time.Duration) *HTTPModelServiceClient {
	if timeout <= 0 {
		timeout = 50 * time.Millisecond
	}
	return &HTTPModelServiceClient{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: timeout,
		},
		maxRetries:   1,
		retryBackoff: 20 * time.Millisecond,
		cb:           rtgov.NewCircuitBreaker(5, 10*time.Second, slog.Default()),
	}
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
			time.Sleep(c.retryBackoff)
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
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/v1/score", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("model client: new request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

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
