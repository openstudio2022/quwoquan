package runruntime

import (
	"fmt"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

func NewRun(
	runID string,
	profile generated.AssistantReasoningProfile,
	definition DefinitionOfDone,
	graph TaskGraph,
	now time.Time,
) (Run, error) {
	if strings.TrimSpace(runID) == "" || strings.TrimSpace(definition.Outcome) == "" ||
		definition.FrozenAt.IsZero() || len(definition.VerificationRequirements) == 0 {
		return Run{}, ErrInvalidRun
	}
	graph.Tasks = cloneTasks(graph.Tasks)
	for index := range graph.Tasks {
		if graph.Tasks[index].Status != generated.AssistantTaskStatusPending &&
			graph.Tasks[index].Status != generated.AssistantTaskStatusReady {
			return Run{}, ErrInvalidTaskGraph
		}
		graph.Tasks[index].Status = generated.AssistantTaskStatusPending
	}
	if err := validateTaskGraph(graph.Tasks); err != nil {
		return Run{}, err
	}
	if graph.GraphRevision <= 0 {
		graph.GraphRevision = 1
	}
	graph.refreshReadyTasks()
	now = now.UTC()
	return Run{
		RunID:            runID,
		Revision:         1,
		GoalRevision:     1,
		State:            generated.AssistantRunStateAccepted,
		ReasoningProfile: profile,
		DefinitionOfDone: cloneDefinition(definition),
		TaskGraph:        TaskGraph{GraphRevision: graph.GraphRevision, Tasks: cloneTasks(graph.Tasks)},
		CreatedAt:        now,
		UpdatedAt:        now,
	}, nil
}

// BindIdentity freezes the owner, session, and idempotency identity before the
// first repository commit. These fields are immutable for the lifetime of the
// AssistantRun and are used by owner isolation and StartRun replay.
func (r *Run) BindIdentity(
	userID string,
	sessionID string,
	clientRequestID string,
	traceID string,
	inputText string,
) error {
	if r == nil ||
		strings.TrimSpace(userID) == "" ||
		strings.TrimSpace(sessionID) == "" ||
		strings.TrimSpace(clientRequestID) == "" {
		return ErrInvalidRun
	}
	if r.UserID != "" || r.SessionID != "" || r.ClientRequestID != "" {
		return ErrRevisionConflict
	}
	r.UserID = strings.TrimSpace(userID)
	r.SessionID = strings.TrimSpace(sessionID)
	r.ClientRequestID = strings.TrimSpace(clientRequestID)
	r.TraceID = strings.TrimSpace(traceID)
	r.InputText = strings.TrimSpace(inputText)
	return nil
}

func (r *Run) BindExecutionInput(
	intentKind string,
	inputDigest string,
	requestedSkillID string,
	requestedDomainID string,
	trigger map[string]any,
	contextSnapshot map[string]any,
	surfaceCapabilities map[string]any,
) error {
	if r == nil ||
		strings.TrimSpace(intentKind) == "" ||
		strings.TrimSpace(inputDigest) == "" ||
		r.IntentKind != "" {
		return ErrInvalidRun
	}
	r.IntentKind = strings.TrimSpace(intentKind)
	r.ExecutionInputDigest = strings.TrimSpace(inputDigest)
	r.RequestedSkillID = strings.TrimSpace(requestedSkillID)
	r.RequestedDomainID = strings.TrimSpace(requestedDomainID)
	r.Trigger = cloneMap(trigger)
	r.ContextSnapshot = cloneMap(contextSnapshot)
	r.SurfaceCapabilities = cloneMap(surfaceCapabilities)
	return nil
}

func (r *Run) SetTerminalSnapshot(snapshot map[string]any, now time.Time) error {
	if r == nil || !terminalState(r.State) || len(snapshot) == 0 {
		return ErrInvalidRun
	}
	if unsafeReasoningPayload(snapshot) {
		return ErrUnsafePayload
	}
	r.TerminalSnapshot = cloneMap(snapshot)
	r.touch(now)
	return nil
}

func (r *Run) SetPresentationDocument(document map[string]any, now time.Time) error {
	if r == nil || terminalState(r.State) || !validPresentationDocument(document) {
		return ErrInvalidRun
	}
	if unsafeReasoningPayload(document) {
		return ErrUnsafePayload
	}
	r.PresentationDocument = cloneMap(document)
	r.touch(now)
	return nil
}

func (r *Run) CommitPresentation(now time.Time) error {
	if r == nil || terminalState(r.State) || !validPresentationDocument(r.PresentationDocument) {
		return ErrInvalidRun
	}
	revision, ok := presentationRevision(r.PresentationDocument["revision"])
	if !ok {
		return ErrInvalidRun
	}
	document := cloneMap(r.PresentationDocument)
	document["revision"] = revision + 1
	document["committedAt"] = now.UTC().Format(time.RFC3339Nano)
	r.PresentationDocument = document
	r.touch(now)
	return nil
}

func validPresentationDocument(document map[string]any) bool {
	if strings.TrimSpace(stringField(document, "templateRef")) == "" ||
		strings.TrimSpace(stringField(document, "templateDigest")) == "" ||
		strings.TrimSpace(stringField(document, "rootNodeId")) == "" ||
		(strings.TrimSpace(stringField(document, "fallbackMarkdown")) == "" &&
			strings.TrimSpace(stringField(document, "fallbackPlainText")) == "") {
		return false
	}
	revision, ok := presentationRevision(document["revision"])
	return ok && revision > 0
}

func presentationRevision(value any) (int64, bool) {
	switch revision := value.(type) {
	case int:
		return int64(revision), true
	case int32:
		return int64(revision), true
	case int64:
		return revision, true
	case float64:
		if revision != float64(int64(revision)) {
			return 0, false
		}
		return int64(revision), true
	default:
		return 0, false
	}
}

func stringField(value map[string]any, key string) string {
	raw, _ := value[key].(string)
	return raw
}

func (r *Run) Transition(next generated.AssistantRunState, reason string, now time.Time) error {
	if r == nil {
		return ErrInvalidTransition
	}
	if terminalState(r.State) || !allowedTransitions[r.State][next] {
		return fmt.Errorf("%w: %s -> %s", ErrInvalidTransition, r.State, next)
	}
	previous := r.State
	r.State = next
	if next == generated.AssistantRunStatePaused {
		r.SuspendedFrom = previous
		r.PauseReason = strings.TrimSpace(reason)
		r.PauseRequested = false
	}
	if terminalState(next) {
		r.TerminalReason = strings.TrimSpace(reason)
		completedAt := now.UTC()
		r.CompletedAt = &completedAt
	}
	r.touch(now)
	observeRunTransition(previous.WireName(), next.WireName())
	return nil
}

func (r *Run) RequestPause(reason string, now time.Time) error {
	if r == nil || terminalState(r.State) || r.State == generated.AssistantRunStatePaused {
		return ErrInvalidTransition
	}
	r.PauseRequested = true
	r.PauseReason = strings.TrimSpace(reason)
	if safeBoundary(r.State) {
		return r.Transition(generated.AssistantRunStatePaused, reason, now)
	}
	r.touch(now)
	return nil
}

func (r *Run) Resume(now time.Time) error {
	if r == nil || r.State != generated.AssistantRunStatePaused {
		return ErrInvalidTransition
	}
	next := r.SuspendedFrom
	if !allowedTransitions[generated.AssistantRunStatePaused][next] {
		next = generated.AssistantRunStateOrienting
	}
	r.SuspendedFrom = ""
	r.PauseReason = ""
	return r.Transition(next, "", now)
}

func (r *Run) RequestSteer(instruction string, now time.Time) error {
	instruction = strings.TrimSpace(instruction)
	if r == nil || terminalState(r.State) || instruction == "" {
		return ErrInvalidRun
	}
	r.PendingSteer = append(r.PendingSteer, instruction)
	if safeBoundary(r.State) {
		r.applyPendingSteer(now)
	} else {
		r.touch(now)
	}
	return nil
}

// ApplySafeBoundary applies steering and cooperative pause only after the
// current Item/Task has reached a durable boundary.
func (r *Run) ApplySafeBoundary(now time.Time) error {
	if r == nil || terminalState(r.State) {
		return ErrInvalidTransition
	}
	r.applyPendingSteer(now)
	if r.PauseRequested {
		return r.Transition(generated.AssistantRunStatePaused, r.PauseReason, now)
	}
	return nil
}

func (r *Run) AcceptVerification(verdict VerificationVerdict, now time.Time) error {
	if r == nil || r.State != generated.AssistantRunStateVerifying || !verdict.Accepted ||
		len(verdict.Missing) > 0 || len(verdict.Failed) > 0 {
		observeCompletionRejected("verdict")
		return ErrCompletionRejected
	}
	if !r.TaskGraph.AllCompleted() {
		observeCompletionRejected("task_graph")
		return fmt.Errorf("%w: task graph is incomplete", ErrCompletionRejected)
	}
	for _, item := range r.Items {
		if item.Status == generated.AssistantRunItemStatusStarted {
			observeCompletionRejected("active_item")
			return fmt.Errorf(
				"%w: run item %s is still active",
				ErrCompletionRejected,
				item.ItemID,
			)
		}
	}
	return r.Transition(generated.AssistantRunStateCompleted, verdict.DecisionSummary, now)
}

func (r *Run) applyPendingSteer(now time.Time) {
	for _, instruction := range r.PendingSteer {
		r.GoalRevision++
		r.GoalHistory = append(r.GoalHistory, GoalRevision{
			Revision:    r.GoalRevision,
			Instruction: instruction,
			AppliedAt:   now.UTC(),
		})
	}
	if len(r.PendingSteer) > 0 {
		r.PendingSteer = nil
		r.touch(now)
	}
}

func (r *Run) touch(now time.Time) {
	r.Revision++
	r.UpdatedAt = now.UTC()
}

func cloneDefinition(value DefinitionOfDone) DefinitionOfDone {
	value.Constraints = append([]string{}, value.Constraints...)
	value.VerificationRequirements = append([]string{}, value.VerificationRequirements...)
	return value
}
