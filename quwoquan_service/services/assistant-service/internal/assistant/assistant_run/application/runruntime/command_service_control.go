package runruntime

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

type ApproveToolUseCommand struct {
	UserID           string
	RunID            string
	ToolInvocationID string
	CommandID        string
	Decision         string
	ApprovalPermit   string
	InstallationID   string
	DeviceID         string
}

type SubmitDeviceActionReceiptCommand struct {
	UserID           string
	RunID            string
	ToolInvocationID string
	CommandID        string
	Receipt          DeviceActionExecutionReceipt
}

func (s *CommandService) Pause(
	ctx context.Context,
	userID string,
	runID string,
	commandID string,
	reason string,
) (Run, error) {
	return s.mutate(ctx, userID, runID, commandID, "run_pause_requested", reason, func(run *Run, now time.Time) error {
		if run.State == generated.AssistantRunStatePaused {
			return nil
		}
		return run.RequestPause(reason, now)
	})
}

func (s *CommandService) Resume(
	ctx context.Context,
	userID string,
	runID string,
	commandID string,
) (Run, error) {
	return s.mutate(ctx, userID, runID, commandID, "run_resumed", nil, func(run *Run, now time.Time) error {
		return run.Resume(now)
	})
}

func (s *CommandService) Steer(
	ctx context.Context,
	userID string,
	runID string,
	commandID string,
	instruction string,
) (Run, error) {
	return s.mutate(ctx, userID, runID, commandID, "run_steer_requested", instruction, func(run *Run, now time.Time) error {
		return run.RequestSteer(instruction, now)
	})
}

func (s *CommandService) Cancel(
	ctx context.Context,
	userID string,
	runID string,
	commandID string,
) (Run, error) {
	startedAt := s.now()
	run, err := s.mutate(ctx, userID, runID, commandID, "run_cancelled", nil, func(run *Run, now time.Time) error {
		if run.State == generated.AssistantRunStateCancelled {
			return nil
		}
		if s.cancel != nil {
			if err := s.cancel.Cancel(ctx, run, "user_cancelled", now); err != nil {
				return err
			}
		} else if err := run.Transition(
			generated.AssistantRunStateCancelled,
			"user_cancelled",
			now,
		); err != nil {
			return err
		}
		snapshot := assistantmodel.AssistantRunTerminalSnapshot{
			AnswerText:        "",
			Processes:         []assistantmodel.AssistantRunVisibleProcess{},
			SelectedPolicyRef: terminalSelectedPolicyRef(run.FrozenPolicySelection),
		}
		return run.SetTerminalSnapshot(snapshot, now)
	})
	observeCancelDuration(startedAt, err)
	return run, err
}

