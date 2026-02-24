package recommendation

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// RemoteEmbeddingService calls an external embedding API (e.g., OpenAI, self-hosted).
// Implements EmbeddingService interface.
type RemoteEmbeddingService struct {
	endpoint string
	apiKey   string
	model    string
	client   *http.Client
}

type RemoteEmbeddingOption func(*RemoteEmbeddingService)

func WithEmbeddingModel(model string) RemoteEmbeddingOption {
	return func(s *RemoteEmbeddingService) { s.model = model }
}

func WithEmbeddingClient(c *http.Client) RemoteEmbeddingOption {
	return func(s *RemoteEmbeddingService) { s.client = c }
}

func NewRemoteEmbeddingService(endpoint, apiKey string, opts ...RemoteEmbeddingOption) *RemoteEmbeddingService {
	s := &RemoteEmbeddingService{
		endpoint: endpoint,
		apiKey:   apiKey,
		model:    "text-embedding-3-small",
		client: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
	for _, opt := range opts {
		opt(s)
	}
	return s
}

type embeddingRequest struct {
	Model string   `json:"model"`
	Input []string `json:"input"`
}

type embeddingResponse struct {
	Data []struct {
		Embedding []float64 `json:"embedding"`
		Index     int       `json:"index"`
	} `json:"data"`
}

func (s *RemoteEmbeddingService) Embed(ctx context.Context, text string) ([]float64, error) {
	results, err := s.EmbedBatch(ctx, []string{text})
	if err != nil {
		return nil, err
	}
	if len(results) == 0 {
		return nil, fmt.Errorf("empty embedding response")
	}
	return results[0], nil
}

func (s *RemoteEmbeddingService) EmbedBatch(ctx context.Context, texts []string) ([][]float64, error) {
	if len(texts) == 0 {
		return nil, nil
	}

	body, err := json.Marshal(embeddingRequest{
		Model: s.model,
		Input: texts,
	})
	if err != nil {
		return nil, fmt.Errorf("marshal embedding request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", s.endpoint, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("create embedding request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if s.apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+s.apiKey)
	}

	resp, err := s.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("embedding request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return nil, fmt.Errorf("embedding service returned %d: %s", resp.StatusCode, string(respBody))
	}

	var result embeddingResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode embedding response: %w", err)
	}

	embeddings := make([][]float64, len(texts))
	for _, d := range result.Data {
		if d.Index < len(embeddings) {
			embeddings[d.Index] = d.Embedding
		}
	}
	return embeddings, nil
}
