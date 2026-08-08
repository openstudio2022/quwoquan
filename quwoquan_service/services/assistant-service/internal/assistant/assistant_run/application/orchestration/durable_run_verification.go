package orchestration

import (
	"context"
	"sort"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

func verifyDurableExecutionCompletion(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	result runruntime.ExecutionResult,
) (runruntime.ExecutionResult, error) {
	if result.WaitingState != "" {
		return result, nil
	}
	if _, err := request.VerifyCompletionWithinExecutionBudget(ctx, result); err != nil {
		return result, err
	}
	if err := executionBudgetConsumptionPersistenceError(ctx); err != nil {
		return result, err
	}
	return result, nil
}

func executionCompletedDeviceAction(
	checkpoint *runruntime.Checkpoint,
) (runruntime.DeviceActionExecutionReceipt, bool) {
	if checkpoint == nil {
		return runruntime.DeviceActionExecutionReceipt{}, false
	}
	const prefix = "device_action_completed:"
	completedRefs := map[string]struct{}{}
	for _, summary := range checkpoint.DecisionSummary {
		if strings.HasPrefix(summary, prefix) {
			completedRefs[strings.TrimSpace(strings.TrimPrefix(summary, prefix))] = struct{}{}
		}
	}
	for index := len(checkpoint.DeviceActionReceipts) - 1; index >= 0; index-- {
		receipt := checkpoint.DeviceActionReceipts[index]
		if _, completed := completedRefs[strings.TrimSpace(receipt.IdempotencyKey)]; completed && strings.TrimSpace(receipt.Outcome) == "completed" &&
			strings.TrimSpace(receipt.Capability) != "" {
			return receipt, true
		}
	}
	return runruntime.DeviceActionExecutionReceipt{}, false
}

func collectExecutionEvidenceRefs(
	processes []assistant.AssistantRunVisibleProcess,
) []string {
	unique := map[string]struct{}{}
	for _, process := range processes {
		for _, reference := range process.AcceptedReferences {
			if sourceID := strings.TrimSpace(reference.SourceID); sourceID != "" {
				unique[sourceID] = struct{}{}
			}
		}
	}
	result := make([]string, 0, len(unique))
	for reference := range unique {
		result = append(result, reference)
	}
	sort.Strings(result)
	return result
}

func verificationEvidenceForExecution(
	definition runruntime.DefinitionOfDone,
	completed bool,
	answer string,
	processes []assistant.AssistantRunVisibleProcess,
	evidenceRefs []string,
	availableArtifactRefs []string,
) []runruntime.VerificationEvidence {
	available := map[string]bool{}
	for _, artifactRef := range availableArtifactRefs {
		artifactRef = strings.TrimSpace(artifactRef)
		if artifactRef != "" {
			available[artifactRef] = true
		}
	}
	answerArtifactRef := ""
	for artifactRef := range available {
		if strings.HasPrefix(artifactRef, "assistant_run_item:answer:") {
			answerArtifactRef = artifactRef
			break
		}
	}
	rows := make([]runruntime.VerificationEvidence, 0, len(definition.VerificationRequirements))
	for _, requirement := range definition.VerificationRequirements {
		requirement = strings.TrimSpace(requirement)
		row := runruntime.VerificationEvidence{Requirement: requirement}
		switch requirement {
		case "answer_present":
			row.Passed = completed && strings.TrimSpace(answer) != "" && answerArtifactRef != ""
			if row.Passed {
				row.ArtifactRefs = []string{answerArtifactRef}
				row.Summary = "final answer is persisted as a durable RunItem"
			} else {
				row.Summary = "final answer is absent or execution did not complete"
			}
		case "evidence_present":
			row.ArtifactRefs = append([]string{}, evidenceRefs...)
			row.Passed = completed && len(row.ArtifactRefs) > 0
			row.Summary = "authoritative evidence ledger references are present"
		case "citations_present":
			row.ArtifactRefs = append([]string{}, evidenceRefs...)
			row.Passed = completed && len(row.ArtifactRefs) > 0 &&
				executionHasAcceptedEvidence(processes)
			row.Summary = "accepted citations are linked to durable evidence"
		default:
			row.Summary = "no deterministic verifier is registered for this requirement"
		}
		rows = append(rows, row)
	}
	return rows
}

func executionAnswerArtifactRef(runID string) string {
	return "assistant_run_item:answer:" + strings.TrimSpace(runID)
}

func executionHasAcceptedEvidence(
	processes []assistant.AssistantRunVisibleProcess,
) bool {
	for _, process := range processes {
		if len(process.AcceptedReferences) > 0 || process.AcceptedDocumentCount > 0 {
			return true
		}
	}
	return false
}