func (s *CommandService) ApproveToolUse(
	ctx context.Context,
	command ApproveToolUseCommand,
) (Run, *DeviceActionPermit, error) {
	decision := strings.TrimSpace(command.Decision)
	if decision != "approved" && decision != "rejected" {
		return Run{}, nil, ErrInvalidRun
	}
	if decision == "approved" &&
		(strings.TrimSpace(command.InstallationID) == "" ||
			strings.TrimSpace(command.DeviceID) == "") {
		return Run{}, nil, ErrInvalidRun
	}
	permitValue, jti, err := newDeviceActionPermitIdentity()
	if err != nil {
		return Run{}, nil, err
	}
	run, err := s.mutate(
		ctx,
		command.UserID,
		command.RunID,
		command.CommandID,
		"tool_use_approved",
		map[string]string{
			"toolInvocationId": command.ToolInvocationID,
			"decision":         decision,
		},
		func(run *Run, now time.Time) error {
			if run.State != generated.AssistantRunStateWaitingApproval ||
				run.Checkpoint == nil ||
				run.Checkpoint.PendingApprovalRef !=
					strings.TrimSpace(command.ToolInvocationID) ||
				strings.TrimSpace(command.ApprovalPermit) !=
					assistantRunContinuationToken(
						run.RunID,
						command.ToolInvocationID,
					) {
				return ErrInvalidTransition
			}
			binding, valid := pendingDeviceActionBinding(
				run.PresentationDocument,
				run.RunID,
				strings.TrimSpace(command.ToolInvocationID),
				strings.TrimSpace(command.ApprovalPermit),
				decision,
				now,
			)
			if !valid {
				return ErrInvalidRun
			}
			if decision == "approved" {
				permit := DeviceActionPermit{
					RunID:            run.RunID,
					ToolInvocationID: strings.TrimSpace(command.ToolInvocationID),
					InstallationID:   strings.TrimSpace(command.InstallationID),
					DeviceID:         strings.TrimSpace(command.DeviceID),
					Capability:       binding.Capability,
					InputDigest:      binding.InputDigest,
					IdempotencyKey:   strings.TrimSpace(command.ToolInvocationID),
					ApprovalRef:      strings.TrimSpace(command.ApprovalPermit),
					JTI:              jti,
					ExpiresAt:        now.UTC().Add(time.Minute),
					Permit:           permitValue,
				}
				run.Checkpoint.PendingApprovalRef = ""
				run.Checkpoint.PendingDeviceAction = &permit
				run.Checkpoint.DecisionSummary = append(
					run.Checkpoint.DecisionSummary,
					"device_action_approved:"+
						strings.TrimSpace(command.ToolInvocationID),
				)
				return run.Transition(
					generated.AssistantRunStateWaitingExternal,
					"device_action_receipt_pending",
					now,
				)
			}
			run.Checkpoint.PendingApprovalRef = ""
			run.Checkpoint.PendingDeviceAction = nil
			for index := range run.Items {
				if run.Items[index].ItemID ==
					strings.TrimSpace(command.ToolInvocationID) &&
					run.Items[index].Status == generated.AssistantRunItemStatusStarted {
					if err := run.CompleteItem(
						run.Items[index].ItemID,
						generated.AssistantRunItemStatusCancelled,
						nil,
						"user_rejected",
						now,
					); err != nil {
						return err
					}
					break
				}
			}
			run.CancelActiveWork("user_rejected", now)
			return run.Transition(generated.AssistantRunStateCancelled, "user_rejected", now)
		},
	)
	if err != nil {
		return Run{}, nil, err
	}
	if run.Checkpoint == nil || run.Checkpoint.PendingDeviceAction == nil {
		return run, nil, nil
	}
	permit := *run.Checkpoint.PendingDeviceAction
	return run, &permit, nil
}

