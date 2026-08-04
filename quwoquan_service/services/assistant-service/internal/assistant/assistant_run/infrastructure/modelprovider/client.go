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

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

// TierModels 是档位到具体模型标识的映射。它来自服务配置，不允许在代码里写死。
type TierModels struct {
	Fast      string
	Balanced  string
	Reasoning string
}

type Config struct {
	CompletionURL string
	APIKey        string
	// Models 至少必须提供 Balanced；缺失的档位回落到 Balanced。
	Models TierModels
	// NativeToolCalling 声明该 endpoint 是否已验证支持 tools/tool_choice 协议。
	NativeToolCalling bool
}

type Client struct {
	endpoint          string
	models            TierModels
	apiKey            string
	nativeToolCalling bool
	http              *http.Client
}

type completionWireRequest struct {
	Model          string        `json:"model"`
	Messages       []messageWire `json:"messages"`
	Temperature    float64       `json:"temperature"`
	ResponseFormat *jsonFormat   `json:"response_format,omitempty"`
	Tools          []toolWire    `json:"tools,omitempty"`
	ToolChoice     string        `json:"tool_choice,omitempty"`
	Stream         bool          `json:"stream,omitempty"`
	StreamOptions  *streamOption `json:"stream_options,omitempty"`
}

type messageWire struct {
	Role       string         `json:"role"`
	Content    string         `json:"content"`
	ToolCallID string         `json:"tool_call_id,omitempty"`
	ToolCalls  []toolCallWire `json:"tool_calls,omitempty"`
}

type toolWire struct {
	Type     string          `json:"type"`
	Function toolFunctionDef `json:"function"`
}

type toolFunctionDef struct {
	Name        string         `json:"name"`
	Description string         `json:"description,omitempty"`
	Parameters  map[string]any `json:"parameters"`
}

type toolCallWire struct {
	Index    int              `json:"index"`
	ID       string           `json:"id"`
	Type     string           `json:"type"`
	Function toolCallFunction `json:"function"`
}

type toolCallFunction struct {
	Name      string `json:"name"`
	Arguments string `json:"arguments"`
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

// New 只接收 BindingCompiler 已选 Adapter 的具体材料。模型标识来自服务配置，endpoint
// 与凭据来自 provider binding，均不穿透 application/domain 或运行时厂商开关。
func New(cfg Config, httpClient *http.Client) (*Client, error) {
	completionURL, err := url.Parse(strings.TrimSpace(cfg.CompletionURL))
	if err != nil || completionURL.Scheme == "" || completionURL.Host == "" {
		return nil, fmt.Errorf("model completion url must be absolute")
	}
	if strings.TrimSpace(cfg.APIKey) == "" {
		return nil, fmt.Errorf("model provider credential is unavailable")
	}
	models, err := resolveTierModels(cfg.Models)
	if err != nil {
		return nil, err
	}
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 30 * time.Second}
	}
	return &Client{
		endpoint:          completionURL.String(),
		models:            models,
		apiKey:            cfg.APIKey,
		nativeToolCalling: cfg.NativeToolCalling,
		http:              httpClient,
	}, nil
}

func resolveTierModels(raw TierModels) (TierModels, error) {
	balanced := strings.TrimSpace(raw.Balanced)
	if balanced == "" {
		return TierModels{}, fmt.Errorf("model provider requires a balanced tier model id")
	}
	resolved := TierModels{
		Fast:      strings.TrimSpace(raw.Fast),
		Balanced:  balanced,
		Reasoning: strings.TrimSpace(raw.Reasoning),
	}
	if resolved.Fast == "" {
		resolved.Fast = balanced
	}
	if resolved.Reasoning == "" {
		resolved.Reasoning = balanced
	}
	return resolved, nil
}

// SupportsNativeToolCalling 让 application 显式判断能力，而不是猜测 endpoint 行为。
func (c *Client) SupportsNativeToolCalling() bool {
	return c.nativeToolCalling
}

// SupportsParallelModelRequests is true because Client keeps no request-local
// mutable state; every call owns its wire payload and response stream.
func (c *Client) SupportsParallelModelRequests() bool {
	return c != nil && c.http != nil
}

// SupportsReasoningTier reports the configured provider-neutral tier, not a
// concrete model identity. resolveTierModels guarantees the value is present.
func (c *Client) SupportsReasoningTier() bool {
	return c != nil && strings.TrimSpace(c.models.Reasoning) != ""
}

