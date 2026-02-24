package recommendation

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
)

// HTTPModelServiceClient implements rtrec.ModelServiceClient by calling rec-model-service POST /v1/score.
type HTTPModelServiceClient struct {
	baseURL    string
	httpClient *http.Client
}

// NewHTTPModelServiceClient creates a client that POSTs to baseURL/v1/score with the given timeout.
func NewHTTPModelServiceClient(baseURL string, timeout time.Duration) *HTTPModelServiceClient {
	if timeout <= 0 {
		timeout = 50 * time.Millisecond
	}
	return &HTTPModelServiceClient{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: timeout,
		},
	}
}

// Predict sends the request to rec-model-service /v1/score and returns the response.
func (c *HTTPModelServiceClient) Predict(ctx context.Context, req *rtrec.ModelPredictRequest) (*rtrec.ModelPredictResponse, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("model client: marshal request: %w", err)
	}
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
