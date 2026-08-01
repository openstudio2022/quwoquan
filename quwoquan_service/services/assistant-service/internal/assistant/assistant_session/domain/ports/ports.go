package ports

import (
	"context"
	"fmt"
	"strings"
	"time"

	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

type SkillSubscriptionStore interface {
	CreateSkillSubscription(context.Context, assistant.SkillSubscription) (assistant.SkillSubscription, error)
	UpsertSkillSubscription(context.Context, assistant.SkillSubscription) (assistant.SkillSubscription, error)
	GetSkillSubscription(context.Context, string, string) (assistant.SkillSubscription, error)
	ListSkillSubscriptions(context.Context, string, string, int) ([]assistant.SkillSubscription, error)
	ListActiveSkillSubscriptionsForDelivery(context.Context, time.Time, int) ([]assistant.SkillSubscription, error)
	UpdateSkillSubscriptionStatus(
		context.Context,
		string,
		string,
		string,
		*time.Time,
		time.Time,
	) (assistant.SkillSubscription, error)
	BeginSkillSubscriptionDelivery(
		context.Context,
		string,
		string,
		string,
		time.Time,
	) (assistant.SkillSubscription, bool, error)
	CompleteSkillSubscriptionDelivery(
		context.Context,
		string,
		string,
		string,
		time.Time,
		time.Time,
	) (assistant.SkillSubscription, error)
	RecordSkillSubscriptionDeliveryFailure(
		context.Context,
		string,
		string,
		string,
		string,
		time.Time,
		time.Time,
	) (assistant.SkillSubscription, error)
	ClearPendingSkillSubscriptionDelivery(
		context.Context,
		string,
		string,
		string,
		time.Time,
		time.Time,
	) error
}

// SessionRunStore 是 AssistantSession 与 AssistantRun(Turn) 两个聚合的
// 对象专属持久化端口。业务状态一律持久化，禁止进程内 map 承载。
type SessionRunStore interface {
	InsertSession(
		context.Context,
		assistant.AssistantSession,
	) (assistant.AssistantSession, bool, error)
	GetSession(
		context.Context,
		string,
	) (assistant.AssistantSession, bool, error)
	UpdateSessionTurnPointer(
		context.Context,
		string,
		string,
		string,
		time.Time,
	) error
	CompareAndSwapSessionSummary(
		context.Context,
		string,
		int64,
		int64,
		int64,
		assistant.AssistantSessionContextSummary,
		time.Time,
	) (bool, error)
	InsertTurn(
		context.Context,
		assistant.AssistantTurn,
	) (assistant.AssistantTurn, bool, error)
	GetTurn(context.Context, string) (assistant.AssistantTurn, bool, error)
	GetTurnByClientRequest(
		context.Context,
		string,
		string,
		string,
	) (assistant.AssistantTurn, bool, error)
	CompleteTurn(
		context.Context,
		assistant.AssistantTurn,
	) (assistant.AssistantTurn, error)
	ListCompletedTurns(
		context.Context,
		string,
		string,
		int,
	) ([]assistant.AssistantTurn, error)
	ListCompletedTurnsAfterSequence(
		context.Context,
		string,
		string,
		int64,
		int,
	) ([]assistant.AssistantTurn, error)
	ListSessions(
		context.Context,
		string,
		int,
		string,
	) ([]assistant.AssistantSession, string, error)
}

type PreferenceSnapshotReader interface {
	ResolveActiveSnapshots(
		context.Context,
		string,
		string,
	) ([]preferencemodel.Snapshot, []preferencemodel.Snapshot, error)
}

type LearningProjectionReader interface {
	GetLearningProjection(
		context.Context,
		string,
	) (*learningmodel.LearningProjection, error)
	GetLearningProjectionForPersona(
		context.Context,
		string,
		string,
	) (*learningmodel.LearningProjection, error)
}

type ServiceScorecardFactCommand struct {
	EventID         string
	AssistantTurnID string
	DomainID        string
	MetricID        string
	MetricValue     float64
	MetricSource    string
	OccurredAt      time.Time
}

type LearningFactWriter interface {
	AppendServiceScorecard(context.Context, ServiceScorecardFactCommand) error
}

type LearningFactWriterFunc func(
	context.Context,
	ServiceScorecardFactCommand,
) error

func (writer LearningFactWriterFunc) AppendServiceScorecard(
	ctx context.Context,
	command ServiceScorecardFactCommand,
) error {
	return writer(ctx, command)
}

type FrozenPolicyResolver interface {
	ResolveFrozenPolicy(
		context.Context,
		string,
		string,
		string,
		string,
	) (assistant.AssistantFrozenPolicySelection, error)
}

type FrozenPolicyResolverFunc func(
	context.Context,
	string,
	string,
	string,
	string,
) (assistant.AssistantFrozenPolicySelection, error)

func (resolve FrozenPolicyResolverFunc) ResolveFrozenPolicy(
	ctx context.Context,
	policyID string,
	personaID string,
	skillID string,
	domainID string,
) (assistant.AssistantFrozenPolicySelection, error) {
	return resolve(ctx, policyID, personaID, skillID, domainID)
}

// PolicySkillCandidateResolver 给出策略在人群下可服务的技能集合。
type PolicySkillCandidateResolver interface {
	ResolvePolicySkillCandidates(
		context.Context,
		string,
		string,
	) ([]string, error)
}

type PolicySkillCandidateResolverFunc func(
	context.Context,
	string,
	string,
) ([]string, error)

func (resolve PolicySkillCandidateResolverFunc) ResolvePolicySkillCandidates(
	ctx context.Context,
	policyID string,
	personaID string,
) ([]string, error) {
	return resolve(ctx, policyID, personaID)
}

// IntersectionEvidenceReader 必须以调用 actor 授权读取当前事实，不能信任展示内容。
type IntersectionEvidenceReader interface {
	ResolveAuthorizedIntersectionEvidence(
		context.Context,
		string,
		[]assistant.AssistantIntersectionEvidenceRef,
	) ([]assistant.AuthorizedIntersectionEvidence, error)
}

type IntersectionReminderReason struct {
	ReasonID    string
	UserID      string
	TargetID    string
	TargetName  string
	Dimension   string
	PrimaryText string
	IsFact      bool
	CreatedAt   time.Time
}

type IntersectionInboxReader interface {
	ListNewIntersectionReasons(
		context.Context,
		string,
		time.Time,
		int,
	) ([]IntersectionReminderReason, error)
}

type CreationSuggestGrounding interface {
	ResolveTagRefs(context.Context, []string) ([]string, error)
	ResolveHomepages(
		context.Context,
		[]string,
	) ([]assistant.AssistantSuggestedHomepageView, error)
}

type ChatGroundingMessage struct {
	MessageID  string
	Seq        int64
	SenderID   string
	SenderName string
	Type       string
	Content    string
	Mentions   []string
	Timestamp  time.Time
	ObjectRef  *ChatGroundingObjectRef
}

type ChatGroundingObjectRef struct {
	ObjectTypeRef string
	ObjectID      string
	RouteID       string
}

type ChatGroundingSendMessageRequest struct {
	ChatConversationID string
	CreatorPersonaID   string
	AssistantSkillID   string
	Type               string
	Content            string
	ClientMsgID        string
}

type ChatGroundingClient interface {
	ResolveAssistantDeliveryMembership(
		context.Context,
		string,
		string,
		string,
		string,
	) (bool, error)
	ListMessages(
		context.Context,
		string,
		string,
		string,
		int64,
		int,
	) ([]ChatGroundingMessage, error)
	SendMessage(context.Context, ChatGroundingSendMessageRequest) error
}

type AssistantDeliveryPolicy struct {
	UserID           string
	AssistantEnabled bool
	QuietHoursStart  *time.Duration
	QuietHoursEnd    *time.Duration
	Version          int64
}

type AssistantDeliveryPolicyReader interface {
	ResolveAssistantDeliveryPolicy(
		context.Context,
		string,
	) (AssistantDeliveryPolicy, error)
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

type NotificationAppMessageCommand struct {
	IdempotencyKey string
	UserID         string
	MessageType    string
	Source         string
	SourceID       string
	Destination    NotificationAppMessageDestination
	Title          string
	Summary        string
	Target         NotificationAppMessageTarget
	Provenance     NotificationAppMessageProvenance
}

type NotificationAppMessageDestination struct {
	Type string
	ID   string
}

type NotificationAppMessageTarget struct {
	TargetType string
	TargetID   string
	RouteID    string
	RoutePath  string
	Dimension  string
}

type NotificationAppMessageProvenance struct {
	Personalized    bool
	InterestTags    []string
	MatchedSegments []string
	LifecycleStage  string
}

type NotificationAppMessageReceipt struct {
	MessageID string
}

type NotificationAppMessageCommandWriter interface {
	CreateAppMessage(
		context.Context,
		NotificationAppMessageCommand,
	) (NotificationAppMessageReceipt, error)
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
