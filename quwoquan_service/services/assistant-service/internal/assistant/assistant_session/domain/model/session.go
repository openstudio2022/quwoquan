package model

import "time"

// AssistantSession owns only the conversation container lifecycle and its
// compacted summary. Execution state, turns, tools and artifacts belong to
// assistant_run.
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

// AssistantSessionListView is the AssistantSession-owned list projection.
type AssistantSessionListView struct {
	Items      []AssistantSession `json:"items"`
	NextCursor string             `json:"nextCursor,omitempty"`
}
