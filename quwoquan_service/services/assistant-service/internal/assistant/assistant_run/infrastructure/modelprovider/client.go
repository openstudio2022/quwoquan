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
	// Models 至少必须提供 Balanced。Fast 缺失时可回落到 Balanced；Reasoning
	// 必须由环境显式声明，禁止把普通档伪装成强推理能力。
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
	Model   string          `json:"model"`
	Choices []choiceWire    `json:"choices"`
	Usage   *usageWire      `json:"usage"`
	Error   json.RawMessage `json:"error"`
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

// SupportsReasoningTier reports only an explicitly configured provider-neutral
// reasoning tier. A balanced model fallback is not evidence of that capability.
func (c *Client) SupportsReasoningTier() bool {
	return c != nil && strings.TrimSpace(c.models.Reasoning) != ""
}

func (c *Client) modelFor(tier ports.ModelTier) (string, ports.ModelTier, bool) {
	switch tier {
	case ports.ModelTierFast:
		model := strings.TrimSpace(c.models.Fast)
		if model == "" {
			return c.models.Balanced, ports.ModelTierBalanced, true
		}
		return model, ports.ModelTierFast, true
	case ports.ModelTierReasoning:
		model := strings.TrimSpace(c.models.Reasoning)
		return model, ports.ModelTierReasoning, model != ""
	default:
		return c.models.Balanced, ports.ModelTierBalanced, true
	}
}

func (c *Client) Complete(
	ctx context.Context,
	request ports.ModelCompletionRequest,
) (ports.ModelCompletionResult, error) {
	started := time.Now()
	model, tierServed, ok := c.modelFor(request.Tier)
	if !ok {
		return ports.ModelCompletionResult{}, ports.ProviderFailure{
			Capability: "model", Reason: ports.ProviderFailureUnavailable,
		}
	}
	payload, err := json.Marshal(c.toWireRequest(request, model))
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
		return ports.ModelCompletionResult{}, providerFailureForStatus(status)
	}
	var decoded completionWireResponse
	if err := json.Unmarshal(body, &decoded); err != nil || len(decoded.Choices) == 0 ||
		!validProviderReceipt(decoded.Model, decoded.Usage) {
		return ports.ModelCompletionResult{}, ports.ProviderFailure{
			Capability: "model", Reason: ports.ProviderFailureInvalidResponse,
		}
	}
	return ports.ModelCompletionResult{
		Content:      strings.TrimSpace(decoded.Choices[0].Message.Content),
		FinishReason: strings.TrimSpace(decoded.Choices[0].FinishReason),
		Usage:        c.toUsage(*decoded.Usage, time.Since(started)),
		ToolCalls:    toApplicationToolCalls(decoded.Choices[0].Message.ToolCalls),
		ModelID:      strings.TrimSpace(decoded.Model),
		TierServed:   tierServed,
	}, nil
}

func (c *Client) Stream(
	ctx context.Context,
	request ports.ModelCompletionRequest,
	emit func(ports.ModelTextDelta) error,
) (ports.ModelCompletionResult, error) {
	started := time.Now()
	model, tierServed, ok := c.modelFor(request.Tier)
	if !ok {
		return ports.ModelCompletionResult{}, ports.ProviderFailure{
			Capability: "model", Reason: ports.ProviderFailureUnavailable,
		}
	}
	payload, err := json.Marshal(c.toWireRequest(request, model))
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
		return ports.ModelCompletionResult{}, providerFailureForStatus(status)
	}
	var answer strings.Builder
	var usage *usageWire
	modelID := ""
	finishReason := ""
	toolCalls := newToolCallAccumulator()
	done := false
	scanner := bufio.NewScanner(response.Body)
	scanner.Buffer(make([]byte, 64*1024), 2*1024*1024)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if !strings.HasPrefix(line, "data:") {
			continue
		}
		data := strings.TrimSpace(strings.TrimPrefix(line, "data:"))
		if data == "" {
			continue
		}
		if data == "[DONE]" {
			done = true
			break
		}
		var chunk completionWireResponse
		if err := json.Unmarshal([]byte(data), &chunk); err != nil {
			return ports.ModelCompletionResult{}, ports.ProviderFailure{
				Capability: "model", Reason: ports.ProviderFailureInvalidResponse,
			}
		}
		if hasProviderErrorEnvelope(chunk.Error) {
			return ports.ModelCompletionResult{}, ports.ProviderFailure{
				Capability: "model", Reason: ports.ProviderFailureInvalidResponse,
			}
		}
		chunkModelID := strings.TrimSpace(chunk.Model)
		if chunkModelID != "" {
			if modelID != "" && modelID != chunkModelID {
				return ports.ModelCompletionResult{}, ports.ProviderFailure{
					Capability: "model", Reason: ports.ProviderFailureInvalidResponse,
				}
			}
			modelID = chunkModelID
		}
		if chunk.Usage != nil {
			copied := *chunk.Usage
			usage = &copied
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
	if !done {
		return ports.ModelCompletionResult{}, ports.ProviderFailure{
			Capability: "model", Reason: ports.ProviderFailureInvalidResponse,
		}
	}
	content := strings.TrimSpace(answer.String())
	collected := toolCalls.collect()
	if (content == "" && len(collected) == 0) ||
		!validProviderReceipt(modelID, usage) {
		return ports.ModelCompletionResult{}, ports.ProviderFailure{
			Capability: "model", Reason: ports.ProviderFailureInvalidResponse,
		}
	}
	return ports.ModelCompletionResult{
		Content:      content,
		FinishReason: finishReason,
		Usage:        c.toUsage(*usage, time.Since(started)),
		ToolCalls:    collected,
		ModelID:      modelID,
		TierServed:   tierServed,
	}, nil
}

func hasProviderErrorEnvelope(raw json.RawMessage) bool {
	normalized := bytes.TrimSpace(raw)
	return len(normalized) > 0 && !bytes.Equal(normalized, []byte("null"))
}

func (c *Client) toWireRequest(
	request ports.ModelCompletionRequest,
	model string,
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
		Model:    model,
		Messages: messages,
		Stream:   request.Stream,
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

func validProviderReceipt(modelID string, usage *usageWire) bool {
	if strings.TrimSpace(modelID) == "" || usage == nil {
		return false
	}
	if usage.PromptTokens < 0 || usage.CompletionTokens < 0 || usage.TotalTokens <= 0 {
		return false
	}
	return usage.TotalTokens >= usage.PromptTokens+usage.CompletionTokens
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
	// TierDegradingModelProvider owns the only retry boundary. Replaying the same
	// provider request here has no idempotency receipt and can create an
	// unaccounted second completion after a response-loss or 5xx boundary.
	response, err := c.http.Do(request)
	if err != nil {
		return nil, 0, providerFailureForTransport(err)
	}
	return response, response.StatusCode, nil
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

func providerFailureForStatus(status int) ports.ProviderFailure {
	reason := ports.ProviderFailureInvalidResponse
	switch {
	case status == http.StatusRequestTimeout:
		reason = ports.ProviderFailureTimeout
	case status == http.StatusTooManyRequests || status >= http.StatusInternalServerError:
		reason = ports.ProviderFailureUnavailable
	}
	return ports.ProviderFailure{Capability: "model", Reason: reason}
}
