package runruntime

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

const verificationBlockReasonPrefix = "verification_rejected:"

func (w *DurableWorker) persistVerificationVerdict(
	ctx context.Context,
	current Run,
	verdict VerificationVerdict,
) (Run, VerificationVerdict, bool, error) {
	completionBoundary := completionBoundaryFactsFor(current)
	itemID, taskAttempt, err := verificationItemIdentity(current)
	if err != nil {
		return Run{}, VerificationVerdict{}, false, err
	}
	if persisted, found, err := verificationVerdictForItem(
		current,
		itemID,
		taskAttempt,
	); found || err != nil {
		return current, persisted, false, err
	}
	artifactRefs := []string{}
	for _, item := range verdict.Evidence {
		artifactRefs = append(artifactRefs, item.ArtifactRefs...)
	}
	authoritative := verdict
	completionReplanned := false
	pauseWon := false
	committed, err := w.commitMutation(ctx, current.RunID, "process_commit", func(
		run *Run,
		now time.Time,
	) error {
		replanned, boundaryErr := guardCompletionBoundary(
			run,
			completionBoundary,
			now,
		)
		if boundaryErr != nil {
			return boundaryErr
		}
		if replanned {
			completionReplanned = true
			return nil
		}
		if run.PauseRequested {
			pauseWon = true
			return nil
		}
		if persisted, found, decodeErr := verificationVerdictForItem(
			*run,
			itemID,
			taskAttempt,
		); found || decodeErr != nil {
			authoritative = persisted
			return decodeErr
		}
		if err := run.BeginItem(
			itemID,
			generated.AssistantRunItemKindEvidence,
			"task_root",
			verdict.DecisionSummary,
			verificationVerdictJournalPayload(*run, verdict, taskAttempt),
			now,
		); err != nil {
			return err
		}
		return run.CompleteItem(
			itemID,
			generated.AssistantRunItemStatusCompleted,
			uniqueSorted(artifactRefs),
			verdict.DecisionSummary,
			now,
		)
	})
	if err != nil {
		return Run{}, VerificationVerdict{}, false, err
	}
	if completionReplanned {
		if committed.PauseRequested {
			return committed, VerificationVerdict{}, true, nil
		}
		return Run{}, VerificationVerdict{}, false, ErrExecutionReplanned
	}
	if pauseWon {
		return committed, VerificationVerdict{}, true, nil
	}
	return committed, authoritative, false, nil
}

func verificationItemIdentity(run Run) (string, int, error) {
	rootIndex := run.TaskGraph.taskIndex("task_root")
	if rootIndex < 0 || run.TaskGraph.Tasks[rootIndex].Attempt <= 0 {
		return "", 0, ErrInvalidTaskGraph
	}
	attempt := run.TaskGraph.Tasks[rootIndex].Attempt
	return "verification:" + run.RunID + ":task:task_root:attempt:" +
		fmt.Sprint(attempt), attempt, nil
}

func verificationVerdictForCurrentAttempt(
	run Run,
) (VerificationVerdict, bool, error) {
	itemID, taskAttempt, err := verificationItemIdentity(run)
	if err != nil {
		return VerificationVerdict{}, false, err
	}
	return verificationVerdictForItem(run, itemID, taskAttempt)
}

func verificationVerdictForItem(
	run Run,
	itemID string,
	taskAttempt int,
) (VerificationVerdict, bool, error) {
	for _, item := range run.Items {
		if item.ItemID != itemID {
			continue
		}
		if item.Kind != generated.AssistantRunItemKindEvidence ||
			item.Status != generated.AssistantRunItemStatusCompleted ||
			item.TaskID != "task_root" {
			return VerificationVerdict{}, true, ErrJournalCorrupt
		}
		verdict, err := verificationVerdictFromJournalPayload(
			run,
			item.Payload,
			taskAttempt,
		)
		return verdict, true, err
	}
	return VerificationVerdict{}, false, nil
}

func verificationVerdictJournalPayload(
	run Run,
	verdict VerificationVerdict,
	taskAttempt int,
) map[string]any {
	payload := verificationVerdictPayload(verdict)
	payload["taskAttempt"] = taskAttempt
	payload["goalRevision"] = run.GoalRevision
	payload["protectedRunFactsDigest"] = ProtectedRunFactsDigest(run)
	payload["failureFingerprint"] = verificationFailureFingerprint(verdict)
	return payload
}

