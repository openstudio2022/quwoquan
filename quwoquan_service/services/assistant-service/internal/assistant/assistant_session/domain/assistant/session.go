package assistant

import (
	"strings"
	"time"

	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
)

type AssistantSession struct {
	SessionID             string                          `json:"sessionId" bson:"_id"`
	UserID                string                          `json:"userId" bson:"userId"`
	State                 string                          `json:"state" bson:"state"`
	ActiveTurnID          string                          `json:"activeTurnId,omitempty" bson:"activeTurnId,omitempty"`
	LastTurnID            string                          `json:"lastTurnId,omitempty" bson:"lastTurnId,omitempty"`
	Summary               string                          `json:"summary,omitempty" bson:"summary,omitempty"`
	SummarySourceSequence int64                           `json:"summarySourceSequence" bson:"summarySourceSequence"`
	SummaryVersion        int64                           `json:"summaryVersion" bson:"summaryVersion"`
	CompletionSequence    int64                           `json:"-" bson:"completionSequence"`
	ContextSummary        *AssistantSessionContextSummary `json:"-" bson:"contextSummary,omitempty"`
	ClientRequestID       string                          `json:"clientRequestId,omitempty" bson:"clientRequestId,omitempty"`
	CreatedAt             time.Time                       `json:"createdAt" bson:"createdAt"`
	UpdatedAt             time.Time                       `json:"updatedAt" bson:"updatedAt"`
}

type CreateSessionInput struct {
	Summary         string `json:"summary"`
	ClientRequestID string `json:"clientRequestId"`
}

type AssistantTurnInput struct {
	Text string `json:"text" bson:"text"`
}

type AssistantTurnTrigger struct {
	Type      string                    `json:"type" bson:"type"`
	MessageID string                    `json:"-" bson:"messageId,omitempty"`
	Envelope  *AssistantTriggerEnvelope `json:"-" bson:"envelope,omitempty"`
}

// AssistantTriggerEnvelope is the persisted causal input for both proactive
// and reactive runs. It is trusted service state, never writable through the
// public CreateTurn JSON body.
type AssistantTriggerEnvelope struct {
	Kind              string    `json:"kind" bson:"kind"`
	TriggerID         string    `json:"triggerId" bson:"triggerId"`
	OccurredAt        time.Time `json:"occurredAt" bson:"occurredAt"`
	SubscriptionRef   string    `json:"subscriptionRef,omitempty" bson:"subscriptionRef,omitempty"`
	SignalRefs        []string  `json:"signalRefs,omitempty" bson:"signalRefs,omitempty"`
	Reason            string    `json:"reason,omitempty" bson:"reason,omitempty"`
	DedupeKey         string    `json:"dedupeKey" bson:"dedupeKey"`
	DeliveryPolicyRef string    `json:"deliveryPolicyRef,omitempty" bson:"deliveryPolicyRef,omitempty"`
}

// AssistantRunRequestContext captures trusted transport metadata at the
// ingress boundary. It deliberately never accepts JSON input: user/page/session
// identity comes from authenticated request headers, not a mutable command body.
// The persisted copy lets a resumed run retain its causal audit context without
// expanding the public AssistantTurn response contract.
type AssistantRunRequestContext struct {
	ClientSessionID string `json:"-" bson:"clientSessionId,omitempty"`
	PageID          string `json:"-" bson:"pageId,omitempty"`
	SurfaceKind     string `json:"-" bson:"surfaceKind,omitempty"`
	SurfaceID       string `json:"-" bson:"surfaceId,omitempty"`
	RouteID         string `json:"-" bson:"routeId,omitempty"`
	OperationID     string `json:"-" bson:"operationId,omitempty"`
	TraceID         string `json:"-" bson:"traceId,omitempty"`
	PersonaID       string `json:"-" bson:"personaId"`
}

