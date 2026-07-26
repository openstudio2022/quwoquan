package assistant

import (
	"strings"
	"time"

	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference_fact/domain/model"
)

type AssistantConversation struct {
	ConversationID  string    `json:"conversationId" bson:"_id"`
	UserID          string    `json:"userId" bson:"userId"`
	State           string    `json:"state" bson:"state"`
	ActiveTurnID    string    `json:"activeTurnId,omitempty" bson:"activeTurnId,omitempty"`
	LastTurnID      string    `json:"lastTurnId,omitempty" bson:"lastTurnId,omitempty"`
	Summary         string    `json:"summary,omitempty" bson:"summary,omitempty"`
	ClientRequestID string    `json:"clientRequestId,omitempty" bson:"clientRequestId,omitempty"`
	CreatedAt       time.Time `json:"createdAt" bson:"createdAt"`
	UpdatedAt       time.Time `json:"updatedAt" bson:"updatedAt"`
}

type CreateConversationInput struct {
	Summary         string `json:"summary"`
	ClientRequestID string `json:"clientRequestId"`
}

type AssistantTurnInput struct {
	Text string `json:"text" bson:"text"`
}

type AssistantTurnTrigger struct {
	Type string `json:"type" bson:"type"`
}

// AssistantRunRequestContext captures trusted transport metadata at the
// ingress boundary. It deliberately never accepts JSON input: user/page/session
// identity comes from authenticated request headers, not a mutable command body.
// The persisted copy lets a resumed run retain its causal audit context without
// expanding the public AssistantTurn response contract.
type AssistantRunRequestContext struct {
	SessionID   string `json:"-" bson:"sessionId,omitempty"`
	PageID      string `json:"-" bson:"pageId,omitempty"`
	SurfaceID   string `json:"-" bson:"surfaceId,omitempty"`
	RouteID     string `json:"-" bson:"routeId,omitempty"`
	OperationID string `json:"-" bson:"operationId,omitempty"`
	TraceID     string `json:"-" bson:"traceId,omitempty"`
}

func (c AssistantRunRequestContext) Normalized() AssistantRunRequestContext {
	return AssistantRunRequestContext{
		SessionID:   strings.TrimSpace(c.SessionID),
		PageID:      strings.TrimSpace(c.PageID),
		SurfaceID:   strings.TrimSpace(c.SurfaceID),
		RouteID:     strings.TrimSpace(c.RouteID),
		OperationID: strings.TrimSpace(c.OperationID),
		TraceID:     strings.TrimSpace(c.TraceID),
	}
}

type AssistantTurnStreamState struct {
	LastSeq     uint64 `json:"lastSeq" bson:"lastSeq"`
	Completed   bool   `json:"completed" bson:"completed"`
	ResumeToken string `json:"resumeToken" bson:"resumeToken"`
}

type AssistantConversationContextTurn struct {
	Role     string `json:"role"`
	Text     string `json:"text"`
	SkillID  string `json:"skillId,omitempty"`
	DomainID string `json:"domainId,omitempty"`
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
	ProcessID              string                         `json:"processId" bson:"processId"`
	Scope                  string                         `json:"scope" bson:"scope"`
	Stage                  string                         `json:"stage" bson:"stage"`
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
	PolicyID string `json:"policyId" bson:"policyId"`
	Version  string `json:"version" bson:"version"`
	Cohort   string `json:"cohort" bson:"cohort"`
}

// AssistantRunTerminalSnapshot is the non-TTL source for GetRun, terminal SSE
// replay and conversation-history recovery.
type AssistantRunTerminalSnapshot struct {
	AnswerText        string                       `json:"answerText" bson:"answerText"`
	Processes         []AssistantRunVisibleProcess `json:"processes" bson:"processes"`
	Failure           *AssistantRunTerminalFailure `json:"failure,omitempty" bson:"failure,omitempty"`
	SelectedPolicyRef *AssistantSelectedPolicyRef  `json:"selectedPolicyRef,omitempty" bson:"selectedPolicyRef,omitempty"`
}

type AssistantTurn struct {
	TurnID                  string                             `json:"turnId" bson:"_id"`
	ConversationID          string                             `json:"conversationId" bson:"conversationId"`
	UserID                  string                             `json:"userId" bson:"userId"`
	TurnType                string                             `json:"turnType" bson:"turnType"`
	Status                  string                             `json:"status" bson:"status"`
	SkillID                 string                             `json:"skillId,omitempty" bson:"skillId,omitempty"`
	DomainID                string                             `json:"domainId,omitempty" bson:"domainId,omitempty"`
	Input                   AssistantTurnInput                 `json:"input" bson:"input"`
	ContextTurns            []AssistantConversationContextTurn `json:"contextTurns,omitempty" bson:"-"`
	PageContext             *AssistantContextSnapshot          `json:"pageContext,omitempty" bson:"pageContext,omitempty"`
	IntersectionEvidence    []AuthorizedIntersectionEvidence   `json:"intersectionEvidence,omitempty" bson:"intersectionEvidence,omitempty"`
	SessionPreferenceFacts  []preferencemodel.Snapshot         `json:"sessionPreferenceFacts,omitempty" bson:"sessionPreferenceFacts,omitempty"`
	LongTermPreferenceFacts []preferencemodel.Snapshot         `json:"longTermPreferenceFacts,omitempty" bson:"longTermPreferenceFacts,omitempty"`
	Trigger                 AssistantTurnTrigger               `json:"trigger" bson:"trigger"`
	StreamState             AssistantTurnStreamState           `json:"streamState" bson:"streamState"`
	TerminalSnapshot        *AssistantRunTerminalSnapshot      `json:"terminalSnapshot,omitempty" bson:"terminalSnapshot,omitempty"`
	ClientRequestID         string                             `json:"clientRequestId,omitempty" bson:"clientRequestId,omitempty"`
	RequestContext          AssistantRunRequestContext         `json:"-" bson:"requestContext,omitempty"`
	TraceID                 string                             `json:"traceId" bson:"traceId"`
	CreatedAt               time.Time                          `json:"createdAt" bson:"createdAt"`
	CompletedAt             *time.Time                         `json:"completedAt,omitempty" bson:"completedAt,omitempty"`
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

// AssistantConversationListView 是 ListAssistantConversations 的响应切片
// （契约：assistant_conversation/fields.yaml AssistantConversationListView）。
type AssistantConversationListView struct {
	Items      []AssistantConversation `json:"items"`
	NextCursor string                  `json:"nextCursor,omitempty"`
}

// AssistantTurnSummaryView 是会话轮次摘要（契约：assistant_run/fields.yaml
// AssistantTurnSummaryView）；transcript、过程与引用均由同一终态快照恢复。
type AssistantTurnSummaryView struct {
	TurnID           string                        `json:"turnId"`
	ConversationID   string                        `json:"conversationId"`
	Status           string                        `json:"status"`
	InputText        string                        `json:"inputText"`
	TerminalSnapshot *AssistantRunTerminalSnapshot `json:"terminalSnapshot,omitempty"`
	SkillID          string                        `json:"skillId,omitempty"`
	DomainID         string                        `json:"domainId,omitempty"`
	CreatedAt        string                        `json:"createdAt"`
	CompletedAt      string                        `json:"completedAt,omitempty"`
}

// AssistantTurnListView 是 ListConversationTurns 的响应切片
// （契约：assistant_run/fields.yaml AssistantTurnListView）。
type AssistantTurnListView struct {
	Items      []AssistantTurnSummaryView `json:"items"`
	NextCursor string                     `json:"nextCursor,omitempty"`
}
