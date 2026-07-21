package assistant

import (
	"time"

	rtfailures "quwoquan_service/runtime/failures"
	preferencemodel "quwoquan_service/services/assistant-service/internal/domain/assistant/preference_fact/model"
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

// AssistantContextSnapshot 是 StartAssistantRun 接收的受限上下文。未声明的 JSON
// 字段不会进入领域模型，交集引用也只能在 application 完成授权回查后进入 turn。
type AssistantContextSnapshot struct {
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
	IntersectionEvidence    []AuthorizedIntersectionEvidence   `json:"intersectionEvidence,omitempty" bson:"intersectionEvidence,omitempty"`
	SessionPreferenceFacts  []preferencemodel.Snapshot         `json:"sessionPreferenceFacts,omitempty" bson:"sessionPreferenceFacts,omitempty"`
	LongTermPreferenceFacts []preferencemodel.Snapshot         `json:"longTermPreferenceFacts,omitempty" bson:"longTermPreferenceFacts,omitempty"`
	AnswerText              string                             `json:"answerText,omitempty" bson:"answerText,omitempty"`
	Trigger                 AssistantTurnTrigger               `json:"trigger" bson:"trigger"`
	StreamState             AssistantTurnStreamState           `json:"streamState" bson:"streamState"`
	Failure                 *rtfailures.Failure                `json:"failure,omitempty" bson:"failure,omitempty"`
	ClientRequestID         string                             `json:"clientRequestId,omitempty" bson:"clientRequestId,omitempty"`
	TraceID                 string                             `json:"traceId" bson:"traceId"`
	CreatedAt               time.Time                          `json:"createdAt" bson:"createdAt"`
	CompletedAt             *time.Time                         `json:"completedAt,omitempty" bson:"completedAt,omitempty"`
}

type CreateTurnInput struct {
	TurnType        string                   `json:"turnType"`
	SkillID         string                   `json:"skillId"`
	DomainID        string                   `json:"domainId"`
	Input           AssistantTurnInput       `json:"input"`
	Trigger         AssistantTurnTrigger     `json:"trigger"`
	ClientRequestID string                   `json:"clientRequestId"`
	ContextSnapshot AssistantContextSnapshot `json:"contextSnapshot"`
}

// AssistantConversationListView 是 ListAssistantConversations 的响应切片
// （契约：assistant_conversation/fields.yaml AssistantConversationListView）。
type AssistantConversationListView struct {
	Items      []AssistantConversation `json:"items"`
	NextCursor string                  `json:"nextCursor,omitempty"`
}

// AssistantTurnSummaryView 是会话轮次摘要（契约：assistant_run/fields.yaml
// AssistantTurnSummaryView）；transcript 恢复主体，过程时间线按需走 GetAssistantRun。
type AssistantTurnSummaryView struct {
	TurnID         string `json:"turnId"`
	ConversationID string `json:"conversationId"`
	Status         string `json:"status"`
	InputText      string `json:"inputText"`
	AnswerText     string `json:"answerText,omitempty"`
	SkillID        string `json:"skillId,omitempty"`
	DomainID       string `json:"domainId,omitempty"`
	CreatedAt      string `json:"createdAt"`
	CompletedAt    string `json:"completedAt,omitempty"`
}

// AssistantTurnListView 是 ListConversationTurns 的响应切片
// （契约：assistant_run/fields.yaml AssistantTurnListView）。
type AssistantTurnListView struct {
	Items      []AssistantTurnSummaryView `json:"items"`
	NextCursor string                     `json:"nextCursor,omitempty"`
}
