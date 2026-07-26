package modelprovider

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
)

type Config struct {
	CompletionURL string
	APIKey        string
}

type Client struct {
	endpoint string
	model    string
	apiKey   string
	http     *http.Client
}

type completionWireRequest struct {
	Model          string        `json:"model"`
	Messages       []messageWire `json:"messages"`
	Temperature    float64       `json:"temperature"`
	ResponseFormat *jsonFormat   `json:"response_format,omitempty"`
	Stream         bool          `json:"stream,omitempty"`
	StreamOptions  *streamOption `json:"stream_options,omitempty"`
}

type messageWire struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type jsonFormat struct {
	Type string `json:"type"`
}

type streamOption struct {
	IncludeUsage bool `json:"include_usage"`
}

type completionWireResponse struct {
	Choices []choiceWire `json:"choices"`
	Usage   usageWire    `json:"usage"`
}

type choiceWire struct {
	Message      messageWire `json:"message"`
	Delta        messageWire `json:"delta"`
	FinishReason string      `json:"finish_reason"`
}

type usageWire struct {
	PromptTokens     int `json:"prompt_tokens"`
	CompletionTokens int `json:"completion_tokens"`
	TotalTokens      int `json:"total_tokens"`
}

// New 只接收 BindingCompiler 已选 Adapter 的具体材料。模型选择、endpoint 与凭据均不
// 穿透 application/domain 或运行时厂商开关。
func New(cfg Config, httpClient *http.Client) (*Client, error) {
	completionURL, err := url.Parse(strings.TrimSpace(cfg.CompletionURL))
	if err != nil || completionURL.Scheme == "" || completionURL.Host == "" {
		return nil, fmt.Errorf("model completion url must be absolute")
	}
	if strings.TrimSpace(cfg.APIKey) == "" {
		return nil, fmt.Errorf("model provider credential is unavailable")
	}
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 30 * time.Second}
	}
	return &Client{
		endpoint: completionURL.String(),
		model:    "mimo-v2-flash",
		apiKey:   cfg.APIKey,
		http:     httpClient,
	}, nil
}

func (c *Client) Complete(
	ctx context.Context,
	request application.ModelCompletionRequest,
) (application.ModelCompletionResult, error) {
	started := time.Now()
	payload, err := json.Marshal(c.toWireRequest(request))
	if err != nil {
		return application.ModelCompletionResult{}, application.ProviderFailure{
			Capability: "model", Reason: application.ProviderFailureInvalidResponse,
		}
	}
	body, status, err := c.post(ctx, payload, false)
	if err != nil {
		return application.ModelCompletionResult{}, err
	}
	if status < http.StatusOK || status >= http.StatusMultipleChoices {
		return application.ModelCompletionResult{}, application.ProviderFailure{
			Capability: "model", Reason: application.ProviderFailureUnavailable,
		}
	}
	var decoded completionWireResponse
	if err := json.Unmarshal(body, &decoded); err != nil || len(decoded.Choices) == 0 {
		return application.ModelCompletionResult{}, application.ProviderFailure{
			Capability: "model", Reason: application.ProviderFailureInvalidResponse,
		}
	}
	return application.ModelCompletionResult{
		Content:      strings.TrimSpace(decoded.Choices[0].Message.Content),
		FinishReason: strings.TrimSpace(decoded.Choices[0].FinishReason),
		Usage:        c.toUsage(decoded.Usage, time.Since(started)),
	}, nil
}

