package assistant

import (
	"time"

	rtfailures "quwoquan_service/runtime/failures"
)

type AssistantConversation struct {
	ConversationID string    `json:"conversationId"`
	UserID         string    `json:"userId"`
	State          string    `json:"state"`
	ActiveTurnID   string    `json:"activeTurnId,omitempty"`
	LastTurnID     string    `json:"lastTurnId,omitempty"`
	Summary        string    `json:"summary,omitempty"`
	CreatedAt      time.Time `json:"createdAt"`
	UpdatedAt      time.Time `json:"updatedAt"`
}

type CreateConversationInput struct {
	Summary string `json:"summary"`
}

type AssistantTurnInput struct {
	Text string `json:"text"`
}

type AssistantTurnTrigger struct {
	Type string `json:"type"`
}

type AssistantTurnStreamState struct {
	LastSeq     uint64 `json:"lastSeq"`
	Completed   bool   `json:"completed"`
	ResumeToken string `json:"resumeToken"`
}

type AssistantTurn struct {
	TurnID         string                   `json:"turnId"`
	ConversationID string                   `json:"conversationId"`
	UserID         string                   `json:"userId"`
	TurnType       string                   `json:"turnType"`
	Status         string                   `json:"status"`
	SkillID        string                   `json:"skillId,omitempty"`
	DomainID       string                   `json:"domainId,omitempty"`
	Input          AssistantTurnInput       `json:"input"`
	Trigger        AssistantTurnTrigger     `json:"trigger"`
	StreamState    AssistantTurnStreamState `json:"streamState"`
	Failure        *rtfailures.Failure      `json:"failure,omitempty"`
	TraceID        string                   `json:"traceId"`
	CreatedAt      time.Time                `json:"createdAt"`
	CompletedAt    *time.Time               `json:"completedAt,omitempty"`
}

type CreateTurnInput struct {
	TurnType string               `json:"turnType"`
	SkillID  string               `json:"skillId"`
	DomainID string               `json:"domainId"`
	Input    AssistantTurnInput   `json:"input"`
	Trigger  AssistantTurnTrigger `json:"trigger"`
}
