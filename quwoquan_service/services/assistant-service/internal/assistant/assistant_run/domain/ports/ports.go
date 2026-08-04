package ports

import (
	"context"
	"fmt"
	"strings"
	"time"

	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

// IntersectionEvidenceReader 通过 content 的公开 Reader 以当前 persona
// 回查客户端提交的最小交集引用，禁止信任客户端展示事实。
type IntersectionEvidenceReader interface {
	ResolveAuthorizedIntersectionEvidence(
		context.Context,
		string,
		[]assistant.AssistantIntersectionEvidenceRef,
	) ([]assistant.AuthorizedIntersectionEvidence, error)
}

type ProactiveInterest struct {
	TagRef    string
	Dimension string
	Score     float64
	Level     int
}

type ProactiveInterestProfile struct {
	TopInterests   []ProactiveInterest
	DimensionTops  map[string][]string
	LifecycleStage string
	FreshnessDays  int
	Segments       []string
}

type ProactiveInterestReader interface {
	GetInterestProfile(
		context.Context,
		string,
	) (*ProactiveInterestProfile, error)
}

type PromptAssetResolver interface {
	ResolvePromptAssets(context.Context, []string) (string, error)
}

type PromptAssetResolverFunc func(context.Context, []string) (string, error)

func (resolve PromptAssetResolverFunc) ResolvePromptAssets(
	ctx context.Context,
	assetIDs []string,
) (string, error) {
	return resolve(ctx, assetIDs)
}

// ProviderFailure 是外部能力对应用层暴露的脱敏失败事实。
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

func (failure ProviderFailure) Error() string {
	return fmt.Sprintf(
		"assistant provider capability=%s reason=%s",
		strings.TrimSpace(failure.Capability),
		failure.Reason,
	)
}

func (failure ProviderFailure) RetryableToolFailure() bool {
	switch failure.Reason {
	case ProviderFailureUnavailable, ProviderFailureTimeout:
		return true
	default:
		return false
	}
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

type PublicSearchProvider interface {
	Search(context.Context, ExternalSearchRequest) (ExternalSearchResult, error)
}

type WeatherProvider interface {
	Lookup(context.Context, ExternalSearchRequest) (ExternalSearchResult, error)
}

type FinanceProvider interface {
	Lookup(context.Context, ExternalSearchRequest) (ExternalSearchResult, error)
}

type ModelStage string

const (
	ModelStageSkillSelection     ModelStage = "skill_selection"
	ModelStageOrchestration      ModelStage = "orchestration"
	ModelStageReasoning          ModelStage = "reasoning"
	ModelStageEvidenceProcessing ModelStage = "evidence_processing"
	ModelStageCompaction         ModelStage = "compaction"
	ModelStagePresentation       ModelStage = "presentation"
	ModelStageFinal              ModelStage = "final"
)

type ModelTier string

const (
	ModelTierFast      ModelTier = "fast"
	ModelTierBalanced  ModelTier = "balanced"
	ModelTierReasoning ModelTier = "reasoning"
)

type ModelMessage struct {
	Role       string
	Content    string
	ToolCallID string
}

type ModelToolChoice string

const (
	ModelToolChoiceNone     ModelToolChoice = "none"
	ModelToolChoiceAuto     ModelToolChoice = "auto"
	ModelToolChoiceRequired ModelToolChoice = "required"
)

type ModelToolDefinition struct {
	Name        string
	Description string
	Parameters  map[string]any
}

type ModelToolCall struct {
	ID        string
	Name      string
	Arguments string
}

type ModelCompletionRequest struct {
	Stage            ModelStage
	Tier             ModelTier
	Messages         []ModelMessage
	Tools            []ModelToolDefinition
	ToolChoice       ModelToolChoice
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
	ToolCalls    []ModelToolCall
	ModelID      string
	TierServed   ModelTier
}

type ModelTextDelta struct {
	Text string
}

type ModelCompletionProvider interface {
	Complete(
		context.Context,
		ModelCompletionRequest,
	) (ModelCompletionResult, error)
	Stream(
		context.Context,
		ModelCompletionRequest,
		func(ModelTextDelta) error,
	) (ModelCompletionResult, error)
}

type NativeToolCallingCapability interface {
	SupportsNativeToolCalling() bool
}

func SupportsNativeToolCalling(provider ModelCompletionProvider) bool {
	capable, ok := provider.(NativeToolCallingCapability)
	return ok && capable.SupportsNativeToolCalling()
}

// ParallelModelRequestsCapability is an explicit provider contract. AgentLoop
// must not infer safe concurrent subagent requests from a concrete client type.
type ParallelModelRequestsCapability interface {
	SupportsParallelModelRequests() bool
}

func SupportsParallelModelRequests(provider ModelCompletionProvider) bool {
	capable, ok := provider.(ParallelModelRequestsCapability)
	return ok && capable.SupportsParallelModelRequests()
}

// ReasoningTierCapability means the provider binding can serve the canonical
// reasoning tier. It intentionally says nothing about a vendor-specific model
// name or sampling parameter.
type ReasoningTierCapability interface {
	SupportsReasoningTier() bool
}

func SupportsReasoningTier(provider ModelCompletionProvider) bool {
	capable, ok := provider.(ReasoningTierCapability)
	return ok && capable.SupportsReasoningTier()
}
