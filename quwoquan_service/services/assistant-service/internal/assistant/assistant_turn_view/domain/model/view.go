package model

import (
	"errors"
	"time"

	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

var (
	ErrSessionNotFound = errors.New("assistant turn view session not found")
	ErrInvalidCursor   = errors.New("assistant turn view cursor is invalid")
)

// Projection is the AssistantTurnView-owned durable document. It contains no
// write-side execution state and can be rebuilt from the typed AssistantRun
// terminal source.
type Projection struct {
	TurnID           string                                       `bson:"_id"`
	UserID           string                                       `bson:"userId"`
	SessionID        string                                       `bson:"sessionId"`
	Status           string                                       `bson:"status"`
	InputText        string                                       `bson:"inputText"`
	TerminalSnapshot *assistantmodel.AssistantRunTerminalSnapshot `bson:"terminalSnapshot,omitempty"`
	SkillID          string                                       `bson:"skillId,omitempty"`
	DomainID         string                                       `bson:"domainId,omitempty"`
	CreatedAt        time.Time                                    `bson:"createdAt"`
	CompletedAt      *time.Time                                   `bson:"completedAt,omitempty"`
	SourceRevision   int64                                        `bson:"sourceRevision"`
	SourceUpdatedAt  time.Time                                    `bson:"sourceUpdatedAt"`
}

type Checkpoint struct {
	SourceUpdatedAt time.Time `bson:"sourceUpdatedAt"`
	SourceRunID     string    `bson:"sourceRunId"`
}

type AssistantTurnSummaryView struct {
	TurnID           string                                       `json:"turnId"`
	SessionID        string                                       `json:"sessionId"`
	Status           string                                       `json:"status"`
	InputText        string                                       `json:"inputText"`
	TerminalSnapshot *assistantmodel.AssistantRunTerminalSnapshot `json:"terminalSnapshot,omitempty"`
	SkillID          string                                       `json:"skillId,omitempty"`
	DomainID         string                                       `json:"domainId,omitempty"`
	CreatedAt        string                                       `json:"createdAt"`
	CompletedAt      string                                       `json:"completedAt,omitempty"`
}

type AssistantTurnListView struct {
	Items      []AssistantTurnSummaryView `json:"items"`
	NextCursor string                     `json:"nextCursor,omitempty"`
}
