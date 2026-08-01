// Package runruntime owns the durable AssistantRun state machine. It exposes
// decision summaries and evidence references only; model reasoning traces are
// never part of the aggregate or journal item contract.
package runruntime

import (
	"errors"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
)

type DefinitionOfDone struct {
	Outcome                  string    `bson:"outcome"`
	Constraints              []string  `bson:"constraints"`
	VerificationRequirements []string  `bson:"verificationRequirements"`
	FrozenAt                 time.Time `bson:"frozenAt"`
}

type TaskBudget struct {
	MaxToolCalls int       `bson:"maxToolCalls"`
	MaxTokens    int64     `bson:"maxTokens"`
	MaxCostUnits int64     `bson:"maxCostUnits"`
	Deadline     time.Time `bson:"deadline"`
}

type TaskVerification struct {
	Requirements []string `bson:"requirements"`
	EvidenceRefs []string `bson:"evidenceRefs"`
	Passed       bool     `bson:"passed"`
	Summary      string   `bson:"summary"`
}

type TaskNode struct {
	TaskID       string                        `bson:"taskId"`
	Goal         string                        `bson:"goal"`
	Dependencies []string                      `bson:"dependencies"`
	Status       generated.AssistantTaskStatus `bson:"status"`
	OwnerAgent   string                        `bson:"ownerAgent"`
	Attempt      int                           `bson:"attempt"`
	Budget       TaskBudget                    `bson:"budget"`
	ArtifactRefs []string                      `bson:"artifactRefs"`
	Verification TaskVerification              `bson:"verification"`
	BlockReason  string                        `bson:"blockReason"`
}

type TaskGraph struct {
	GraphRevision int64      `bson:"graphRevision"`
	Tasks         []TaskNode `bson:"tasks"`
}

type RunItem struct {
	ItemID       string                           `bson:"itemId"`
	Kind         generated.AssistantRunItemKind   `bson:"kind"`
	Status       generated.AssistantRunItemStatus `bson:"status"`
	Sequence     int64                            `bson:"sequence"`
	TaskID       string                           `bson:"taskId"`
	Summary      string                           `bson:"summary"`
	Payload      map[string]any                   `bson:"payload"`
	ArtifactRefs []string                         `bson:"artifactRefs"`
	StartedAt    time.Time                        `bson:"startedAt"`
	CompletedAt  time.Time                        `bson:"completedAt"`
}

type DeviceActionExecutionReceipt struct {
	ActionKind     string    `bson:"actionKind"`
	IdempotencyKey string    `bson:"idempotencyKey"`
	Outcome        string    `bson:"outcome"`
	ExecutedAt     time.Time `bson:"executedAt"`
	DeviceObjectID string    `bson:"deviceObjectId,omitempty"`
	FailureCode    string    `bson:"failureCode,omitempty"`
}

type Checkpoint struct {
	CheckpointID         string                         `bson:"checkpointId"`
	Revision             int64                          `bson:"revision"`
	GoalSummary          string                         `bson:"goalSummary"`
	DecisionSummary      []string                       `bson:"decisionSummary"`
	CompletedTaskIDs     []string                       `bson:"completedTaskIds"`
	OpenTaskIDs          []string                       `bson:"openTaskIds"`
	EvidenceRefs         []string                       `bson:"evidenceRefs"`
	PendingApprovalRef   string                         `bson:"pendingApprovalRef"`
	DeviceActionReceipts []DeviceActionExecutionReceipt `bson:"deviceActionReceipts"`
	RemainingBudget      map[string]int64               `bson:"remainingBudget"`
	CreatedAt            time.Time                      `bson:"createdAt"`
}

type GoalRevision struct {
	Revision    int64     `bson:"revision"`
	Instruction string    `bson:"instruction"`
	AppliedAt   time.Time `bson:"appliedAt"`
}

