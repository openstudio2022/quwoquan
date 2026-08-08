// Package runruntime owns the durable AssistantRun state machine. It exposes
// decision summaries and evidence references only; model reasoning traces are
// never part of the aggregate or journal item contract.
package runruntime

import (
	"errors"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
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
	TaskID             string                        `bson:"taskId"`
	Goal               string                        `bson:"goal"`
	Dependencies       []string                      `bson:"dependencies"`
	Status             generated.AssistantTaskStatus `bson:"status"`
	OwnerAgent         string                        `bson:"ownerAgent"`
	Attempt            int                           `bson:"attempt"`
	ClaimID            string                        `bson:"claimId,omitempty"`
	ClaimOwner         string                        `bson:"claimOwner,omitempty"`
	FencingToken       int64                         `bson:"fencingToken"`
	HeartbeatAt        time.Time                     `bson:"heartbeatAt,omitempty"`
	LeaseExpiresAt     time.Time                     `bson:"leaseExpiresAt,omitempty"`
	IdempotencyKey     string                        `bson:"idempotencyKey,omitempty"`
	ResultArtifactRef  string                        `bson:"resultArtifactRef,omitempty"`
	TerminalReceiptRef string                        `bson:"terminalReceiptRef,omitempty"`
	Budget             TaskBudget                    `bson:"budget"`
	ArtifactRefs       []string                      `bson:"artifactRefs"`
	Verification       TaskVerification              `bson:"verification"`
	BlockReason        string                        `bson:"blockReason"`
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
	InstallationID string    `bson:"installationId" json:"installationId"`
	DeviceID       string    `bson:"deviceId" json:"deviceId"`
	Capability     string    `bson:"capability" json:"capability"`
	InputDigest    string    `bson:"inputDigest" json:"inputDigest"`
	Permit         string    `bson:"permit" json:"permit"`
	IdempotencyKey string    `bson:"idempotencyKey" json:"idempotencyKey"`
	Outcome        string    `bson:"outcome" json:"outcome"`
	ExecutedAt     time.Time `bson:"executedAt" json:"executedAt"`
	DeviceObjectID string    `bson:"deviceObjectId,omitempty" json:"deviceObjectId,omitempty"`
	FailureCode    string    `bson:"failureCode,omitempty" json:"failureCode,omitempty"`
}

type DeviceActionPermit struct {
	RunID            string    `bson:"runId" json:"runId"`
	ToolInvocationID string    `bson:"toolInvocationId" json:"toolInvocationId"`
	InstallationID   string    `bson:"installationId" json:"installationId"`
	DeviceID         string    `bson:"deviceId" json:"deviceId"`
	Capability       string    `bson:"capability" json:"capability"`
	InputDigest      string    `bson:"inputDigest" json:"inputDigest"`
	IdempotencyKey   string    `bson:"idempotencyKey" json:"idempotencyKey"`
	ApprovalRef      string    `bson:"approvalRef" json:"approvalRef"`
	JTI              string    `bson:"jti" json:"jti"`
	ExpiresAt        time.Time `bson:"expiresAt" json:"expiresAt"`
	Permit           string    `bson:"permit" json:"permit"`
}

// ContextObservationSnapshot is the bounded, user-visible observation state
// that may survive an AgentLoop restart. It deliberately excludes raw tool
// payloads, prompts and model reasoning; large results remain in Artifact
// Store and the Run journal.
type ContextObservationSnapshot struct {
	Iteration int      `bson:"iteration"`
	ToolName  string   `bson:"toolName"`
	Status    string   `bson:"status"`
	Summary   string   `bson:"summary"`
	SourceIDs []string `bson:"sourceIds"`
}

// ContextExecutionState is the durable cursor for one AssistantRun AgentLoop.
// Counters and the source ledger are absolute for the Run goal revision, so a
// worker restart cannot reset exploration or tool budgets.
type ContextExecutionState struct {
	PlanCursor          int                          `bson:"planCursor"`
	ToolIteration       int                          `bson:"toolIteration"`
	ReflectionIteration int                          `bson:"reflectionIteration"`
	NavigationDepth     int                          `bson:"navigationDepth"`
	SourceIDs           []string                     `bson:"sourceIds"`
	ToolHistory         []string                     `bson:"toolHistory"`
	ModelHistory        []string                     `bson:"modelHistory,omitempty"`
	RecentObservations  []ContextObservationSnapshot `bson:"recentObservations"`
}

