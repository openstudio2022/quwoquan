package application

import (
	"context"
	"fmt"
	"strings"
	"time"
)

// ProviderFailure 是外部能力对应用层暴露的脱敏失败事实。vendor 返回体、凭据和
// endpoint 不得进入此类型，调用方只能基于 capability/reason 决定恢复语义。
type ProviderFailure struct {
	Capability string
	Reason     ProviderFailureReason
}

type ProviderFailureReason string

const (
	ProviderFailureUnavailable     ProviderFailureReason = "unavailable"
	ProviderFailureTimeout         ProviderFailureReason = "timeout"
	ProviderFailureInvalidResponse ProviderFailureReason = "invalid_response"
)

func (f ProviderFailure) Error() string {
	return fmt.Sprintf(
		"assistant provider capability=%s reason=%s",
		strings.TrimSpace(f.Capability),
		f.Reason,
	)
}

type ExternalReference struct {
	Title     string
	URL       string
	Source    string
	Snippet   string
	Published string
	Rank      int
}

type ExternalSearchRequest struct {
	Query              string
	Queries            []string
	SkillID            string
	Location           string
	LocationSearchName string
	Symbols            []string
}

type ExternalSearchResult struct {
	Summary    string
	References []ExternalReference
}

// PublicSearchProvider 只负责公共网页检索；不包含天气和金融的专属数据语义。
type PublicSearchProvider interface {
	Search(context.Context, ExternalSearchRequest) (ExternalSearchResult, error)
}

// WeatherProvider 只暴露规范化的天气结果，地理编码、备用上游、HTTP 和解析都由
// infrastructure adapter 封装。
type WeatherProvider interface {
	Lookup(context.Context, ExternalSearchRequest) (ExternalSearchResult, error)
}

// FinanceProvider 只暴露规范化的行情摘要，代码校验和第三方 DTO 解析不穿透到
// application。
type FinanceProvider interface {
	Lookup(context.Context, ExternalSearchRequest) (ExternalSearchResult, error)
}

type ModelStage string

const (
	ModelStageSkillSelection     ModelStage = "skill_selection"
	ModelStageReasoning          ModelStage = "reasoning"
	ModelStageEvidenceProcessing ModelStage = "evidence_processing"
	ModelStageFinal              ModelStage = "final"
)

type ModelMessage struct {
	Role    string
	Content string
}

// ModelCompletionRequest 是模型 adapter 的强类型入站契约；消息和结构化输出要求
// 由 application 决定，模型名、endpoint、鉴权和 wire DTO 由 infrastructure 决定。
type ModelCompletionRequest struct {
	Stage            ModelStage
	Messages         []ModelMessage
	StructuredOutput bool
	Stream           bool
}

type ModelUsage struct {
	PromptTokens     int
	CompletionTokens int
	TotalTokens      int
	Latency          time.Duration
}

type ModelCompletionResult struct {
	Content      string
	FinishReason string
	Usage        ModelUsage
}

// ModelCompletionProvider 是唯一允许 application 调用的模型外部能力端口。
// 它没有 vendor DTO、HTTP header、密钥或动态 map。
type ModelCompletionProvider interface {
	Complete(context.Context, ModelCompletionRequest) (ModelCompletionResult, error)
	Stream(
		context.Context,
		ModelCompletionRequest,
		func(ModelTextDelta) error,
	) (ModelCompletionResult, error)
}