type Run struct {
	RunID                   string                              `bson:"runId"`
	UserID                  string                              `bson:"userId"`
	SessionID               string                              `bson:"sessionId"`
	ClientRequestID         string                              `bson:"clientRequestId"`
	ExecutionInputDigest    string                              `bson:"executionInputDigest"`
	TraceID                 string                              `bson:"traceId"`
	IntentKind              string                              `bson:"intentKind"`
	InputText               string                              `bson:"inputText"`
	RequestedSkillID        string                              `bson:"requestedSkillId,omitempty"`
	RequestedDomainID       string                              `bson:"requestedDomainId,omitempty"`
	Trigger                 map[string]any                      `bson:"trigger,omitempty"`
	ContextSnapshot         map[string]any                      `bson:"contextSnapshot,omitempty"`
	SurfaceCapabilities     map[string]any                      `bson:"surfaceCapabilities,omitempty"`
	SessionPreferenceFacts  []preferencemodel.Snapshot          `bson:"sessionPreferenceFacts,omitempty"`
	LongTermPreferenceFacts []preferencemodel.Snapshot          `bson:"longTermPreferenceFacts,omitempty"`
	Revision                int64                               `bson:"revision"`
	JournalSequence         int64                               `bson:"journalSequence"`
	GoalRevision            int64                               `bson:"goalRevision"`
	State                   generated.AssistantRunState         `bson:"state"`
	ReasoningProfile        generated.AssistantReasoningProfile `bson:"reasoningProfile"`
	DefinitionOfDone        DefinitionOfDone                    `bson:"definitionOfDone"`
	TaskGraph               TaskGraph                           `bson:"taskGraph"`
	Items                   []RunItem                           `bson:"items"`
	Checkpoint              *Checkpoint                         `bson:"checkpoint,omitempty"`
	PresentationDocument    map[string]any                      `bson:"presentationDocument,omitempty"`
	GoalHistory             []GoalRevision                      `bson:"goalHistory"`
	PendingSteer            []string                            `bson:"pendingSteer"`
	PauseRequested          bool                                `bson:"pauseRequested"`
	PauseReason             string                              `bson:"pauseReason"`
	SuspendedFrom           generated.AssistantRunState         `bson:"suspendedFrom"`
	TerminalReason          string                              `bson:"terminalReason"`
	TerminalSnapshot        map[string]any                      `bson:"terminalSnapshot"`
	CreatedAt               time.Time                           `bson:"createdAt"`
	UpdatedAt               time.Time                           `bson:"updatedAt"`
	CompletedAt             *time.Time                          `bson:"completedAt,omitempty"`
}

type VerificationEvidence struct {
	Requirement  string
	Passed       bool
	EvidenceRefs []string
	Summary      string
}

type VerificationVerdict struct {
	Accepted        bool
	Evidence        []VerificationEvidence
	Missing         []string
	Failed          []string
	DecisionSummary string
}

var (
	ErrInvalidRun         = errors.New("invalid assistant run")
	ErrInvalidTransition  = errors.New("invalid assistant run transition")
	ErrRevisionConflict   = errors.New("assistant run revision conflict")
	ErrInvalidTaskGraph   = errors.New("invalid assistant task graph")
	ErrTaskNotReady       = errors.New("assistant task is not ready")
	ErrItemStateConflict  = errors.New("assistant run item state conflict")
	ErrCompletionRejected = errors.New("assistant run completion rejected")
	ErrUnsafePayload      = errors.New("assistant run item contains unsafe reasoning payload")
	ErrRunNotFound        = errors.New("assistant run not found")
	ErrLeaseConflict      = errors.New("assistant run worker lease conflict")
	ErrJournalGap         = errors.New("assistant run journal gap")
	ErrJournalCorrupt     = errors.New("assistant run journal is corrupt")
	ErrNoWork             = errors.New("assistant run queue has no ready work")
	ErrExecutionFenced    = errors.New("assistant run execution is fenced")
	ErrExecutionCancelled = errors.New("assistant run execution was cancelled")
)