// ContextCompactionCheckpoint owns only a bounded semantic summary and the
// exact cursor at which it was produced. Canonical permissions, consent,
// object ownership and DefinitionOfDone are re-injected from Run state and are
// never copied into or trusted from this summary.
type ContextCompactionCheckpoint struct {
	ContextRevision int64                 `bson:"contextRevision"`
	SummaryText     string                `bson:"summaryText"`
	State           ContextExecutionState `bson:"state"`
	CompactedAt     time.Time             `bson:"compactedAt"`
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
	PendingDeviceAction  *DeviceActionPermit            `bson:"pendingDeviceAction,omitempty"`
	DeviceActionReceipts []DeviceActionExecutionReceipt `bson:"deviceActionReceipts"`
	BudgetConsumption    BudgetConsumption              `bson:"budgetConsumption"`
	BudgetReceiptScope   string                         `bson:"budgetReceiptScope"`
	BudgetReceiptSeq     int64                          `bson:"budgetReceiptSeq"`
	ContextState         ContextExecutionState          `bson:"contextState"`
	ContextCompaction    *ContextCompactionCheckpoint   `bson:"contextCompaction,omitempty"`
	ContextReceiptScope  string                         `bson:"contextReceiptScope"`
	ContextReceiptSeq    int64                          `bson:"contextReceiptSeq"`
	RemainingBudget      map[string]int64               `bson:"remainingBudget"`
	CreatedAt            time.Time                      `bson:"createdAt"`
}

type GoalRevision struct {
	Revision    int64     `bson:"revision"`
	Instruction string    `bson:"instruction"`
	AppliedAt   time.Time `bson:"appliedAt"`
}

type FrozenPolicyTemplate struct {
	TemplateID      string   `bson:"templateId"`
	SkillID         string   `bson:"skillId"`
	DomainID        string   `bson:"domainId"`
	PromptPolicy    string   `bson:"promptPolicy"`
	AllowedTools    []string `bson:"allowedTools"`
	SearchIntensity string   `bson:"searchIntensity"`
}

type FrozenLearningContextPolicy struct {
	Enabled                  bool     `bson:"enabled"`
	AllowedSignals           []string `bson:"allowedSignals"`
	AllowedMetricIDs         []string `bson:"allowedMetricIds"`
	AllowedReasonCodes       []string `bson:"allowedReasonCodes"`
	MinimumFeedbackSamples   int      `bson:"minimumFeedbackSamples"`
	WindowDays               int      `bson:"windowDays"`
	SnapshotTrainingEligible bool     `bson:"snapshotTrainingEligible"`
}

type FrozenPolicySelection struct {
	PolicyID              string                      `bson:"policyId"`
	ReleaseDigest         string                      `bson:"releaseDigest"`
	Cohort                string                      `bson:"cohort"`
	RolloutRevision       int                         `bson:"rolloutRevision"`
	RuleID                string                      `bson:"ruleId"`
	Template              FrozenPolicyTemplate        `bson:"template"`
	LearningContextPolicy FrozenLearningContextPolicy `bson:"learningContextPolicy"`
}

type RequestContext struct {
	ClientSessionID string `bson:"clientSessionId,omitempty"`
	PageID          string `bson:"pageId,omitempty"`
	SurfaceKind     string `bson:"surfaceKind,omitempty"`
	SurfaceID       string `bson:"surfaceId,omitempty"`
	RouteID         string `bson:"routeId,omitempty"`
	OperationID     string `bson:"operationId,omitempty"`
	TraceID         string `bson:"traceId,omitempty"`
	PersonaID       string `bson:"personaId,omitempty"`
}

// SessionContinuity is the AssistantRun-side anti-corruption snapshot of the
// owning AssistantSession summary. It is frozen when the Run starts and never
// contains permission, consent, ownership or safety-policy state.
type SessionContinuity struct {
	SummaryID      string            `bson:"summaryId"`
	Text           string            `bson:"text"`
	FromTurnID     string            `bson:"fromTurnId"`
	ToTurnID       string            `bson:"toTurnId"`
	TurnCount      int               `bson:"turnCount"`
	CurrentGoal    string            `bson:"currentGoal,omitempty"`
	ConfirmedFacts []string          `bson:"confirmedFacts,omitempty"`
	PendingItems   []string          `bson:"pendingItems,omitempty"`
	ConfirmedSlots map[string]string `bson:"confirmedSlots,omitempty"`
}

