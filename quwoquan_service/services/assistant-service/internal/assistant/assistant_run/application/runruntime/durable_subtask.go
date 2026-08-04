package runruntime

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

const maxDurableSubtaskPayloadBytes = 256 << 10

type DurableSubtaskClaimRequest struct {
	TaskID      string
	OwnerAgent  string
	InputDigest string
}

type DurableSubtaskClaim struct {
	RunID          string
	TaskID         string
	ClaimID        string
	ClaimOwner     string
	InputDigest    string
	FencingToken   int64
	Attempt        int
	IdempotencyKey string
	LeaseExpiresAt time.Time
}

type DurableSubtaskResult struct {
	Outcome      string
	Summary      string
	FailureCode  string
	Payload      map[string]any
	ArtifactRefs []string
}

type DurableSubtaskTerminalReceipt struct {
	ReceiptRef        string
	RunID             string
	TaskID            string
	InputDigest       string
	Outcome           string
	Attempt           int
	FencingToken      int64
	IdempotencyKey    string
	Summary           string
	FailureCode       string
	ResultArtifactRef string
	Payload           map[string]any
	CompletedAt       time.Time
}

func (r *Run) ClaimDurableSubtask(
	request DurableSubtaskClaimRequest,
	claimOwner string,
	leaseTTL time.Duration,
	now time.Time,
) (DurableSubtaskClaim, *DurableSubtaskTerminalReceipt, error) {
	if r == nil || terminalState(r.State) || leaseTTL <= 0 ||
		!validDurableSubtaskClaimRequest(request) ||
		strings.TrimSpace(claimOwner) == "" {
		return DurableSubtaskClaim{}, nil, ErrInvalidRun
	}
	now = now.UTC()
	index := r.TaskGraph.taskIndex(strings.TrimSpace(request.TaskID))
	if index < 0 {
		return DurableSubtaskClaim{}, nil, ErrTaskNotReady
	}
	task := &r.TaskGraph.Tasks[index]
	if task.OwnerAgent != strings.TrimSpace(request.OwnerAgent) {
		return DurableSubtaskClaim{}, nil, ErrRevisionConflict
	}
	idempotencyKey := durableSubtaskIdempotencyKey(
		r.RunID,
		r.GoalRevision,
		request,
	)
	if task.IdempotencyKey != "" && task.IdempotencyKey != idempotencyKey {
		return DurableSubtaskClaim{}, nil, ErrRevisionConflict
	}
	if task.TerminalReceiptRef != "" {
		receipt, err := r.durableSubtaskTerminalReceipt(*task)
		if err != nil {
			return DurableSubtaskClaim{}, nil, err
		}
		if receipt.InputDigest != request.InputDigest ||
			receipt.IdempotencyKey != idempotencyKey {
			return DurableSubtaskClaim{}, nil, ErrRevisionConflict
		}
		claim := durableSubtaskClaimFromTask(r.RunID, request.InputDigest, *task)
		return claim, &receipt, nil
	}
	switch task.Status {
	case generated.AssistantTaskStatusReady:
		if err := r.TaskGraph.Start(task.TaskID); err != nil {
			return DurableSubtaskClaim{}, nil, err
		}
		index = r.TaskGraph.taskIndex(task.TaskID)
		task = &r.TaskGraph.Tasks[index]
	case generated.AssistantTaskStatusRunning:
		if task.ClaimID != "" {
			if task.LeaseExpiresAt.IsZero() || !now.Before(task.LeaseExpiresAt) {
				task.Attempt++
				r.TaskGraph.GraphRevision++
			} else {
				return DurableSubtaskClaim{}, nil, ErrLeaseConflict
			}
		} else if task.Attempt <= 0 {
			task.Attempt = 1
			r.TaskGraph.GraphRevision++
		}
	case generated.AssistantTaskStatusCancelled:
		return DurableSubtaskClaim{}, nil, ErrExecutionCancelled
	case generated.AssistantTaskStatusCompleted,
		generated.AssistantTaskStatusFailed:
		return DurableSubtaskClaim{}, nil, ErrJournalCorrupt
	default:
		return DurableSubtaskClaim{}, nil, ErrTaskNotReady
	}
	task.FencingToken++
	task.ClaimOwner = strings.TrimSpace(claimOwner)
	task.ClaimID = durableSubtaskClaimID(
		r.RunID,
		task.TaskID,
		task.ClaimOwner,
		task.FencingToken,
		now,
	)
	task.HeartbeatAt = now
	task.LeaseExpiresAt = now.Add(leaseTTL)
	task.IdempotencyKey = idempotencyKey
	task.ResultArtifactRef = ""
	task.TerminalReceiptRef = ""
	task.BlockReason = ""
	r.TaskGraph.GraphRevision++
	r.touch(now)
	return durableSubtaskClaimFromTask(r.RunID, request.InputDigest, *task), nil, nil
}