func (c AssistantRunRequestContext) Normalized() AssistantRunRequestContext {
	return AssistantRunRequestContext{
		ClientSessionID: strings.TrimSpace(c.ClientSessionID),
		PageID:          strings.TrimSpace(c.PageID),
		SurfaceKind:     strings.TrimSpace(c.SurfaceKind),
		SurfaceID:       strings.TrimSpace(c.SurfaceID),
		RouteID:         strings.TrimSpace(c.RouteID),
		OperationID:     strings.TrimSpace(c.OperationID),
		TraceID:         strings.TrimSpace(c.TraceID),
		PersonaID:       strings.TrimSpace(c.PersonaID),
	}
}

type AssistantTurnStreamState struct {
	LastSeq     uint64 `json:"lastSeq" bson:"lastSeq"`
	Completed   bool   `json:"completed" bson:"completed"`
	ResumeToken string `json:"resumeToken" bson:"resumeToken"`
}

type AssistantSessionContextTurn struct {
	Role     string `json:"role"`
	Text     string `json:"text"`
	SkillID  string `json:"skillId,omitempty"`
	DomainID string `json:"domainId,omitempty"`
}

type AssistantSessionContextSummary struct {
	SummaryID      string            `json:"summaryId" bson:"summaryId"`
	Text           string            `json:"text" bson:"text"`
	FromTurnID     string            `json:"fromTurnId" bson:"fromTurnId"`
	ToTurnID       string            `json:"toTurnId" bson:"toTurnId"`
	TurnCount      int               `json:"turnCount" bson:"turnCount"`
	CurrentGoal    string            `json:"currentGoal,omitempty" bson:"currentGoal,omitempty"`
	ConfirmedFacts []string          `json:"confirmedFacts,omitempty" bson:"confirmedFacts,omitempty"`
	PendingItems   []string          `json:"pendingItems,omitempty" bson:"pendingItems,omitempty"`
	ConfirmedSlots map[string]string `json:"confirmedSlots,omitempty" bson:"confirmedSlots,omitempty"`
}

// AssistantIntersectionEvidenceRef 是客户端可以提交的最小交集引用。它不包含
// 可被篡改的标题、结论、标签或 URL；application 必须以当前 actor 回查后才使用。
type AssistantIntersectionEvidenceRef struct {
	IntersectionID string `json:"intersectionId"`
	EvidenceID     string `json:"evidenceId"`
	SourceRef      string `json:"sourceRef"`
	ObjectTypeRef  string `json:"objectTypeRef"`
	ObjectID       string `json:"objectId"`
}

// AssistantPageObjectRef 是页面上下文允许进入服务的最小对象引用。标题、摘要、
// URL 与标签均不可信，不进入领域模型。
type AssistantPageObjectRef struct {
	ObjectTypeRef string `json:"objectTypeRef" bson:"objectTypeRef"`
	ObjectID      string `json:"objectId" bson:"objectId"`
}

// AssistantPageUserAction 是页面上下文允许进入 prompt 的结构化动作标识。
type AssistantPageUserAction struct {
	Action        string     `json:"action" bson:"action"`
	ObjectTypeRef string     `json:"objectTypeRef,omitempty" bson:"objectTypeRef,omitempty"`
	ObjectID      string     `json:"objectId,omitempty" bson:"objectId,omitempty"`
	OccurredAt    *time.Time `json:"occurredAt,omitempty" bson:"occurredAt,omitempty"`
}

type AssistantContextConsent struct {
	CanReadCurrentPage bool `json:"canReadCurrentPage" bson:"canReadCurrentPage"`
}

// AssistantContextSnapshot 是 AssistantRun 与 ReportPageContext 接收的受限上下文。
// application 只保留当前页定位、动作与最小交集引用；客户端展示文本不会进入领域模型。
type AssistantContextSnapshot struct {
	CapturedAt               time.Time                          `json:"capturedAt,omitempty" bson:"capturedAt,omitempty"`
	PageType                 string                             `json:"pageType,omitempty" bson:"pageType,omitempty"`
	PageObjects              []AssistantPageObjectRef           `json:"pageObjects,omitempty" bson:"pageObjects,omitempty"`
	UserActions              []AssistantPageUserAction          `json:"userActions,omitempty" bson:"userActions,omitempty"`
	ConsentMatrix            *AssistantContextConsent           `json:"consentMatrix,omitempty" bson:"consentMatrix,omitempty"`
	IntersectionEvidenceRefs []AssistantIntersectionEvidenceRef `json:"intersectionEvidenceRefs,omitempty"`
}