func verificationVerdictFromJournalPayload(
	run Run,
	payload map[string]any,
	wantTaskAttempt int,
) (VerificationVerdict, error) {
	accepted, found := payload["accepted"].(bool)
	protectedFactsDigest, protectedFactsFound :=
		payload["protectedRunFactsDigest"].(string)
	if !goalHistoryIsContinuous(run.GoalHistory, run.GoalRevision) ||
		!found || integerPayloadValue(payload["taskAttempt"]) != wantTaskAttempt ||
		integerPayloadValue(payload["goalRevision"]) != int(run.GoalRevision) ||
		!protectedFactsFound || !validCompletionDigest(protectedFactsDigest) ||
		protectedFactsDigest != ProtectedRunFactsDigest(run) {
		return VerificationVerdict{}, ErrJournalCorrupt
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		return VerificationVerdict{}, ErrJournalCorrupt
	}
	var wire struct {
		Evidence []struct {
			Requirement   string   `json:"requirement"`
			VerifierID    string   `json:"verifierId"`
			Passed        bool     `json:"passed"`
			ArtifactRefs  []string `json:"artifactRefs"`
			Summary       string   `json:"summary"`
			FixSuggestion string   `json:"fixSuggestion"`
		} `json:"evidence"`
		Missing         []string `json:"missing"`
		Failed          []string `json:"failed"`
		DecisionSummary string   `json:"decisionSummary"`
	}
	if err := json.Unmarshal(raw, &wire); err != nil {
		return VerificationVerdict{}, ErrJournalCorrupt
	}
	verdict := VerificationVerdict{
		Accepted: accepted, Missing: append([]string{}, wire.Missing...),
		Failed:          append([]string{}, wire.Failed...),
		DecisionSummary: strings.TrimSpace(wire.DecisionSummary),
		Evidence:        make([]VerificationEvidence, 0, len(wire.Evidence)),
	}
	for _, row := range wire.Evidence {
		verdict.Evidence = append(verdict.Evidence, VerificationEvidence{
			Requirement: strings.TrimSpace(row.Requirement), VerifierID: strings.TrimSpace(row.VerifierID),
			Passed: row.Passed, ArtifactRefs: append([]string{}, row.ArtifactRefs...),
			Summary: strings.TrimSpace(row.Summary), FixSuggestion: strings.TrimSpace(row.FixSuggestion),
		})
	}
	wantFingerprint, ok := payload["failureFingerprint"].(string)
	if !ok || !validVerificationFingerprint(wantFingerprint) ||
		verificationFailureFingerprint(verdict) != wantFingerprint {
		return VerificationVerdict{}, ErrJournalCorrupt
	}
	return verdict, nil
}

func integerPayloadValue(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case int32:
		return int(typed)
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	default:
		return 0
	}
}

func verificationFailureFingerprint(verdict VerificationVerdict) string {
	type evidenceIdentity struct {
		VerifierID  string `json:"verifierId"`
		Requirement string `json:"requirement"`
		Passed      bool   `json:"passed"`
	}
	rows := make([]evidenceIdentity, 0, len(verdict.Evidence))
	for _, row := range verdict.Evidence {
		rows = append(rows, evidenceIdentity{
			VerifierID:  strings.TrimSpace(row.VerifierID),
			Requirement: strings.TrimSpace(row.Requirement),
			Passed:      row.Passed,
		})
	}
	sort.Slice(rows, func(left, right int) bool {
		if rows[left].VerifierID != rows[right].VerifierID {
			return rows[left].VerifierID < rows[right].VerifierID
		}
		if rows[left].Requirement != rows[right].Requirement {
			return rows[left].Requirement < rows[right].Requirement
		}
		return !rows[left].Passed && rows[right].Passed
	})
	encoded, _ := json.Marshal(struct {
		Evidence []evidenceIdentity `json:"evidence"`
		Missing  []string           `json:"missing"`
		Failed   []string           `json:"failed"`
	}{rows, uniqueSorted(verdict.Missing), uniqueSorted(verdict.Failed)})
	digest := sha256.Sum256(encoded)
	return hex.EncodeToString(digest[:])
}

func validVerificationFingerprint(value string) bool {
	if len(value) != sha256.Size*2 || strings.ToLower(value) != value {
		return false
	}
	decoded, err := hex.DecodeString(value)
	return err == nil && len(decoded) == sha256.Size
}

func verificationVerdictPayload(verdict VerificationVerdict) map[string]any {
	evidence := make([]map[string]any, 0, len(verdict.Evidence))
	for _, item := range verdict.Evidence {
		evidence = append(evidence, map[string]any{
			"requirement": item.Requirement, "verifierId": item.VerifierID,
			"passed": item.Passed, "artifactRefs": append([]string{}, item.ArtifactRefs...),
			"summary": item.Summary, "fixSuggestion": item.FixSuggestion,
		})
	}
	return map[string]any{
		"accepted": verdict.Accepted, "evidence": evidence,
		"missing":         append([]string{}, verdict.Missing...),
		"failed":          append([]string{}, verdict.Failed...),
		"decisionSummary": verdict.DecisionSummary,
	}
}