type Run struct {
	RunID                     string                                          `bson:"runId"`
	UserID                    string                                          `bson:"userId"`
	PersonaID                 string                                          `bson:"personaId,omitempty"`
	SessionID                 string                                          `bson:"sessionId"`
	ClientRequestID           string                                          `bson:"clientRequestId"`
	ExecutionInputDigest      string                                          `bson:"executionInputDigest"`
	TraceID                   string                                          `bson:"traceId"`
	RequestContext            RequestContext                                  `bson:"requestContext"`
	IntentKind                string                                          `bson:"intentKind"`
	InputText                 string                                          `bson:"inputText"`
	RequestedSkillID          string                                          `bson:"requestedSkillId,omitempty"`
	RequestedDomainID         string                                          `bson:"requestedDomainId,omitempty"`
	SkillPackageID            string                                          `bson:"skillPackageId"`
	SkillPackageReleaseDigest string                                          `bson:"skillPackageReleaseDigest"`
	FrozenPolicySelection     FrozenPolicySelection                           `bson:"frozenPolicySelection"`
	Trigger                   map[string]any                                  `bson:"trigger,omitempty"`
	ContextSnapshot           map[string]any                                  `bson:"contextSnapshot,omitempty"`
	SurfaceCapabilities       map[string]any                                  `bson:"surfaceCapabilities,omitempty"`
	SessionContinuity         *SessionContinuity                              `bson:"sessionContinuity,omitempty"`
	ConfirmedSlots            assistantmodel.AssistantRunConfirmedSlots       `bson:"confirmedSlots,omitempty"`
	SessionPreferences        []preferencemodel.AssistantPreferenceSnapshot   `bson:"sessionPreferences,omitempty"`
	LongTermPreferences       []preferencemodel.AssistantPreferenceSnapshot   `bson:"longTermPreferences,omitempty"`
	FeedbackContextSnapshot   assistantmodel.AssistantFeedbackContextSnapshot `bson:"feedbackContextSnapshot"`
	Revision                  int64                                           `bson:"revision"`
	JournalSequence           int64                                           `bson:"journalSequence"`
	GoalRevision              int64                                           `bson:"goalRevision"`
	State                     generated.AssistantRunState                     `bson:"state"`
	ReasoningProfile          generated.AssistantReasoningProfile             `bson:"reasoningProfile"`
	ReasoningPolicy           ReasoningProfileConfig                          `bson:"reasoningPolicy"`
	DefinitionOfDone          DefinitionOfDone                                `bson:"definitionOfDone"`
	TaskGraph                 TaskGraph                                       `bson:"taskGraph"`
	Items                     []RunItem                                       `bson:"items"`
	Checkpoint                *Checkpoint                                     `bson:"checkpoint,omitempty"`
	PresentationDocument      map[string]any                                  `bson:"presentationDocument,omitempty"`
	GoalHistory               []GoalRevision                                  `bson:"goalHistory"`
	PendingSteer              []string                                        `bson:"pendingSteer"`
	PauseRequested            bool                                            `bson:"pauseRequested"`
	PauseReason               string                                          `bson:"pauseReason"`
	SuspendedFrom             generated.AssistantRunState                     `bson:"suspendedFrom"`
	TerminalReason            string                                          `bson:"terminalReason"`
	TerminalSnapshot          *assistantmodel.AssistantRunTerminalSnapshot    `bson:"terminalSnapshot,omitempty"`
	CreatedAt                 time.Time                                       `bson:"createdAt"`
	UpdatedAt                 time.Time                                       `bson:"updatedAt"`
	CompletedAt               *time.Time                                      `bson:"completedAt,omitempty"`
}

type VerificationEvidence struct {
	Requirement   string
	VerifierID    string
	Passed        bool
	ArtifactRefs  []string
	Summary       string
	FixSuggestion string
}

type VerificationVerdict struct {
	Accepted        bool
	Evidence        []VerificationEvidence
	Missing         []string
	Failed          []string
	DecisionSummary string
}

var (
	ErrInvalidRun        = errors.New("invalid assistant run")
	ErrInvalidTransition = errors.New("invalid assistant run transition")
	ErrRevisionConflict  = errors.New("assistant run revision conflict")
	// ErrRunIdempotencyConflict is distinct from aggregate CAS contention: the
	// caller reused one Start identity for a different immutable input.
	ErrRunIdempotencyConflict = errors.New("assistant run idempotency conflict")
	ErrInvalidTaskGraph       = errors.New("invalid assistant task graph")
	ErrTaskNotReady           = errors.New("assistant task is not ready")
	ErrItemStateConflict      = errors.New("assistant run item state conflict")
	ErrCompletionRejected     = errors.New("assistant run completion rejected")
	ErrUnsafePayload          = errors.New("assistant run item contains unsafe reasoning payload")
	ErrRunNotFound            = errors.New("assistant run not found")
	ErrLeaseConflict          = errors.New("assistant run worker lease conflict")
	ErrJournalGap             = errors.New("assistant run journal gap")
	ErrJournalCorrupt         = errors.New("assistant run journal is corrupt")
	ErrNoWork                 = errors.New("assistant run queue has no ready work")
	ErrExecutionFenced        = errors.New("assistant run execution is fenced")
	ErrExecutionCancelled     = errors.New("assistant run execution was cancelled")
	// ErrExecutionReplanned stops the current in-memory AgentLoop after a
	// steering instruction crossed a persisted Item boundary. The Run remains
	// runnable and the next claim receives the revised effective goal.
	ErrExecutionReplanned      = errors.New("assistant run execution must replan")
	ErrSkillPackageUnavailable = errors.New("assistant Skill package is unavailable")
	ErrSkillDisabled           = errors.New("assistant Skill is disabled by the effective account or surface policy")
	ErrSkillSettingUnavailable = errors.New("assistant Skill setting is unavailable")
	ErrPolicyUnavailable       = errors.New("assistant policy selection is unavailable")
	// Device permit failures are command-domain decisions. Keeping them
	// separate prevents HTTP mapping from collapsing security rejection into a
	// retryable aggregate revision conflict or a generic invalid argument.
	ErrDeviceActionPermitInvalid  = errors.New("assistant device action permit is invalid")
	ErrDeviceActionPermitExpired  = errors.New("assistant device action permit is expired")
	ErrDeviceActionPermitReplayed = errors.New("assistant device action permit was already consumed")
)