// AuthorizedIntersectionEvidence 是 content 的公开 Reader 以当前 actor 重新验证后
// 返回的事实。它是模型 prompt、evidence ledger 与 citation 的唯一交集事实来源。
type AuthorizedIntersectionEvidence struct {
	IntersectionID string    `json:"intersectionId" bson:"intersectionId"`
	EvidenceID     string    `json:"evidenceId" bson:"evidenceId"`
	SourceRef      string    `json:"sourceRef" bson:"sourceRef"`
	ObjectTypeRef  string    `json:"objectTypeRef" bson:"objectTypeRef"`
	ObjectID       string    `json:"objectId" bson:"objectId"`
	PrimaryText    string    `json:"primaryText" bson:"primaryText"`
	Dimension      string    `json:"dimension,omitempty" bson:"dimension,omitempty"`
	VerifiedAt     time.Time `json:"verifiedAt" bson:"verifiedAt"`
}

// AssistantRunVisibleReference is the only citation shape retained in a
// terminal Run snapshot. Destination validation happens before projection.
type AssistantRunVisibleReference struct {
	Title       string              `json:"title" bson:"title,omitempty"`
	Destination CitationDestination `json:"destination" bson:"destination"`
	Source      string              `json:"source" bson:"source,omitempty"`
	Snippet     string              `json:"snippet" bson:"snippet,omitempty"`
}

// AssistantRunVisibleProcess deliberately excludes model reasoning, retrieval
// queries, tool input and provider diagnostics.
type AssistantRunVisibleProcess struct {
	ProcessID string `json:"processId" bson:"processId"`
	Scope     string `json:"scope" bson:"scope"`
	// Stage 取值域是 PlannerPhaseId；ActionCode 取值域是 PlannerActionCode。
	Stage                  string                         `json:"stage" bson:"stage"`
	ActionCode             string                         `json:"actionCode" bson:"actionCode,omitempty"`
	Status                 string                         `json:"status" bson:"status"`
	Order                  int                            `json:"order" bson:"order"`
	Summary                string                         `json:"summary" bson:"summary,omitempty"`
	SkillID                string                         `json:"skillId" bson:"skillId,omitempty"`
	DomainID               string                         `json:"domainId" bson:"domainId,omitempty"`
	SearchedDocumentCount  int                            `json:"searchedDocumentCount" bson:"searchedDocumentCount"`
	ProcessedDocumentCount int                            `json:"processedDocumentCount" bson:"processedDocumentCount"`
	AcceptedDocumentCount  int                            `json:"acceptedDocumentCount" bson:"acceptedDocumentCount"`
	AcceptedReferences     []AssistantRunVisibleReference `json:"acceptedReferences" bson:"acceptedReferences"`
}

// AssistantRunTerminalFailure is a public-safe projection. Internal failure
// location, cause, context and provider text never enter the terminal snapshot.
type AssistantRunTerminalFailure struct {
	Code   string `json:"code" bson:"code"`
	Origin string `json:"origin" bson:"origin"`
	Kind   string `json:"kind" bson:"kind"`
	Nature string `json:"nature" bson:"nature"`
}

type AssistantSelectedPolicyRef struct {
	PolicyID      string `json:"policyId" bson:"policyId"`
	ReleaseDigest string `json:"releaseDigest" bson:"releaseDigest"`
	Cohort        string `json:"cohort" bson:"cohort"`
}

type AssistantFrozenPolicyTemplate struct {
	TemplateID      string   `json:"-" bson:"templateId"`
	SkillID         string   `json:"-" bson:"skillId"`
	DomainID        string   `json:"-" bson:"domainId"`
	PromptPolicy    string   `json:"-" bson:"promptPolicy"`
	AllowedTools    []string `json:"-" bson:"allowedTools"`
	SearchIntensity string   `json:"-" bson:"searchIntensity"`
}