func (c *Client) modelFor(tier ports.ModelTier) string {
	switch tier {
	case ports.ModelTierFast:
		return c.models.Fast
	case ports.ModelTierReasoning:
		return c.models.Reasoning
	default:
		return c.models.Balanced
	}
}

func servedTier(tier ports.ModelTier) ports.ModelTier {
	switch tier {
	case ports.ModelTierFast, ports.ModelTierBalanced, ports.ModelTierReasoning:
		return tier
	default:
		return ports.ModelTierBalanced
	}
}

func (c *Client) Complete(
	ctx context.Context,
	request ports.ModelCompletionRequest,
) (ports.ModelCompletionResult, error) {
	started := time.Now()
	payload, err := json.Marshal(c.toWireRequest(request))
	if err != nil {
		return ports.ModelCompletionResult{}, ports.ProviderFailure{
			Capability: "model", Reason: ports.ProviderFailureInvalidResponse,
		}
	}
	body, status, err := c.post(ctx, payload, false)
	if err != nil {
		return ports.ModelCompletionResult{}, err
	}
	if status < http.StatusOK || status >= http.StatusMultipleChoices {
		return ports.ModelCompletionResult{}, ports.ProviderFailure{
			Capability: "model", Reason: ports.ProviderFailureUnavailable,
		}
	}
	var decoded completionWireResponse
	if err := json.Unmarshal(body, &decoded); err != nil || len(decoded.Choices) == 0 {
		return ports.ModelCompletionResult{}, ports.ProviderFailure{
			Capability: "model", Reason: ports.ProviderFailureInvalidResponse,
		}
	}
	return ports.ModelCompletionResult{
		Content:      strings.TrimSpace(decoded.Choices[0].Message.Content),
		FinishReason: strings.TrimSpace(decoded.Choices[0].FinishReason),
		Usage:        c.toUsage(decoded.Usage, time.Since(started)),
		ToolCalls:    toApplicationToolCalls(decoded.Choices[0].Message.ToolCalls),
		ModelID:      c.modelFor(request.Tier),
		TierServed:   servedTier(request.Tier),
	}, nil
}

func (c *Client) Stream(
	ctx context.Context,
	request ports.ModelCompletionRequest,
	emit func(ports.ModelTextDelta) error,
) (ports.ModelCompletionResult, error) {
	started := time.Now()
	payload, err := json.Marshal(c.toWireRequest(request))
	if err != nil {
		return ports.ModelCompletionResult{}, ports.ProviderFailure{
			Capability: "model", Reason: ports.ProviderFailureInvalidResponse,
		}
	}
	response, status, err := c.postResponse(ctx, payload, true)
	if err != nil {
		return ports.ModelCompletionResult{}, err
	}
	defer response.Body.Close()
	if status < http.StatusOK || status >= http.StatusMultipleChoices {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 1024))
		return ports.ModelCompletionResult{}, ports.ProviderFailure{
			Capability: "model", Reason: ports.ProviderFailureUnavailable,
		}
	}
	var answer strings.Builder
	var usage usageWire
	finishReason := ""
	toolCalls := newToolCallAccumulator()
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
			return ports.ModelCompletionResult{}, ports.ProviderFailure{
				Capability: "model", Reason: ports.ProviderFailureInvalidResponse,
			}
		}
		if chunk.Usage != (usageWire{}) {
			usage = chunk.Usage
		}
		for _, choice := range chunk.Choices {
			if choice.FinishReason != "" {
				finishReason = choice.FinishReason
			}
			toolCalls.absorb(choice.Delta.ToolCalls)
			if choice.Delta.Content == "" {
				continue
			}
			answer.WriteString(choice.Delta.Content)
			if emit != nil {
				if err := emit(ports.ModelTextDelta{Text: choice.Delta.Content}); err != nil {
					return ports.ModelCompletionResult{}, err
				}
			}
		}
	}
	if err := scanner.Err(); err != nil {
		return ports.ModelCompletionResult{}, providerFailureForTransport(err)
	}
	content := strings.TrimSpace(answer.String())
	collected := toolCalls.collect()
	if content == "" && len(collected) == 0 {
		return ports.ModelCompletionResult{}, ports.ProviderFailure{
			Capability: "model", Reason: ports.ProviderFailureInvalidResponse,
		}
	}
	return ports.ModelCompletionResult{
		Content:      content,
		FinishReason: finishReason,
		Usage:        c.toUsage(usage, time.Since(started)),
		ToolCalls:    collected,
		ModelID:      c.modelFor(request.Tier),
		TierServed:   servedTier(request.Tier),
	}, nil
}

