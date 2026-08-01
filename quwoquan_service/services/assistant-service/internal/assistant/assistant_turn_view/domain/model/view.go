package model

import (
	"errors"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

var (
	ErrSessionNotFound = errors.New("assistant turn view session not found")
	ErrInvalidCursor   = errors.New("assistant turn view cursor is invalid")
)

// AssistantTurnSummaryView is the terminal session-history slice owned by
// AssistantTurnView. The terminal snapshot is the shared, durable Run value
// object used by GetRun, terminal SSE replay, and history recovery.
type AssistantTurnSummaryView struct {
	TurnID           string                                  `json:"turnId"`
	SessionID        string                                  `json:"sessionId"`
	Status           string                                  `json:"status"`
	InputText        string                                  `json:"inputText"`
	TerminalSnapshot *assistant.AssistantRunTerminalSnapshot `json:"terminalSnapshot,omitempty"`
	SkillID          string                                  `json:"skillId,omitempty"`
	DomainID         string                                  `json:"domainId,omitempty"`
	CreatedAt        string                                  `json:"createdAt"`
	CompletedAt      string                                  `json:"completedAt,omitempty"`
}

// AssistantTurnListView is the only wire result of ListSessionTurns.
type AssistantTurnListView struct {
	Items      []AssistantTurnSummaryView `json:"items"`
	NextCursor string                     `json:"nextCursor,omitempty"`
}