type AssistantFrozenLearningContextPolicy struct {
	Enabled                  bool     `json:"-" bson:"enabled"`
	AllowedSignals           []string `json:"-" bson:"allowedSignals"`
	AllowedMetricIDs         []string `json:"-" bson:"allowedMetricIds"`
	AllowedReasonCodes       []string `json:"-" bson:"allowedReasonCodes"`
	MinimumFeedbackSamples   int      `json:"-" bson:"minimumFeedbackSamples"`
	WindowDays               int      `json:"-" bson:"windowDays"`
	SnapshotTrainingEligible bool     `json:"-" bson:"snapshotTrainingEligible"`
}

type AssistantFeedbackMetricSummary struct {
	MetricID    string  `json:"-" bson:"metricId"`
	SampleCount int64   `json:"-" bson:"sampleCount"`
	Average     float64 `json:"-" bson:"average"`
	Latest      float64 `json:"-" bson:"latest"`
}

type AssistantFeedbackReasonSummary struct {
	ReasonCode string `json:"-" bson:"reasonCode"`
	Count      int64  `json:"-" bson:"count"`
}

type AssistantFeedbackContextSnapshot struct {
	Decision                 string                           `json:"-" bson:"decision"`
	ConsentID                string                           `json:"-" bson:"consentId,omitempty"`
	ConsentGrantedAt         time.Time                        `json:"-" bson:"consentGrantedAt,omitempty"`
	DefinitionDigest         string                           `json:"-" bson:"definitionDigest,omitempty"`
	SourceWatermarkSequence  int64                            `json:"-" bson:"sourceWatermarkSequence,omitempty"`
	WindowDays               int                              `json:"-" bson:"windowDays,omitempty"`
	FeedbackSampleCount      int64                            `json:"-" bson:"feedbackSampleCount,omitempty"`
	PositiveFeedbackCount    int64                            `json:"-" bson:"positiveFeedbackCount,omitempty"`
	NegativeFeedbackCount    int64                            `json:"-" bson:"negativeFeedbackCount,omitempty"`
	TextFeedbackCount        int64                            `json:"-" bson:"textFeedbackCount,omitempty"`
	Metrics                  []AssistantFeedbackMetricSummary `json:"-" bson:"metrics,omitempty"`
	Reasons                  []AssistantFeedbackReasonSummary `json:"-" bson:"reasons,omitempty"`
	SnapshotTrainingEligible bool                             `json:"-" bson:"snapshotTrainingEligible"`
}

type AssistantFrozenPolicySelection struct {
	PolicyID              string                               `json:"-" bson:"policyId"`
	ReleaseDigest         string                               `json:"-" bson:"releaseDigest"`
	Cohort                string                               `json:"-" bson:"cohort"`
	RolloutRevision       int                                  `json:"-" bson:"rolloutRevision"`
	RuleID                string                               `json:"-" bson:"ruleId"`
	Template              AssistantFrozenPolicyTemplate        `json:"-" bson:"template"`
	LearningContextPolicy AssistantFrozenLearningContextPolicy `json:"-" bson:"learningContextPolicy"`
}

func (selection AssistantFrozenPolicySelection) PublicRef() *AssistantSelectedPolicyRef {
	if strings.TrimSpace(selection.PolicyID) == "" ||
		strings.TrimSpace(selection.ReleaseDigest) == "" ||
		strings.TrimSpace(selection.Cohort) == "" {
		return nil
	}
	return &AssistantSelectedPolicyRef{
		PolicyID:      strings.TrimSpace(selection.PolicyID),
		ReleaseDigest: strings.TrimSpace(selection.ReleaseDigest),
		Cohort:        strings.TrimSpace(selection.Cohort),
	}
}

