package embedding

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"time"

	runtimeconfig "quwoquan_service/runtime/config"
	runtimegovernance "quwoquan_service/runtime/governance"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	embeddingapp "quwoquan_service/services/content-service/internal/content/post/application/embedding"
)

const (
	EmbeddingAPIKeyEnv    = "CONTENT_EMBEDDING_API_KEY"
	embeddingModelEnv     = "CONTENT_EMBEDDING_MODEL"
	defaultEmbeddingModel = "text-embedding-3-small"
	embeddingCapabilityID = "content.embedding.generation"
)

// OpenAICompatibleBinding 是受控运行时注入后的内容向量 Provider 绑定。
// endpoint、密钥和模型只在 infrastructure adapter 内解析，组合根不持有这些细节。
type OpenAICompatibleBinding struct {
	Endpoint string
	APIKey   string
	Model    string
	Timeout  time.Duration
}

// LoadOpenAICompatibleBinding 从编译期选定的 Binding 物化内容向量 Provider。
func LoadOpenAICompatibleBinding(
	appEnv string,
	configProvider runtimeconfig.RuntimeConfigProvider,
) (OpenAICompatibleBinding, error) {
	if configProvider == nil {
		return OpenAICompatibleBinding{}, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"embedding binding has no runtime config provider",
		)
	}
	descriptor, found := contentgenerated.ExternalProviderBindingFor(
		appEnv,
		embeddingCapabilityID,
	)
	if !found || descriptor.State != "enabled" || descriptor.AdapterID != OpenAICompatibleAdapterID {
		return OpenAICompatibleBinding{}, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"embedding binding is unavailable for the current environment",
		)
	}
	endpointKey := strings.TrimSpace(descriptor.EndpointEnvironmentKeys["endpoint"])
	if endpointKey == "" {
		return OpenAICompatibleBinding{}, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"embedding binding has no endpoint reference",
		)
	}
	endpoint, endpointOK := configProvider.GetString(endpointKey)
	apiKey, apiKeyOK := configProvider.GetString(EmbeddingAPIKeyEnv)
	if !endpointOK || !apiKeyOK {
		return OpenAICompatibleBinding{}, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"embedding binding material is unavailable",
		)
	}
	model, _ := configProvider.GetString(embeddingModelEnv)
	binding := OpenAICompatibleBinding{
		Endpoint: endpoint,
		APIKey:   apiKey,
		Model:    model,
		Timeout:  time.Duration(descriptor.TimeoutMilliseconds) * time.Millisecond,
	}
	if binding.Model == "" {
		binding.Model = defaultEmbeddingModel
	}
	if err := binding.validate(); err != nil {
		return OpenAICompatibleBinding{}, err
	}
	return binding, nil
}

func (b OpenAICompatibleBinding) validate() error {
	if b.Endpoint == "" {
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"embedding binding requires CONTENT_EMBEDDING_ENDPOINT",
		)
	}
	parsed, err := url.Parse(b.Endpoint)
	if err != nil || parsed.Scheme == "" || parsed.Host == "" || parsed.User != nil {
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"embedding binding has an invalid endpoint",
		)
	}
	if b.APIKey == "" {
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"embedding binding requires CONTENT_EMBEDDING_API_KEY",
		)
	}
	if b.Model == "" {
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"embedding binding requires a model",
		)
	}
	if b.Timeout <= 0 {
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"embedding binding requires a positive timeout",
		)
	}
	return nil
}

// ValidateOpenAICompatibleBinding 确认受控 Binding 完整，供启动前检查。
func ValidateOpenAICompatibleBinding(
	appEnv string,
	configProvider runtimeconfig.RuntimeConfigProvider,
) error {
	_, err := LoadOpenAICompatibleBinding(appEnv, configProvider)
	return err
}

type gateway struct {
	endpoint string
	apiKey   string
	model    string
	client   *http.Client
}

type GatewayOption func(*gateway)

// WithHTTPClient 仅供 infrastructure adapter 的传输装配与契约测试使用。
func WithHTTPClient(client *http.Client) GatewayOption {
	return func(gateway *gateway) {
		if client != nil {
			gateway.client = client
		}
	}
}

// NewOpenAICompatibleGateway 组装 content.embedding.EmbeddingGateway 的唯一远端实现。
func NewOpenAICompatibleGateway(
	binding OpenAICompatibleBinding,
	options ...GatewayOption,
) (embeddingapp.EmbeddingGateway, error) {
	if err := binding.validate(); err != nil {
		return nil, err
	}
	gateway := &gateway{
		endpoint: binding.Endpoint,
		apiKey:   binding.APIKey,
		model:    binding.Model,
		client: runtimegovernance.WrapClientWithCB(
			&http.Client{Timeout: binding.Timeout},
			runtimegovernance.NewCircuitBreaker(5, 15*time.Second, slog.Default()),
		),
	}
	for _, option := range options {
		option(gateway)
	}
	return gateway, nil
}

type openAIEmbeddingRequest struct {
	Model string   `json:"model"`
	Input []string `json:"input"`
}

type openAIEmbeddingResponse struct {
	Data []struct {
		Embedding []float64 `json:"embedding"`
		Index     int       `json:"index"`
	} `json:"data"`
}

func (g *gateway) Embed(ctx context.Context, text string) (embeddingapp.Vector, error) {
	vectors, err := g.EmbedBatch(ctx, []string{text})
	if err != nil {
		return nil, err
	}
	if len(vectors) != 1 || len(vectors[0]) == 0 {
		return nil, unavailable("embedding gateway returned an empty vector")
	}
	return vectors[0], nil
}

func (g *gateway) EmbedBatch(
	ctx context.Context,
	texts []string,
) ([]embeddingapp.Vector, error) {
	if len(texts) == 0 {
		return []embeddingapp.Vector{}, nil
	}
	payload, err := json.Marshal(openAIEmbeddingRequest{
		Model: g.model,
		Input: texts,
	})
	if err != nil {
		return nil, unavailable("embedding gateway request could not be encoded")
	}
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		g.endpoint,
		bytes.NewReader(payload),
	)
	if err != nil {
		return nil, unavailable("embedding gateway request could not be created")
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", "Bearer "+g.apiKey)

	response, err := g.client.Do(request)
	if err != nil {
		if errors.Is(err, context.DeadlineExceeded) || errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return nil, contentgenerated.AppErrorFromUpstreamTimeout(
				"embedding gateway request timed out",
			)
		}
		return nil, unavailable("embedding gateway request failed")
	}
	defer response.Body.Close()
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 1024))
		return nil, unavailable(fmt.Sprintf("embedding gateway returned HTTP %d", response.StatusCode))
	}

	var decoded openAIEmbeddingResponse
	if err := json.NewDecoder(io.LimitReader(response.Body, 1024*1024)).Decode(&decoded); err != nil {
		return nil, unavailable("embedding gateway response could not be decoded")
	}
	vectors := make([]embeddingapp.Vector, len(texts))
	for _, item := range decoded.Data {
		if item.Index < 0 || item.Index >= len(vectors) || len(item.Embedding) == 0 {
			return nil, unavailable("embedding gateway returned an invalid vector response")
		}
		vectors[item.Index] = embeddingapp.Vector(item.Embedding)
	}
	for _, vector := range vectors {
		if len(vector) == 0 {
			return nil, unavailable("embedding gateway response omitted a vector")
		}
	}
	return vectors, nil
}

func unavailable(debugMessage string) error {
	return contentgenerated.AppErrorFromRequiredDependencyUnavailable(debugMessage)
}