func (s *CommandService) SubmitDeviceActionReceipt(
	ctx context.Context,
	command SubmitDeviceActionReceiptCommand,
) (Run, error) {
	command = normalizeDeviceActionReceiptCommand(command)
	return s.mutateWithIdempotencyConflict(
		ctx,
		command.UserID,
		command.RunID,
		command.CommandID,
		"device_action_receipt_submitted",
		command,
		ErrDeviceActionPermitReplayed,
		func(run *Run, now time.Time) error {
			if deviceActionPermitWasConsumed(run, command) {
				return ErrDeviceActionPermitReplayed
			}
			if run.State != generated.AssistantRunStateWaitingExternal ||
				run.Checkpoint == nil ||
				run.Checkpoint.PendingDeviceAction == nil {
				return ErrDeviceActionPermitInvalid
			}
			permit := *run.Checkpoint.PendingDeviceAction
			receipt := command.Receipt
			if permit.RunID != command.RunID ||
				permit.ToolInvocationID != command.ToolInvocationID ||
				permit.InstallationID != receipt.InstallationID ||
				permit.DeviceID != receipt.DeviceID ||
				permit.Capability != receipt.Capability ||
				permit.InputDigest != receipt.InputDigest ||
				permit.IdempotencyKey != receipt.IdempotencyKey ||
				permit.IdempotencyKey != command.CommandID ||
				permit.Permit != receipt.Permit ||
				permit.ExpiresAt.IsZero() ||
				receipt.ExecutedAt.IsZero() {
				return ErrDeviceActionPermitInvalid
			}
			outcome := strings.TrimSpace(receipt.Outcome)
			switch outcome {
			case "completed":
				if strings.TrimSpace(receipt.FailureCode) != "" {
					return ErrDeviceActionPermitInvalid
				}
			case "unavailable", "denied", "failed":
				if strings.TrimSpace(receipt.FailureCode) == "" {
					return ErrDeviceActionPermitInvalid
				}
			default:
				return ErrDeviceActionPermitInvalid
			}
			// A permit is invalid at its exact expiry instant; accepting equality
			// would grant one extra scheduler tick beyond the signed boundary.
			if !now.UTC().Before(permit.ExpiresAt.UTC()) {
				return ErrDeviceActionPermitExpired
			}
			receipt.Outcome = outcome
			run.Checkpoint.DeviceActionReceipts = append(
				run.Checkpoint.DeviceActionReceipts,
				receipt,
			)
			run.Checkpoint.PendingDeviceAction = nil
			if outcome == "completed" {
				run.Checkpoint.DecisionSummary = append(
					run.Checkpoint.DecisionSummary,
					"device_action_completed:"+permit.ToolInvocationID,
				)
				return run.Transition(generated.AssistantRunStateExecuting, "", now)
			}
			run.Checkpoint.DecisionSummary = append(
				run.Checkpoint.DecisionSummary,
				"device_action_failed:"+permit.ToolInvocationID+":"+outcome,
			)
			for index := range run.Items {
				if run.Items[index].ItemID == permit.ToolInvocationID &&
					run.Items[index].Status == generated.AssistantRunItemStatusStarted {
					if err := run.CompleteItem(
						run.Items[index].ItemID,
						generated.AssistantRunItemStatusCancelled,
						nil,
						"device_action_"+outcome,
						now,
					); err != nil {
						return err
					}
					break
				}
			}
			run.CancelActiveWork("device_action_"+outcome, now)
			return run.Transition(
				generated.AssistantRunStateCancelled,
				"device_action_"+outcome,
				now,
			)
		},
	)
}

func normalizeDeviceActionReceiptCommand(
	command SubmitDeviceActionReceiptCommand,
) SubmitDeviceActionReceiptCommand {
	command.UserID = strings.TrimSpace(command.UserID)
	command.RunID = strings.TrimSpace(command.RunID)
	command.ToolInvocationID = strings.TrimSpace(command.ToolInvocationID)
	command.CommandID = strings.TrimSpace(command.CommandID)
	command.Receipt.InstallationID = strings.TrimSpace(command.Receipt.InstallationID)
	command.Receipt.DeviceID = strings.TrimSpace(command.Receipt.DeviceID)
	command.Receipt.Capability = strings.TrimSpace(command.Receipt.Capability)
	command.Receipt.InputDigest = strings.TrimSpace(command.Receipt.InputDigest)
	command.Receipt.Permit = strings.TrimSpace(command.Receipt.Permit)
	command.Receipt.IdempotencyKey = strings.TrimSpace(command.Receipt.IdempotencyKey)
	command.Receipt.Outcome = strings.TrimSpace(command.Receipt.Outcome)
	command.Receipt.ExecutedAt = command.Receipt.ExecutedAt.UTC()
	command.Receipt.DeviceObjectID = strings.TrimSpace(command.Receipt.DeviceObjectID)
	command.Receipt.FailureCode = strings.TrimSpace(command.Receipt.FailureCode)
	return command
}