// AssistantRunTerminalSnapshot is the non-TTL source for GetRun, terminal SSE
// replay and session-history recovery.
type AssistantRunTerminalSnapshot struct {
	AnswerText        string                       `json:"answerText" bson:"answerText"`
	Processes         []AssistantRunVisibleProcess `json:"processes" bson:"processes"`
	Failure           *AssistantRunTerminalFailure `json:"failure,omitempty" bson:"failure,omitempty"`
	SelectedPolicyRef *AssistantSelectedPolicyRef  `json:"selectedPolicyRef,omitempty" bson:"selectedPolicyRef,omitempty"`
}

type AssistantTurn struct {
	TurnID                  string                           `json:"turnId" bson:"_id"`
	ExecutionRunID          string                           `json:"-" bson:"-"`
	SessionID               string                           `json:"sessionId" bson:"sessionId"`
	UserID                  string                           `json:"userId" bson:"userId"`
	TurnType                string                           `json:"turnType" bson:"turnType"`
	Status                  string                           `json:"status" bson:"status"`
	CompletionSequence      int64                            `json:"-" bson:"completionSequence,omitempty"`
	SkillID                 string                           `json:"skillId,omitempty" bson:"skillId,omitempty"`
	DomainID                string                           `json:"domainId,omitempty" bson:"domainId,omitempty"`
	Input                   AssistantTurnInput               `json:"input" bson:"input"`
	ContextTurns            []AssistantSessionContextTurn    `json:"contextTurns,omitempty" bson:"-"`
	ContextSummary          *AssistantSessionContextSummary  `json:"-" bson:"-"`
	PageContext             *AssistantContextSnapshot        `json:"pageContext,omitempty" bson:"pageContext,omitempty"`
	IntersectionEvidence    []AuthorizedIntersectionEvidence `json:"intersectionEvidence,omitempty" bson:"intersectionEvidence,omitempty"`
	SessionPreferenceFacts  []preferencemodel.Snapshot       `json:"sessionPreferenceFacts,omitempty" bson:"sessionPreferenceFacts,omitempty"`
	LongTermPreferenceFacts []preferencemodel.Snapshot       `json:"longTermPreferenceFacts,omitempty" bson:"longTermPreferenceFacts,omitempty"`
	Trigger                 AssistantTurnTrigger             `json:"trigger" bson:"trigger"`
	StreamState             AssistantTurnStreamState         `json:"streamState" bson:"streamState"`
	TerminalSnapshot        *AssistantRunTerminalSnapshot    `json:"terminalSnapshot,omitempty" bson:"terminalSnapshot,omitempty"`
	ClientRequestID         string                           `json:"clientRequestId,omitempty" bson:"clientRequestId,omitempty"`
	RequestContext          AssistantRunRequestContext       `json:"-" bson:"requestContext,omitempty"`
	FrozenPolicySelection   AssistantFrozenPolicySelection   `json:"-" bson:"frozenPolicySelection"`
	FeedbackContextSnapshot AssistantFeedbackContextSnapshot `json:"-" bson:"feedbackContextSnapshot"`
	TraceID                 string                           `json:"traceId" bson:"traceId"`
	CreatedAt               time.Time                        `json:"createdAt" bson:"createdAt"`
	CompletedAt             *time.Time                       `json:"completedAt,omitempty" bson:"completedAt,omitempty"`
}

type CreateTurnInput struct {
	TurnType        string                     `json:"turnType"`
	SkillID         string                     `json:"skillId"`
	DomainID        string                     `json:"domainId"`
	Input           AssistantTurnInput         `json:"input"`
	Trigger         AssistantTurnTrigger       `json:"trigger"`
	ClientRequestID string                     `json:"clientRequestId"`
	ContextSnapshot AssistantContextSnapshot   `json:"contextSnapshot"`
	RequestContext  AssistantRunRequestContext `json:"-"`
}

// AssistantSessionListView 是 ListAssistantSessions 的响应切片
// （契约：assistant_session/fields.yaml AssistantSessionListView）。
type AssistantSessionListView struct {
	Items      []AssistantSession `json:"items"`
	NextCursor string             `json:"nextCursor,omitempty"`
}