func (r *Run) HeartbeatDurableSubtask(
	claim DurableSubtaskClaim,
	leaseTTL time.Duration,
	now time.Time,
) (DurableSubtaskClaim, error) {
	if r == nil || terminalState(r.State) || leaseTTL <= 0 {
		return DurableSubtaskClaim{}, ErrExecutionFenced
	}
	now = now.UTC()
	index := r.TaskGraph.taskIndex(strings.TrimSpace(claim.TaskID))
	if index < 0 {
		return DurableSubtaskClaim{}, ErrExecutionFenced
	}
	task := &r.TaskGraph.Tasks[index]
	if task.Status == generated.AssistantTaskStatusCancelled {
		return DurableSubtaskClaim{}, ErrExecutionCancelled
	}
	if task.Status != generated.AssistantTaskStatusRunning ||
		!sameDurableSubtaskClaim(r.RunID, r.GoalRevision, *task, claim) ||
		task.LeaseExpiresAt.IsZero() || !now.Before(task.LeaseExpiresAt) {
		return DurableSubtaskClaim{}, ErrExecutionFenced
	}
	task.HeartbeatAt = now
	task.LeaseExpiresAt = now.Add(leaseTTL)
	r.TaskGraph.GraphRevision++
	r.touch(now)
	claim.LeaseExpiresAt = task.LeaseExpiresAt
	return claim, nil
}

func (r *Run) FinishDurableSubtask(
	claim DurableSubtaskClaim,
	result DurableSubtaskResult,
	now time.Time,
) (DurableSubtaskTerminalReceipt, error) {
	if r == nil || terminalState(r.State) {
		return DurableSubtaskTerminalReceipt{}, ErrExecutionFenced
	}
	now = now.UTC()
	index := r.TaskGraph.taskIndex(strings.TrimSpace(claim.TaskID))
	if index < 0 {
		return DurableSubtaskTerminalReceipt{}, ErrExecutionFenced
	}
	task := &r.TaskGraph.Tasks[index]
	if task.TerminalReceiptRef != "" {
		receipt, err := r.durableSubtaskTerminalReceipt(*task)
		if err != nil {
			return DurableSubtaskTerminalReceipt{}, err
		}
		if receipt.InputDigest != claim.InputDigest ||
			receipt.IdempotencyKey != claim.IdempotencyKey {
			return DurableSubtaskTerminalReceipt{}, ErrRevisionConflict
		}
		return receipt, nil
	}
	if task.Status == generated.AssistantTaskStatusCancelled {
		return DurableSubtaskTerminalReceipt{}, ErrExecutionCancelled
	}
	if task.Status != generated.AssistantTaskStatusRunning ||
		!sameDurableSubtaskClaim(r.RunID, r.GoalRevision, *task, claim) ||
		task.LeaseExpiresAt.IsZero() || !now.Before(task.LeaseExpiresAt) {
		return DurableSubtaskTerminalReceipt{}, ErrExecutionFenced
	}
	encodedResult, normalized, err := encodeDurableSubtaskResult(result)
	if err != nil {
		return DurableSubtaskTerminalReceipt{}, err
	}
	itemID := durableSubtaskTerminalItemID(claim.IdempotencyKey)
	resultArtifactRef := "assistant_run_item:" + itemID
	payload := map[string]any{
		"receiptType":       "durable_subtask_terminal",
		"inputDigest":       claim.InputDigest,
		"outcome":           normalized.Outcome,
		"attempt":           claim.Attempt,
		"fencingToken":      claim.FencingToken,
		"idempotencyKey":    claim.IdempotencyKey,
		"failureCode":       normalized.FailureCode,
		"resultPayloadJson": encodedResult,
	}
	if err := r.BeginItem(
		itemID,
		generated.AssistantRunItemKindSubagent,
		claim.TaskID,
		normalized.Summary,
		payload,
		now,
	); err != nil {
		return DurableSubtaskTerminalReceipt{}, err
	}
	itemStatus := generated.AssistantRunItemStatusCompleted
	taskArtifactRefs := uniqueSorted(append(
		[]string{resultArtifactRef},
		normalized.ArtifactRefs...,
	))
	if normalized.Outcome == "failed" {
		itemStatus = generated.AssistantRunItemStatusFailed
		if err := r.TaskGraph.Fail(
			claim.TaskID,
			normalized.FailureCode,
			false,
		); err != nil {
			return DurableSubtaskTerminalReceipt{}, err
		}
	} else if err := r.TaskGraph.Complete(
		claim.TaskID,
		taskArtifactRefs,
		TaskVerification{Passed: true},
	); err != nil {
		return DurableSubtaskTerminalReceipt{}, err
	}
	if err := r.CompleteItem(
		itemID,
		itemStatus,
		taskArtifactRefs,
		normalized.Summary,
		now,
	); err != nil {
		return DurableSubtaskTerminalReceipt{}, err
	}
	index = r.TaskGraph.taskIndex(claim.TaskID)
	task = &r.TaskGraph.Tasks[index]
	task.ArtifactRefs = taskArtifactRefs
	task.ResultArtifactRef = resultArtifactRef
	task.TerminalReceiptRef = resultArtifactRef
	r.TaskGraph.GraphRevision++
	r.touch(now)
	return r.durableSubtaskTerminalReceipt(*task)
}