func (c *Client) toWireRequest(
	request ports.ModelCompletionRequest,
) completionWireRequest {
	messages := make([]messageWire, 0, len(request.Messages))
	for _, message := range request.Messages {
		messages = append(messages, messageWire{
			Role:       strings.TrimSpace(message.Role),
			Content:    message.Content,
			ToolCallID: strings.TrimSpace(message.ToolCallID),
		})
	}
	wire := completionWireRequest{
		Model:       c.modelFor(request.Tier),
		Messages:    messages,
		Temperature: 0.2,
		Stream:      request.Stream,
	}
	if request.StructuredOutput {
		wire.ResponseFormat = &jsonFormat{Type: "json_object"}
	}
	if c.nativeToolCalling && len(request.Tools) > 0 {
		wire.Tools = make([]toolWire, 0, len(request.Tools))
		for _, definition := range request.Tools {
			parameters := definition.Parameters
			if parameters == nil {
				parameters = map[string]any{"type": "object", "properties": map[string]any{}}
			}
			wire.Tools = append(wire.Tools, toolWire{
				Type: "function",
				Function: toolFunctionDef{
					Name:        strings.TrimSpace(definition.Name),
					Description: strings.TrimSpace(definition.Description),
					Parameters:  parameters,
				},
			})
		}
		wire.ToolChoice = string(request.ToolChoice)
		if wire.ToolChoice == "" {
			wire.ToolChoice = string(ports.ModelToolChoiceAuto)
		}
	}
	if request.Stream {
		wire.StreamOptions = &streamOption{IncludeUsage: true}
	}
	return wire
}

func toApplicationToolCalls(raw []toolCallWire) []ports.ModelToolCall {
	if len(raw) == 0 {
		return nil
	}
	calls := make([]ports.ModelToolCall, 0, len(raw))
	for _, item := range raw {
		name := strings.TrimSpace(item.Function.Name)
		if name == "" {
			continue
		}
		calls = append(calls, ports.ModelToolCall{
			ID:        strings.TrimSpace(item.ID),
			Name:      name,
			Arguments: strings.TrimSpace(item.Function.Arguments),
		})
	}
	if len(calls) == 0 {
		return nil
	}
	return calls
}

// toolCallAccumulator 复原 SSE 分片的工具调用：name 与 id 通常只在首片出现，arguments
// 按片增量拼接。
type toolCallAccumulator struct {
	order   []int
	byIndex map[int]*toolCallWire
}

func newToolCallAccumulator() *toolCallAccumulator {
	return &toolCallAccumulator{byIndex: map[int]*toolCallWire{}}
}

func (a *toolCallAccumulator) absorb(deltas []toolCallWire) {
	for _, delta := range deltas {
		existing, ok := a.byIndex[delta.Index]
		if !ok {
			a.order = append(a.order, delta.Index)
			copied := delta
			a.byIndex[delta.Index] = &copied
			continue
		}
		if id := strings.TrimSpace(delta.ID); id != "" {
			existing.ID = id
		}
		if name := strings.TrimSpace(delta.Function.Name); name != "" {
			existing.Function.Name = name
		}
		existing.Function.Arguments += delta.Function.Arguments
	}
}

func (a *toolCallAccumulator) collect() []ports.ModelToolCall {
	ordered := make([]toolCallWire, 0, len(a.order))
	for _, index := range a.order {
		ordered = append(ordered, *a.byIndex[index])
	}
	return toApplicationToolCalls(ordered)
}

func (c *Client) toUsage(raw usageWire, latency time.Duration) ports.ModelUsage {
	return ports.ModelUsage{
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
			return nil, 0, ports.ProviderFailure{
				Capability: "model", Reason: ports.ProviderFailureInvalidResponse,
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

func providerFailureForTransport(err error) ports.ProviderFailure {
	if errors.Is(err, context.DeadlineExceeded) {
		return ports.ProviderFailure{
			Capability: "model", Reason: ports.ProviderFailureTimeout,
		}
	}
	return ports.ProviderFailure{
		Capability: "model", Reason: ports.ProviderFailureUnavailable,
	}
}