func deviceActionPermitWasConsumed(
	run *Run,
	command SubmitDeviceActionReceiptCommand,
) bool {
	if run == nil || run.Checkpoint == nil {
		return false
	}
	permitValue := strings.TrimSpace(command.Receipt.Permit)
	if permitValue == "" {
		return false
	}
	for _, receipt := range run.Checkpoint.DeviceActionReceipts {
		if strings.TrimSpace(receipt.Permit) != permitValue {
			continue
		}
		// Replayed classifies reuse of the same consumed permit binding. A
		// caller that changes any target binding still receives Invalid instead
		// of learning that an unrelated opaque permit was consumed.
		return strings.TrimSpace(receipt.IdempotencyKey) ==
			strings.TrimSpace(command.ToolInvocationID) &&
			strings.TrimSpace(receipt.InstallationID) == command.Receipt.InstallationID &&
			strings.TrimSpace(receipt.DeviceID) == command.Receipt.DeviceID &&
			strings.TrimSpace(receipt.Capability) == command.Receipt.Capability &&
			strings.TrimSpace(receipt.InputDigest) == command.Receipt.InputDigest &&
			strings.TrimSpace(receipt.IdempotencyKey) == command.Receipt.IdempotencyKey
	}
	return false
}

type pendingDeviceActionIntentBinding struct {
	Capability  string
	InputDigest string
}

func pendingDeviceActionBinding(
	presentation map[string]any,
	runID string,
	toolInvocationID string,
	approvalPermit string,
	decision string,
	now time.Time,
) (pendingDeviceActionIntentBinding, bool) {
	for _, rawNode := range objectSlice(presentation["nodes"]) {
		action := objectValue(rawNode["action"])
		if strings.TrimSpace(stringValue(action["kind"])) != "ApproveTool" {
			continue
		}
		approveTool := objectValue(action["approveTool"])
		if strings.TrimSpace(stringValue(approveTool["runId"])) != runID ||
			strings.TrimSpace(stringValue(approveTool["toolInvocationId"])) !=
				toolInvocationID ||
			strings.TrimSpace(stringValue(approveTool["decision"])) != decision ||
			strings.TrimSpace(stringValue(approveTool["approvalPermit"])) !=
				approvalPermit {
			continue
		}
		expiresAt, err := time.Parse(
			time.RFC3339Nano,
			strings.TrimSpace(stringValue(action["expiresAt"])),
		)
		capability := strings.TrimSpace(stringValue(approveTool["capability"]))
		inputDigest := strings.TrimSpace(stringValue(approveTool["inputDigest"]))
		expectedDigest := actionIntentRequestDigest(approveTool)
		if err != nil || !now.UTC().Before(expiresAt.UTC()) ||
			capability == "" || inputDigest == "" ||
			expectedDigest == "" ||
			expectedDigest != strings.TrimSpace(stringValue(action["requestDigest"])) {
			continue
		}
		return pendingDeviceActionIntentBinding{
			Capability:  capability,
			InputDigest: inputDigest,
		}, true
	}
	return pendingDeviceActionIntentBinding{}, false
}

func objectSlice(value any) []map[string]any {
	switch values := value.(type) {
	case []map[string]any:
		return values
	case []any:
		result := make([]map[string]any, 0, len(values))
		for _, value := range values {
			if object := objectValue(value); object != nil {
				result = append(result, object)
			}
		}
		return result
	default:
		return nil
	}
}

func objectValue(value any) map[string]any {
	object, _ := value.(map[string]any)
	return object
}

func stringValue(value any) string {
	text, _ := value.(string)
	return text
}

func assistantRunContinuationToken(runID string, toolUseID string) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(runID) + "\x00" + strings.TrimSpace(toolUseID)))
	return "ct_" + hex.EncodeToString(digest[:16])
}

func actionIntentRequestDigest(value map[string]any) string {
	encoded, err := json.Marshal(value)
	if err != nil {
		return ""
	}
	digest := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(digest[:])
}

func newDeviceActionPermitIdentity() (string, string, error) {
	permitBytes := make([]byte, 32)
	if _, err := rand.Read(permitBytes); err != nil {
		return "", "", err
	}
	jtiBytes := make([]byte, 16)
	if _, err := rand.Read(jtiBytes); err != nil {
		return "", "", err
	}
	return "dap_" + hex.EncodeToString(permitBytes),
		"dapjti_" + hex.EncodeToString(jtiBytes),
		nil
}