func (c *Client) Stream(
	ctx context.Context,
	request application.ModelCompletionRequest,
	emit func(application.ModelTextDelta) error,
) (application.ModelCompletionResult, error) {
	started := time.Now()
	payload, err := json.Marshal(c.toWireRequest(request))
	if err != nil {
		return application.ModelCompletionResult{}, application.ProviderFailure{
			Capability: "model", Reason: application.ProviderFailureInvalidResponse,
		}
	}
	response, status, err := c.postResponse(ctx, payload, true)
	if err != nil {
		return application.ModelCompletionResult{}, err
	}
	defer response.Body.Close()
	if status < http.StatusOK || status >= http.StatusMultipleChoices {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 1024))
		return application.ModelCompletionResult{}, application.ProviderFailure{
			Capability: "model", Reason: application.ProviderFailureUnavailable,
		}
	}
	var answer strings.Builder
	var usage usageWire
	finishReason := ""
	scanner := bufio.NewScanner(response.Body)
	scanner.Buffer(make([]byte, 64*1024), 2*1024*1024)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if !strings.HasPrefix(line, "data:") {
			continue
		}
		data := strings.TrimSpace(strings.TrimPrefix(line, "data:"))
		if data == "" || data == "[DONE]" {
			continue
		}
		var chunk completionWireResponse
		if err := json.Unmarshal([]byte(data), &chunk); err != nil {
			return application.ModelCompletionResult{}, application.ProviderFailure{
				Capability: "model", Reason: application.ProviderFailureInvalidResponse,
			}
		}
		if chunk.Usage != (usageWire{}) {
			usage = chunk.Usage
		}
		for _, choice := range chunk.Choices {
			if choice.FinishReason != "" {
				finishReason = choice.FinishReason
			}
			if choice.Delta.Content == "" {
				continue
			}
			answer.WriteString(choice.Delta.Content)
			if emit != nil {
				if err := emit(application.ModelTextDelta{Text: choice.Delta.Content}); err != nil {
					return application.ModelCompletionResult{}, err
				}
			}
		}
	}
	if err := scanner.Err(); err != nil {
		return application.ModelCompletionResult{}, providerFailureForTransport(err)
	}
	content := strings.TrimSpace(answer.String())
	if content == "" {
		return application.ModelCompletionResult{}, application.ProviderFailure{
			Capability: "model", Reason: application.ProviderFailureInvalidResponse,
		}
	}
	return application.ModelCompletionResult{
		Content:      content,
		FinishReason: finishReason,
		Usage:        c.toUsage(usage, time.Since(started)),
	}, nil
}

func (c *Client) toWireRequest(
	request application.ModelCompletionRequest,
) completionWireRequest {
	messages := make([]messageWire, 0, len(request.Messages))
	for _, message := range request.Messages {
		messages = append(messages, messageWire{
			Role:    strings.TrimSpace(message.Role),
			Content: message.Content,
		})
	}
	wire := completionWireRequest{
		Model:       c.model,
		Messages:    messages,
		Temperature: 0.2,
		Stream:      request.Stream,
	}
	if request.StructuredOutput {
		wire.ResponseFormat = &jsonFormat{Type: "json_object"}
	}
	if request.Stream {
		wire.StreamOptions = &streamOption{IncludeUsage: true}
	}
	return wire
}

func (c *Client) toUsage(raw usageWire, latency time.Duration) application.ModelUsage {
	return application.ModelUsage{
		PromptTokens:     raw.PromptTokens,
		CompletionTokens: raw.CompletionTokens,
		TotalTokens:      raw.TotalTokens,
		Latency:          latency,
	}
}

func (c *Client) post(
	ctx context.Context,
	payload []byte,
	stream bool,
) ([]byte, int, error) {
	response, status, err := c.postResponse(ctx, payload, stream)
	if err != nil {
		return nil, 0, err
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 1024*1024))
	if err != nil {
		return nil, 0, providerFailureForTransport(err)
	}
	return body, status, nil
}

func (c *Client) postResponse(
	ctx context.Context,
	payload []byte,
	stream bool,
) (*http.Response, int, error) {
	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		request, err := http.NewRequestWithContext(
			ctx,
			http.MethodPost,
			c.endpoint,
			bytes.NewReader(payload),
		)
		if err != nil {
			return nil, 0, application.ProviderFailure{
				Capability: "model", Reason: application.ProviderFailureInvalidResponse,
			}
		}
		request.Header.Set("Authorization", "Bearer "+c.apiKey)
		request.Header.Set("Content-Type", "application/json")
		if stream {
			request.Header.Set("Accept", "text/event-stream")
		}
		response, err := c.http.Do(request)
		if err == nil {
			if response.StatusCode < http.StatusInternalServerError || attempt == 1 {
				return response, response.StatusCode, nil
			}
			_ = response.Body.Close()
			lastErr = errors.New("transient provider status")
		} else {
			lastErr = err
		}
		if attempt == 0 {
			select {
			case <-ctx.Done():
				return nil, 0, providerFailureForTransport(ctx.Err())
			case <-time.After(100 * time.Millisecond):
			}
		}
	}
	return nil, 0, providerFailureForTransport(lastErr)
}

func providerFailureForTransport(err error) application.ProviderFailure {
	if errors.Is(err, context.DeadlineExceeded) {
		return application.ProviderFailure{
			Capability: "model", Reason: application.ProviderFailureTimeout,
		}
	}
	return application.ProviderFailure{
		Capability: "model", Reason: application.ProviderFailureUnavailable,
	}
}
