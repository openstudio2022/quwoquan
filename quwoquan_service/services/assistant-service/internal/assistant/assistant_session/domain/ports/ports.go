package ports

import (
	"context"
	"time"

	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
)

// SessionStore is the AssistantSession aggregate boundary. AssistantRun state,
// journal and receipts belong exclusively to assistant_run.Repository.
type SessionStore interface {
	// InsertSession commits the aggregate and the AssistantSessionCreated
	// domain event returned by AssistantSession.CreatedEvent() in one
	// transaction. A replayed creation returns the stored aggregate and must
	// not append a second event.
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

// PendingSessionEvent is one claimed, not-yet-published AssistantSession
// domain event owned by the transactional outbox.
type PendingSessionEvent struct {
	EventID    string
	EventType  string
	SessionID  string
	OccurredAt time.Time
	Payload    assistant.SessionEventPayload
}

// SessionOutboxStore is the relay-facing half of the AssistantSession
// transactional outbox. Only the store that commits the aggregate may
// implement it, so the event and the aggregate can never diverge.
type SessionOutboxStore interface {
	ClaimPendingSessionEvents(
		context.Context,
		string,
		time.Duration,
		int,
	) ([]PendingSessionEvent, error)
	MarkSessionEventPublished(
		context.Context,
		string,
		string,
		string,
		time.Time,
	) error
	ReleaseSessionEventClaim(context.Context, string, string) error
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
