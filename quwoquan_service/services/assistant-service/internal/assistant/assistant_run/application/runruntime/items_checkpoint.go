package runruntime

import (
	"sort"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

func (r *Run) BeginItem(
	itemID string,
	kind generated.AssistantRunItemKind,
	taskID string,
	summary string,
	payload map[string]any,
	now time.Time,
) error {
	if r == nil || terminalState(r.State) || strings.TrimSpace(itemID) == "" || kind == "" {
		return ErrItemStateConflict
	}
	if unsafeReasoningPayload(payload) {
		return ErrUnsafePayload
	}
	for _, item := range r.Items {
		if item.ItemID == itemID {
			return ErrItemStateConflict
		}
	}
	r.Items = append(r.Items, RunItem{
		ItemID:    itemID,
		Kind:      kind,
		Status:    generated.AssistantRunItemStatusStarted,
		Sequence:  int64(len(r.Items) + 1),
		TaskID:    strings.TrimSpace(taskID),
		Summary:   strings.TrimSpace(summary),
		Payload:   cloneMap(payload),
		StartedAt: now.UTC(),
	})
	r.touch(now)
	return nil
}

func (r *Run) CompleteItem(
	itemID string,
	status generated.AssistantRunItemStatus,
	artifactRefs []string,
	summary string,
	now time.Time,
) error {
	if status != generated.AssistantRunItemStatusCompleted &&
		status != generated.AssistantRunItemStatusFailed &&
		status != generated.AssistantRunItemStatusCancelled {
		return ErrItemStateConflict
	}
	for index := range r.Items {
		if r.Items[index].ItemID != itemID {
			continue
		}
		if r.Items[index].Status != generated.AssistantRunItemStatusStarted {
			return ErrItemStateConflict
		}
		r.Items[index].Status = status
		r.Items[index].ArtifactRefs = append([]string{}, artifactRefs...)
		if strings.TrimSpace(summary) != "" {
			r.Items[index].Summary = strings.TrimSpace(summary)
		}
		r.Items[index].CompletedAt = now.UTC()
		r.touch(now)
		observeItemClosure(r.Items[index].Kind.WireName(), status.WireName())
		return nil
	}
	return ErrItemStateConflict
}

func (r *Run) CancelActiveWork(reason string, now time.Time) {
	if r == nil {
		return
	}
	reason = strings.TrimSpace(reason)
	changed := false
	for index := range r.Items {
		if r.Items[index].Status != generated.AssistantRunItemStatusStarted {
			continue
		}
		r.Items[index].Status = generated.AssistantRunItemStatusCancelled
		r.Items[index].Summary = reason
		r.Items[index].CompletedAt = now.UTC()
		observeItemClosure(
			r.Items[index].Kind.WireName(),
			generated.AssistantRunItemStatusCancelled.WireName(),
		)
		changed = true
	}
	for index := range r.TaskGraph.Tasks {
		switch r.TaskGraph.Tasks[index].Status {
		case generated.AssistantTaskStatusPending,
			generated.AssistantTaskStatusReady,
			generated.AssistantTaskStatusRunning:
			r.TaskGraph.Tasks[index].Status = generated.AssistantTaskStatusCancelled
			r.TaskGraph.Tasks[index].BlockReason = reason
			changed = true
		}
	}
	if changed {
		r.TaskGraph.GraphRevision++
		r.touch(now)
	}
}

func (r *Run) CreateCheckpoint(
	checkpointID string,
	goalSummary string,
	decisionSummary []string,
	pendingApprovalRef string,
	remainingBudget map[string]int64,
	now time.Time,
) (Checkpoint, error) {
	if r == nil || terminalState(r.State) || strings.TrimSpace(checkpointID) == "" {
		return Checkpoint{}, ErrInvalidRun
	}
	var deviceActionReceipts []DeviceActionExecutionReceipt
	if r.Checkpoint != nil {
		deviceActionReceipts = append(
			[]DeviceActionExecutionReceipt{},
			r.Checkpoint.DeviceActionReceipts...,
		)
	}
	checkpoint := Checkpoint{
		CheckpointID:         checkpointID,
		Revision:             r.Revision + 1,
		GoalSummary:          strings.TrimSpace(goalSummary),
		DecisionSummary:      append([]string{}, decisionSummary...),
		PendingApprovalRef:   strings.TrimSpace(pendingApprovalRef),
		DeviceActionReceipts: deviceActionReceipts,
		RemainingBudget:      cloneInt64Map(remainingBudget),
		CreatedAt:            now.UTC(),
	}
	for _, task := range r.TaskGraph.Tasks {
		if task.Status == generated.AssistantTaskStatusCompleted {
			checkpoint.CompletedTaskIDs = append(checkpoint.CompletedTaskIDs, task.TaskID)
		} else if task.Status != generated.AssistantTaskStatusCancelled {
			checkpoint.OpenTaskIDs = append(checkpoint.OpenTaskIDs, task.TaskID)
		}
		checkpoint.EvidenceRefs = append(checkpoint.EvidenceRefs, task.Verification.EvidenceRefs...)
	}
	for _, item := range r.Items {
		checkpoint.EvidenceRefs = append(checkpoint.EvidenceRefs, item.ArtifactRefs...)
	}
	checkpoint.EvidenceRefs = uniqueSorted(checkpoint.EvidenceRefs)
	r.Checkpoint = &checkpoint
	r.touch(now)
	checkpoint.Revision = r.Revision
	r.Checkpoint.Revision = r.Revision
	return checkpoint, nil
}

func cloneMap(value map[string]any) map[string]any {
	if value == nil {
		return nil
	}
	result := make(map[string]any, len(value))
	for key, item := range value {
		result[key] = item
	}
	return result
}

func cloneInt64Map(value map[string]int64) map[string]int64 {
	result := make(map[string]int64, len(value))
	for key, item := range value {
		result[key] = item
	}
	return result
}

func uniqueSorted(values []string) []string {
	seen := map[string]struct{}{}
	for _, value := range values {
		if value = strings.TrimSpace(value); value != "" {
			seen[value] = struct{}{}
		}
	}
	result := make([]string, 0, len(seen))
	for value := range seen {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func unsafeReasoningPayload(payload map[string]any) bool {
	for key, value := range payload {
		normalized := strings.ToLower(strings.ReplaceAll(strings.ReplaceAll(key, "_", ""), "-", ""))
		switch normalized {
		case "chainofthought", "reasoningtrace", "internalthought", "scratchpad", "hiddenreasoning":
			return true
		}
		switch nested := value.(type) {
		case map[string]any:
			if unsafeReasoningPayload(nested) {
				return true
			}
		case []any:
			for _, item := range nested {
				if child, ok := item.(map[string]any); ok && unsafeReasoningPayload(child) {
					return true
				}
			}
		}
	}
	return false
}
