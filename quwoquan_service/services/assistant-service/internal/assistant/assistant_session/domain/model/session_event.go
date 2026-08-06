package model

import "time"

// Event names are the ones declared by
// services/assistant-service/contracts/assistant/assistant_session/events.yaml.
const (
	SessionCreatedEventType  = "AssistantSessionCreated"
	SessionArchivedEventType = "AssistantSessionArchived"
)

// SessionEventPayload carries exactly the payload_fields declared for the
// AssistantSession events; nothing else may leave the aggregate boundary.
type SessionEventPayload struct {
	SessionID string `json:"sessionId" bson:"sessionId"`
}

// SessionDomainEvent is the AssistantSession aggregate's outbound fact. It is
// produced by the aggregate and must be committed in the same transaction as
// the aggregate mutation that produced it.
type SessionDomainEvent struct {
	EventID    string
	EventType  string
	SessionID  string
	OccurredAt time.Time
	Payload    SessionEventPayload
}

// CreatedEvent returns the AssistantSessionCreated fact for this aggregate.
// The event identity is derived from the aggregate identity so a replayed
// creation can never append a second event.
func (session AssistantSession) CreatedEvent() SessionDomainEvent {
	return SessionDomainEvent{
		EventID:    SessionCreatedEventType + ":" + session.SessionID,
		EventType:  SessionCreatedEventType,
		SessionID:  session.SessionID,
		OccurredAt: session.CreatedAt.UTC(),
		Payload:    SessionEventPayload{SessionID: session.SessionID},
	}
}