func (w *DurableWorker) tryVerificationRepair(
	ctx context.Context,
	current Run,
	verdict VerificationVerdict,
) (Run, bool, bool, string, error) {
	if current.PauseRequested {
		return current, false, true, "", nil
	}
	rootIndex := current.TaskGraph.taskIndex("task_root")
	if rootIndex < 0 {
		return current, false, false, "verification_task_graph_invalid", ErrInvalidTaskGraph
	}
	root := current.TaskGraph.Tasks[rootIndex]
	if current.State != generated.AssistantRunStateExecuting ||
		root.Status != generated.AssistantTaskStatusRunning || root.Attempt <= 0 {
		return current, false, false, "verification_task_graph_invalid", ErrInvalidTaskGraph
	}
	fingerprint := verificationFailureFingerprint(verdict)
	previousFingerprint := strings.TrimPrefix(
		strings.TrimSpace(root.BlockReason),
		verificationBlockReasonPrefix,
	)
	if strings.HasPrefix(root.BlockReason, verificationBlockReasonPrefix) &&
		previousFingerprint == fingerprint {
		return current, false, false, "verification_no_progress", nil
	}
	if root.Attempt-1 >= current.ReasoningPolicy.StopRules.MaxVerificationRepairs {
		return current, false, false, "verification_repair_exhausted", nil
	}
	instruction := verificationRepairInstruction(verdict)
	if instruction == "" {
		return current, false, false, "verification_fix_unavailable", nil
	}
	now := w.now().UTC()
	deadline := root.Budget.Deadline
	if deadline.IsZero() {
		deadline = current.CreatedAt.UTC().Add(current.ReasoningPolicy.Budget.MaxDuration)
	}
	remaining := remainingBudget(current)
	if !now.Before(deadline) || remaining["tokens"] <= 0 || remaining["costUnits"] <= 0 {
		return current, false, false, "verification_budget_exhausted", nil
	}
	availableArtifactRefs := []string{}
	for _, row := range verdict.Evidence {
		availableArtifactRefs = append(availableArtifactRefs, row.ArtifactRefs...)
	}
	expectedAttempt := root.Attempt
	expectedProtectedFactsDigest := ProtectedRunFactsDigest(current)
	completionBoundary := completionBoundaryFactsFor(current)
	completionReplanned := false
	pauseWon := false
	committed, err := w.commitMutation(ctx, current.RunID, "task_graph_patch", func(
		run *Run,
		now time.Time,
	) error {
		replanned, boundaryErr := guardCompletionBoundary(
			run,
			completionBoundary,
			now,
		)
		if boundaryErr != nil {
			return boundaryErr
		}
		if replanned {
			completionReplanned = true
			return nil
		}
		if run.PauseRequested {
			pauseWon = true
			return nil
		}
		index := run.TaskGraph.taskIndex("task_root")
		if index < 0 || run.TaskGraph.Tasks[index].Attempt != expectedAttempt ||
			run.TaskGraph.Tasks[index].Status != generated.AssistantTaskStatusRunning ||
			ProtectedRunFactsDigest(*run) != expectedProtectedFactsDigest {
			return ErrRevisionConflict
		}
		run.TaskGraph.Tasks[index].Verification = TaskVerification{
			Requirements: append([]string{}, run.DefinitionOfDone.VerificationRequirements...),
			EvidenceRefs: uniqueSorted(availableArtifactRefs), Passed: false, Summary: instruction,
		}
		if err := run.TaskGraph.Fail(
			"task_root", verificationBlockReasonPrefix+fingerprint, true,
		); err != nil {
			return err
		}
		if err := run.TaskGraph.Start("task_root"); err != nil {
			return err
		}
		if err := run.Transition(generated.AssistantRunStateObserving, "", now); err != nil {
			return err
		}
		if err := run.Transition(generated.AssistantRunStateReflecting, "", now); err != nil {
			return err
		}
		return run.Transition(generated.AssistantRunStateExecuting, "", now)
	})
	if err != nil {
		return current, false, false, "", err
	}
	if completionReplanned {
		if committed.PauseRequested {
			return committed, false, true, "", nil
		}
		return committed, true, false, "", nil
	}
	if pauseWon {
		return committed, false, true, "", nil
	}
	return committed, true, false, "", nil
}

func verificationRepairInstruction(verdict VerificationVerdict) string {
	suggestions := []string{}
	for _, row := range verdict.Evidence {
		if !row.Passed && strings.TrimSpace(row.FixSuggestion) != "" {
			suggestions = append(suggestions, strings.TrimSpace(row.FixSuggestion))
		}
	}
	suggestions = uniqueSorted(suggestions)
	if len(suggestions) == 0 {
		return ""
	}
	return boundedVerificationText(strings.Join(suggestions, "; "), 1024)
}