func (r *Run) durableSubtaskTerminalReceipt(
	task TaskNode,
) (DurableSubtaskTerminalReceipt, error) {
	itemID := strings.TrimPrefix(
		strings.TrimSpace(task.TerminalReceiptRef),
		"assistant_run_item:",
	)
	if itemID == "" || itemID == task.TerminalReceiptRef {
		return DurableSubtaskTerminalReceipt{}, ErrJournalCorrupt
	}
	for _, item := range r.Items {
		if item.ItemID != itemID {
			continue
		}
		if item.Kind != generated.AssistantRunItemKindSubagent ||
			item.TaskID != task.TaskID || item.CompletedAt.IsZero() ||
			(item.Status != generated.AssistantRunItemStatusCompleted &&
				item.Status != generated.AssistantRunItemStatusFailed) {
			return DurableSubtaskTerminalReceipt{}, ErrJournalCorrupt
		}
		payload, err := decodeDurableSubtaskResultPayload(
			stringPayloadValue(item.Payload, "resultPayloadJson"),
		)
		if err != nil {
			return DurableSubtaskTerminalReceipt{}, err
		}
		receipt := DurableSubtaskTerminalReceipt{
			ReceiptRef:        task.TerminalReceiptRef,
			RunID:             r.RunID,
			TaskID:            task.TaskID,
			InputDigest:       stringPayloadValue(item.Payload, "inputDigest"),
			Outcome:           stringPayloadValue(item.Payload, "outcome"),
			Attempt:           intPayloadValue(item.Payload, "attempt"),
			FencingToken:      int64PayloadValue(item.Payload, "fencingToken"),
			IdempotencyKey:    stringPayloadValue(item.Payload, "idempotencyKey"),
			Summary:           item.Summary,
			FailureCode:       stringPayloadValue(item.Payload, "failureCode"),
			ResultArtifactRef: task.ResultArtifactRef,
			Payload:           payload,
			CompletedAt:       item.CompletedAt.UTC(),
		}
		if receipt.InputDigest == "" || receipt.IdempotencyKey == "" ||
			receipt.ResultArtifactRef == "" || receipt.Attempt <= 0 ||
			receipt.FencingToken <= 0 ||
			(receipt.Outcome != "completed" && receipt.Outcome != "failed") {
			return DurableSubtaskTerminalReceipt{}, ErrJournalCorrupt
		}
		return receipt, nil
	}
	return DurableSubtaskTerminalReceipt{}, ErrJournalCorrupt
}

func durableSubtaskClaimFromTask(
	runID string,
	inputDigest string,
	task TaskNode,
) DurableSubtaskClaim {
	return DurableSubtaskClaim{
		RunID:          runID,
		TaskID:         task.TaskID,
		ClaimID:        task.ClaimID,
		ClaimOwner:     task.ClaimOwner,
		InputDigest:    inputDigest,
		FencingToken:   task.FencingToken,
		Attempt:        task.Attempt,
		IdempotencyKey: task.IdempotencyKey,
		LeaseExpiresAt: task.LeaseExpiresAt,
	}
}

func sameDurableSubtaskClaim(
	runID string,
	goalRevision int64,
	task TaskNode,
	claim DurableSubtaskClaim,
) bool {
	expectedIdempotencyKey := durableSubtaskIdempotencyKey(
		runID,
		goalRevision,
		DurableSubtaskClaimRequest{
			TaskID:      task.TaskID,
			OwnerAgent:  task.OwnerAgent,
			InputDigest: claim.InputDigest,
		},
	)
	return validDurableSubtaskDigest(claim.InputDigest) &&
		strings.TrimSpace(claim.RunID) == strings.TrimSpace(runID) &&
		strings.TrimSpace(claim.TaskID) == task.TaskID &&
		strings.TrimSpace(claim.ClaimID) == task.ClaimID &&
		strings.TrimSpace(claim.ClaimOwner) == task.ClaimOwner &&
		claim.FencingToken == task.FencingToken &&
		claim.Attempt == task.Attempt &&
		strings.TrimSpace(claim.IdempotencyKey) == task.IdempotencyKey &&
		expectedIdempotencyKey == task.IdempotencyKey
}

