package ports

import (
	"context"
	"time"

	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
)

// SessionStore is the AssistantSession aggregate boundary. AssistantRun state,
// journal and receipts belong exclusively to assistant_run.Repository.
type SessionStore interface {
	InsertSession(
		context.Context,
		assistant.AssistantSession,
	) (assistant.AssistantSession, bool, error)
	GetSession(
		context.Context,
		string,
	) (assistant.AssistantSession, bool, error)
	OwnedSessionExists(context.Context, string, string) (bool, error)
	ListSessions(
		context.Context,
		string,
		int,
		string,
	) ([]assistant.AssistantSession, string, error)
	CommitSessionSummary(
		context.Context,
		SessionSummaryCommit,
	) (SessionSummaryCommitResult, error)
}

type SessionSummaryCommit struct {
	CompletionEventID      string
	SessionID              string
	ExpectedVersion        int64
	ExpectedSourceSequence int64
	NextSourceSequence     int64
	Summary                assistant.AssistantSessionContextSummary
	UpdatedAt              time.Time
}

type SessionSummaryCommitResult struct {
	Applied  bool
	Replayed bool
	Conflict bool
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
	) (bool, error)
	ListMessages(
		context.Context,
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
