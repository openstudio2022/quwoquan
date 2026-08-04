package runruntime

import (
	"encoding/hex"
	"fmt"
	"math"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
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
	personaID string,
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
	r.PersonaID = strings.TrimSpace(personaID)
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

func (r *Run) BindSessionContinuity(continuity SessionContinuity) error {
	if r == nil || r.SessionContinuity != nil {
		return ErrInvalidRun
	}
	continuity = cloneSessionContinuity(continuity)
	if strings.TrimSpace(continuity.SummaryID) == "" {
		return nil
	}
	if strings.TrimSpace(continuity.Text) == "" ||
		strings.TrimSpace(continuity.FromTurnID) == "" ||
		strings.TrimSpace(continuity.ToTurnID) == "" ||
		continuity.TurnCount <= 0 {
		return ErrInvalidRun
	}
	r.SessionContinuity = &continuity
	return nil
}

// MergeConfirmedSlots advances only the current AssistantRun's explicitly
// confirmed descriptor values. Previous AssistantSession continuity is not an
// input here; terminal compaction is the sole owner of cross-Run merging.
func (r *Run) MergeConfirmedSlots(
	slots assistantmodel.AssistantRunConfirmedSlots,
	now time.Time,
) error {
	if r == nil || terminalState(r.State) {
		return ErrInvalidRun
	}
	merged, err := r.ConfirmedSlots.Merge(slots)
	if err != nil {
		return ErrInvalidRun
	}
	if r.ConfirmedSlots.Equal(merged) {
		return nil
	}
	r.ConfirmedSlots = merged.Clone()
	r.touch(now)
	return nil
}

// ConfirmedSlotSnapshot prevents repository callers, terminal projectors and
// executors from sharing the aggregate's mutable map.
func (r Run) ConfirmedSlotSnapshot() assistantmodel.AssistantRunConfirmedSlots {
	return r.ConfirmedSlots.Clone()
}

func (r *Run) BindSkillPackage(
	packageID string,
	releaseDigest string,
) error {
	if r == nil || strings.TrimSpace(packageID) == "" ||
		!validSkillPackageDigest(strings.TrimSpace(releaseDigest)) ||
		r.SkillPackageID != "" || r.SkillPackageReleaseDigest != "" {
		return ErrInvalidRun
	}
	r.SkillPackageID = strings.TrimSpace(packageID)
	r.SkillPackageReleaseDigest = strings.TrimSpace(releaseDigest)
	return nil
}

func (r *Run) BindFeedbackContext(
	snapshot assistantmodel.AssistantFeedbackContextSnapshot,
) error {
	if r == nil || strings.TrimSpace(r.FeedbackContextSnapshot.Decision) != "" ||
		!validFeedbackContextSnapshot(snapshot) ||
		!validFeedbackContextAgainstPolicy(
			snapshot,
			r.FrozenPolicySelection.LearningContextPolicy,
		) {
		return ErrInvalidRun
	}
	r.FeedbackContextSnapshot = snapshot.Clone()
	return nil
}

func validFeedbackContextSnapshot(
	snapshot assistantmodel.AssistantFeedbackContextSnapshot,
) bool {
	decision := strings.TrimSpace(snapshot.Decision)
	if !assistantmodel.IsKnownAssistantFeedbackContextDecision(decision) ||
		snapshot.WindowDays < 0 || snapshot.WindowDays > 90 {
		return false
	}
	if decision == "injected" {
		return strings.TrimSpace(snapshot.ConsentID) != "" &&
			!snapshot.ConsentGrantedAt.IsZero() &&
			validBareSHA256(snapshot.DefinitionDigest) &&
			snapshot.SourceWatermarkSequence > 0 &&
			snapshot.WindowDays > 0 && snapshot.FeedbackSampleCount > 0 &&
			validFeedbackAggregates(snapshot)
	}
	return strings.TrimSpace(snapshot.ConsentID) == "" &&
		snapshot.ConsentGrantedAt.IsZero() &&
		strings.TrimSpace(snapshot.DefinitionDigest) == "" &&
		snapshot.SourceWatermarkSequence == 0 &&
		snapshot.FeedbackSampleCount == 0 &&
		snapshot.PositiveFeedbackCount == 0 &&
		snapshot.NegativeFeedbackCount == 0 &&
		snapshot.TextFeedbackCount == 0 &&
		len(snapshot.Metrics) == 0 && len(snapshot.Reasons) == 0 &&
		!snapshot.SnapshotTrainingEligible
}

func validFeedbackAggregates(
	snapshot assistantmodel.AssistantFeedbackContextSnapshot,
) bool {
	if snapshot.PositiveFeedbackCount < 0 ||
		snapshot.NegativeFeedbackCount < 0 ||
		snapshot.TextFeedbackCount < 0 ||
		snapshot.PositiveFeedbackCount > snapshot.FeedbackSampleCount ||
		snapshot.NegativeFeedbackCount > snapshot.FeedbackSampleCount ||
		snapshot.TextFeedbackCount > snapshot.FeedbackSampleCount {
		return false
	}
	metricIDs := make(map[string]struct{}, len(snapshot.Metrics))
	for _, metric := range snapshot.Metrics {
		metricID := strings.TrimSpace(metric.MetricID)
		if metricID == "" || metric.SampleCount <= 0 ||
			metric.SampleCount > snapshot.FeedbackSampleCount ||
			math.IsNaN(metric.Average) || math.IsInf(metric.Average, 0) ||
			math.IsNaN(metric.Latest) || math.IsInf(metric.Latest, 0) {
			return false
		}
		if _, exists := metricIDs[metricID]; exists {
			return false
		}
		metricIDs[metricID] = struct{}{}
	}
	reasonCodes := make(map[string]struct{}, len(snapshot.Reasons))
	for _, reason := range snapshot.Reasons {
		reasonCode := strings.TrimSpace(reason.ReasonCode)
		if reasonCode == "" || reason.Count <= 0 ||
			reason.Count > snapshot.FeedbackSampleCount {
			return false
		}
		if _, exists := reasonCodes[reasonCode]; exists {
			return false
		}
		reasonCodes[reasonCode] = struct{}{}
	}
	return true
}

func validFeedbackContextAgainstPolicy(
	snapshot assistantmodel.AssistantFeedbackContextSnapshot,
	policy FrozenLearningContextPolicy,
) bool {
	if snapshot.WindowDays != policy.WindowDays {
		return false
	}
	if snapshot.Decision != "injected" {
		return true
	}
	if !policy.Enabled || policy.MinimumFeedbackSamples < 1 ||
		snapshot.FeedbackSampleCount < int64(policy.MinimumFeedbackSamples) ||
		snapshot.SnapshotTrainingEligible != policy.SnapshotTrainingEligible {
		return false
	}
	allowedSignals := feedbackValueSet(policy.AllowedSignals)
	if _, allowed := allowedSignals["feedback_counts"]; !allowed &&
		(snapshot.PositiveFeedbackCount != 0 || snapshot.NegativeFeedbackCount != 0 ||
			snapshot.TextFeedbackCount != 0) {
		return false
	}
	if _, allowed := allowedSignals["metric_summaries"]; !allowed && len(snapshot.Metrics) > 0 {
		return false
	}
	allowedMetrics := feedbackValueSet(policy.AllowedMetricIDs)
	for _, metric := range snapshot.Metrics {
		if _, allowed := allowedMetrics[strings.TrimSpace(metric.MetricID)]; !allowed {
			return false
		}
	}
	if _, allowed := allowedSignals["top_reason_codes"]; !allowed && len(snapshot.Reasons) > 0 {
		return false
	}
	allowedReasons := feedbackValueSet(policy.AllowedReasonCodes)
	for _, reason := range snapshot.Reasons {
		if _, allowed := allowedReasons[strings.TrimSpace(reason.ReasonCode)]; !allowed {
			return false
		}
	}
	return true
}

func feedbackValueSet(values []string) map[string]struct{} {
	result := make(map[string]struct{}, len(values))
	for _, value := range values {
		if value = strings.TrimSpace(value); value != "" {
			result[value] = struct{}{}
		}
	}
	return result
}

func validBareSHA256(value string) bool {
	value = strings.TrimSpace(value)
	if len(value) != 64 || value != strings.ToLower(value) {
		return false
	}
	_, err := hex.DecodeString(value)
	return err == nil
}

func (r *Run) SetTerminalSnapshot(
	snapshot assistantmodel.AssistantRunTerminalSnapshot,
	now time.Time,
) error {
	if r == nil || !terminalState(r.State) || !validTerminalSnapshot(r.State, snapshot) {
		return ErrInvalidRun
	}
	r.TerminalSnapshot = snapshot.Clone()
	r.touch(now)
	return nil
}

func validTerminalSnapshot(
	state generated.AssistantRunState,
	snapshot assistantmodel.AssistantRunTerminalSnapshot,
) bool {
	if state == generated.AssistantRunStateCompleted &&
		strings.TrimSpace(snapshot.AnswerText) == "" {
		return false
	}
	if state == generated.AssistantRunStateFailed && snapshot.Failure == nil {
		return false
	}
	if snapshot.Failure != nil &&
		(strings.TrimSpace(snapshot.Failure.Code) == "" ||
			strings.TrimSpace(snapshot.Failure.Origin) == "" ||
			strings.TrimSpace(snapshot.Failure.Kind) == "" ||
			strings.TrimSpace(snapshot.Failure.Nature) == "") {
		return false
	}
	if snapshot.SelectedPolicyRef != nil &&
		(strings.TrimSpace(snapshot.SelectedPolicyRef.PolicyID) == "" ||
			strings.TrimSpace(snapshot.SelectedPolicyRef.ReleaseDigest) == "" ||
			strings.TrimSpace(snapshot.SelectedPolicyRef.Cohort) == "") {
		return false
	}
	return true
}

func terminalSelectedPolicyRef(
	selection FrozenPolicySelection,
) *assistantmodel.AssistantSelectedPolicyRef {
	if strings.TrimSpace(selection.PolicyID) == "" {
		return nil
	}
	return &assistantmodel.AssistantSelectedPolicyRef{
		PolicyID:      strings.TrimSpace(selection.PolicyID),
		ReleaseDigest: strings.TrimSpace(selection.ReleaseDigest),
		Cohort:        strings.TrimSpace(selection.Cohort),
	}
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

// EffectiveGoal returns the immutable starting goal plus every steering
// instruction that has crossed a durable safe boundary. The original input is
// retained for audit, while execution always receives the cumulative current
// goal instead of silently ignoring GoalHistory.
func (r Run) EffectiveGoal() string {
	base := strings.TrimSpace(r.InputText)
	var revisions []GoalRevision
	for _, revision := range r.GoalHistory {
		if strings.TrimSpace(revision.Instruction) == "" {
			continue
		}
		revisions = append(revisions, revision)
	}
	if len(revisions) == 0 {
		return base
	}
	var goal strings.Builder
	goal.WriteString(base)
	goal.WriteString("\n\n已生效的后续约束：")
	for _, revision := range revisions {
		goal.WriteString("\n- 修订 ")
		goal.WriteString(fmt.Sprint(revision.Revision))
		goal.WriteString("：")
		goal.WriteString(strings.TrimSpace(revision.Instruction))
	}
	return goal.String()
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

func cloneSessionContinuity(value SessionContinuity) SessionContinuity {
	value.ConfirmedFacts = append([]string(nil), value.ConfirmedFacts...)
	value.PendingItems = append([]string(nil), value.PendingItems...)
	if value.ConfirmedSlots != nil {
		value.ConfirmedSlots = cloneStringMap(value.ConfirmedSlots)
	}
	return value
}

func cloneSessionContinuityPtr(value *SessionContinuity) *SessionContinuity {
	if value == nil {
		return nil
	}
	cloned := cloneSessionContinuity(*value)
	return &cloned
}

func cloneStringMap(value map[string]string) map[string]string {
	if value == nil {
		return nil
	}
	cloned := make(map[string]string, len(value))
	for key, item := range value {
		cloned[key] = item
	}
	return cloned
}