func validDurableSubtaskClaimRequest(
	request DurableSubtaskClaimRequest,
) bool {
	return strings.TrimSpace(request.TaskID) != "" &&
		strings.HasPrefix(strings.TrimSpace(request.OwnerAgent), "subagent:") &&
		validDurableSubtaskDigest(request.InputDigest)
}

func validDurableSubtaskDigest(value string) bool {
	value = strings.TrimSpace(value)
	if len(value) != len("sha256:")+sha256.Size*2 ||
		!strings.HasPrefix(value, "sha256:") {
		return false
	}
	for _, char := range strings.TrimPrefix(value, "sha256:") {
		if !(char >= '0' && char <= '9') && !(char >= 'a' && char <= 'f') {
			return false
		}
	}
	return true
}

func durableSubtaskIdempotencyKey(
	runID string,
	goalRevision int64,
	request DurableSubtaskClaimRequest,
) string {
	return durableSubtaskDigest(
		"durable-subtask-idempotency",
		strings.TrimSpace(runID),
		fmt.Sprint(goalRevision),
		strings.TrimSpace(request.TaskID),
		strings.TrimSpace(request.OwnerAgent),
		strings.TrimSpace(request.InputDigest),
	)
}

func durableSubtaskClaimID(
	runID string,
	taskID string,
	claimOwner string,
	fencingToken int64,
	now time.Time,
) string {
	return durableSubtaskDigest(
		"durable-subtask-claim",
		strings.TrimSpace(runID),
		strings.TrimSpace(taskID),
		strings.TrimSpace(claimOwner),
		fmt.Sprint(fencingToken),
		fmt.Sprint(now.UTC().UnixNano()),
	)
}

func durableSubtaskTerminalItemID(idempotencyKey string) string {
	digest := sha256.Sum256([]byte(
		"durable-subtask-terminal\x00" + strings.TrimSpace(idempotencyKey),
	))
	return "subtask-terminal:" + hex.EncodeToString(digest[:16])
}

func durableSubtaskDigest(parts ...string) string {
	hash := sha256.New()
	for _, part := range parts {
		hash.Write([]byte(part))
		hash.Write([]byte{0})
	}
	return "sha256:" + hex.EncodeToString(hash.Sum(nil))
}

func encodeDurableSubtaskResult(
	result DurableSubtaskResult,
) (string, DurableSubtaskResult, error) {
	result.Outcome = strings.TrimSpace(result.Outcome)
	result.Summary = strings.TrimSpace(result.Summary)
	result.FailureCode = strings.TrimSpace(result.FailureCode)
	result.ArtifactRefs = uniqueSorted(result.ArtifactRefs)
	if len(result.Summary) > 4096 || len(result.ArtifactRefs) > 64 ||
		unsafeReasoningPayload(result.Payload) {
		return "", DurableSubtaskResult{}, ErrUnsafePayload
	}
	switch result.Outcome {
	case "completed":
		if result.Summary == "" || len(result.Payload) == 0 ||
			result.FailureCode != "" {
			return "", DurableSubtaskResult{}, ErrInvalidRun
		}
	case "failed":
		if result.FailureCode == "" {
			return "", DurableSubtaskResult{}, ErrInvalidRun
		}
	default:
		return "", DurableSubtaskResult{}, ErrInvalidRun
	}
	encoded, err := json.Marshal(result.Payload)
	if err != nil || len(encoded) > maxDurableSubtaskPayloadBytes {
		return "", DurableSubtaskResult{}, ErrInvalidRun
	}
	return string(encoded), result, nil
}

func decodeDurableSubtaskResultPayload(value string) (map[string]any, error) {
	if len(value) == 0 || len(value) > maxDurableSubtaskPayloadBytes {
		return nil, ErrJournalCorrupt
	}
	decoded := map[string]any{}
	if err := json.Unmarshal([]byte(value), &decoded); err != nil ||
		unsafeReasoningPayload(decoded) {
		return nil, ErrJournalCorrupt
	}
	return decoded, nil
}

func stringPayloadValue(payload map[string]any, key string) string {
	value, _ := payload[key].(string)
	return strings.TrimSpace(value)
}

func intPayloadValue(payload map[string]any, key string) int {
	return int(int64PayloadValue(payload, key))
}

func int64PayloadValue(payload map[string]any, key string) int64 {
	switch value := payload[key].(type) {
	case int:
		return int64(value)
	case int32:
		return int64(value)
	case int64:
		return value
	case float64:
		return int64(value)
	default:
		return 0
	}
}
