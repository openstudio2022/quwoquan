package model

import (
	"errors"
	"time"
)

var (
	ErrSessionNotFound = errors.New("assistant turn view session not found")
	ErrInvalidCursor   = errors.New("assistant turn view cursor is invalid")
)

type CitationDestinationView struct {
	Kind          string `json:"kind" bson:"kind"`
	ObjectTypeRef string `json:"objectTypeRef,omitempty" bson:"objectTypeRef,omitempty"`
	ObjectID      string `json:"objectId,omitempty" bson:"objectId,omitempty"`
	URL           string `json:"url,omitempty" bson:"url,omitempty"`
}

type VisibleReferenceView struct {
	Title       string                  `json:"title" bson:"title,omitempty"`
	Destination CitationDestinationView `json:"destination" bson:"destination"`
	Source      string                  `json:"source" bson:"source,omitempty"`
	Snippet     string                  `json:"snippet" bson:"snippet,omitempty"`
}

type VisibleProcessView struct {
	ProcessID              string                 `json:"processId" bson:"processId"`
	Scope                  string                 `json:"scope" bson:"scope"`
	Stage                  string                 `json:"stage" bson:"stage"`
	ActionCode             string                 `json:"actionCode,omitempty" bson:"actionCode,omitempty"`
	Status                 string                 `json:"status" bson:"status"`
	Order                  int                    `json:"order" bson:"order"`
	Summary                string                 `json:"summary,omitempty" bson:"summary,omitempty"`
	SkillID                string                 `json:"skillId,omitempty" bson:"skillId,omitempty"`
	DomainID               string                 `json:"domainId,omitempty" bson:"domainId,omitempty"`
	SearchedDocumentCount  int                    `json:"searchedDocumentCount" bson:"searchedDocumentCount"`
	ProcessedDocumentCount int                    `json:"processedDocumentCount" bson:"processedDocumentCount"`
	AcceptedDocumentCount  int                    `json:"acceptedDocumentCount" bson:"acceptedDocumentCount"`
	AcceptedReferences     []VisibleReferenceView `json:"acceptedReferences" bson:"acceptedReferences"`
}

type TerminalFailureView struct {
	Code   string `json:"code" bson:"code"`
	Origin string `json:"origin" bson:"origin"`
	Kind   string `json:"kind" bson:"kind"`
	Nature string `json:"nature" bson:"nature"`
}

type SelectedPolicyRefView struct {
	PolicyID      string `json:"policyId" bson:"policyId"`
	ReleaseDigest string `json:"releaseDigest" bson:"releaseDigest"`
	Cohort        string `json:"cohort" bson:"cohort"`
}

type TerminalSnapshotView struct {
	AnswerText        string                 `json:"answerText" bson:"answerText"`
	Processes         []VisibleProcessView   `json:"processes" bson:"processes"`
	Failure           *TerminalFailureView   `json:"failure,omitempty" bson:"failure,omitempty"`
	SelectedPolicyRef *SelectedPolicyRefView `json:"selectedPolicyRef,omitempty" bson:"selectedPolicyRef,omitempty"`
}

// Projection is the AssistantTurnView-owned durable document. It contains no
// write-side execution state and can be rebuilt from the typed AssistantRun
// terminal source.
type Projection struct {
	TurnID           string                `bson:"_id"`
	UserID           string                `bson:"userId"`
	SessionID        string                `bson:"sessionId"`
	Status           string                `bson:"status"`
	InputText        string                `bson:"inputText"`
	TerminalSnapshot *TerminalSnapshotView `bson:"terminalSnapshot,omitempty"`
	SkillID          string                `bson:"skillId,omitempty"`
	DomainID         string                `bson:"domainId,omitempty"`
	CreatedAt        time.Time             `bson:"createdAt"`
	CompletedAt      *time.Time            `bson:"completedAt,omitempty"`
	SourceRevision   int64                 `bson:"sourceRevision"`
	SourceUpdatedAt  time.Time             `bson:"sourceUpdatedAt"`
}

type Checkpoint struct {
	SourceUpdatedAt time.Time `bson:"sourceUpdatedAt"`
	SourceRunID     string    `bson:"sourceRunId"`
}

type AssistantTurnSummaryView struct {
	TurnID           string                `json:"turnId"`
	SessionID        string                `json:"sessionId"`
	Status           string                `json:"status"`
	InputText        string                `json:"inputText"`
	TerminalSnapshot *TerminalSnapshotView `json:"terminalSnapshot,omitempty"`
	SkillID          string                `json:"skillId,omitempty"`
	DomainID         string                `json:"domainId,omitempty"`
	CreatedAt        string                `json:"createdAt"`
	CompletedAt      string                `json:"completedAt,omitempty"`
}

type AssistantTurnListView struct {
	Items      []AssistantTurnSummaryView `json:"items"`
	NextCursor string                     `json:"nextCursor,omitempty"`
}
