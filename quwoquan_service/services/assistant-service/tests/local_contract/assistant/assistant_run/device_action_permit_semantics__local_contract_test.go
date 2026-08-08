// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-003
package assistant_run_test

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	rundomain "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain"
)

func TestAssistantRunStartIdempotencyConflictIsTypedAndSideEffectFree(t *testing.T) {
	t.Parallel()
	repository := newMemoryRunRepository()
	clock := time.Date(2026, 8, 8, 9, 0, 0, 0, time.UTC)
	service := newDevicePermitCommandService(repository, &clock)
	useCases := runapplication.NewUseCases(service)
	input := runapplication.StartInput{
		ClientRequestID: "run-idempotency-key",
		Intent: rundomain.Intent{
			Kind:   "answer",
			Answer: &rundomain.AnswerIntent{Text: "整理行程"},
		},
		TrustedPersonaID: "run-owner:persona",
	}
	first, err := useCases.Start(
		t.Context(),
		"run-owner",
		"run-session",
		"trace-idempotency",
		input,
	)
	if err != nil {
		t.Fatalf("start AssistantRun: %v", err)
	}
	replayed, err := useCases.Start(
		t.Context(),
		"run-owner",
		"run-session",
		"trace-idempotency",
		input,
	)
	if err != nil || replayed.RunID != first.RunID {
		t.Fatalf("same digest did not replay: run=%s err=%v", replayed.RunID, err)
	}
	baseline := devicePermitRepositoryFacts(repository, first.RunID)
	input.Intent.Answer.Text = "改成完全不同的目标"
	_, err = useCases.Start(
		t.Context(),
		"run-owner",
		"run-session",
		"trace-idempotency",
		input,
	)
	assertAssistantAppError(
		t,
		err,
		"ASSISTANT.USER.run_idempotency_conflict",
		http.StatusConflict,
	)
	assertDevicePermitRepositoryFacts(t, repository, first.RunID, baseline)
}

func TestDeviceActionPermitRejectsEveryBindingMismatchWithoutWritingFacts(t *testing.T) {
	t.Parallel()
	tests := map[string]func(*runruntime.SubmitDeviceActionReceiptCommand){
		"tool invocation": func(command *runruntime.SubmitDeviceActionReceiptCommand) {
			command.ToolInvocationID = "different-tool"
		},
		"installation": func(command *runruntime.SubmitDeviceActionReceiptCommand) {
			command.Receipt.InstallationID = "different-installation"
		},
		"device": func(command *runruntime.SubmitDeviceActionReceiptCommand) {
			command.Receipt.DeviceID = "different-device"
		},
		"capability": func(command *runruntime.SubmitDeviceActionReceiptCommand) {
			command.Receipt.Capability = "different-capability"
		},
		"input digest": func(command *runruntime.SubmitDeviceActionReceiptCommand) {
			command.Receipt.InputDigest = "sha256:" + strings.Repeat("b", 64)
		},
		"idempotency key": func(command *runruntime.SubmitDeviceActionReceiptCommand) {
			command.Receipt.IdempotencyKey = "different-idempotency-key"
		},
		"command identity": func(command *runruntime.SubmitDeviceActionReceiptCommand) {
			command.CommandID = "different-command"
		},
		"opaque permit": func(command *runruntime.SubmitDeviceActionReceiptCommand) {
			command.Receipt.Permit = "different-permit"
		},
		"execution time": func(command *runruntime.SubmitDeviceActionReceiptCommand) {
			command.Receipt.ExecutedAt = time.Time{}
		},
		"completed with failure": func(command *runruntime.SubmitDeviceActionReceiptCommand) {
			command.Receipt.FailureCode = "ASSISTANT.SYSTEM.device_action_failed"
		},
		"failed without failure": func(command *runruntime.SubmitDeviceActionReceiptCommand) {
			command.Receipt.Outcome = "failed"
		},
		"unknown outcome": func(command *runruntime.SubmitDeviceActionReceiptCommand) {
			command.Receipt.Outcome = "maybe"
		},
	}
	for name, mutate := range tests {
		name, mutate := name, mutate
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			fixture := newDevicePermitFixture(t)
			command := fixture.validCommand()
			mutate(&command)
			baseline := devicePermitRepositoryFacts(
				fixture.repository,
				fixture.run.RunID,
			)
			_, err := fixture.service.SubmitDeviceActionReceipt(
				t.Context(),
				command,
			)
			if !errors.Is(err, runruntime.ErrDeviceActionPermitInvalid) {
				t.Fatalf("binding mismatch error=%v", err)
			}
			assertDevicePermitRepositoryFacts(
				t,
				fixture.repository,
				fixture.run.RunID,
				baseline,
			)
		})
	}
}

func TestDeviceActionPermitExpiresAtExactBoundaryWithoutWritingFacts(t *testing.T) {
	t.Parallel()
	fixture := newDevicePermitFixture(t)
	*fixture.clock = fixture.permit.ExpiresAt
	baseline := devicePermitRepositoryFacts(
		fixture.repository,
		fixture.run.RunID,
	)
	_, err := fixture.service.SubmitDeviceActionReceipt(
		t.Context(),
		fixture.validCommand(),
	)
	if !errors.Is(err, runruntime.ErrDeviceActionPermitExpired) {
		t.Fatalf("exact expiry error=%v", err)
	}
	assertDevicePermitRepositoryFacts(
		t,
		fixture.repository,
		fixture.run.RunID,
		baseline,
	)
	useCases := runapplication.NewUseCases(fixture.service)
	command := fixture.validCommand()
	_, err = useCases.SubmitDeviceActionReceipt(
		t.Context(),
		command.UserID,
		command.RunID,
		command.ToolInvocationID,
		command.CommandID,
		devicePermitReceiptInput(command.Receipt),
	)
	assertAssistantAppError(
		t,
		err,
		"ASSISTANT.USER.device_action_permit_expired",
		http.StatusGone,
	)
}

func TestConsumedDeviceActionPermitRejectsReplayWithoutNewFacts(t *testing.T) {
	t.Parallel()
	fixture := newDevicePermitFixture(t)
	command := fixture.validCommand()
	completed, err := fixture.service.SubmitDeviceActionReceipt(
		t.Context(),
		command,
	)
	if err != nil || completed.State != generated.AssistantRunStateExecuting {
		t.Fatalf("submit valid device receipt: state=%s err=%v", completed.State, err)
	}
	baseline := devicePermitRepositoryFacts(
		fixture.repository,
		fixture.run.RunID,
	)

	// An exact transport retry replays its durable command receipt.
	if _, err := fixture.service.SubmitDeviceActionReceipt(
		t.Context(),
		command,
	); err != nil {
		t.Fatalf("exact receipt replay: %v", err)
	}
	assertDevicePermitRepositoryFacts(
		t,
		fixture.repository,
		fixture.run.RunID,
		baseline,
	)

	changed := command
	changed.Receipt.DeviceObjectID = "different-object"
	_, err = fixture.service.SubmitDeviceActionReceipt(t.Context(), changed)
	if !errors.Is(err, runruntime.ErrDeviceActionPermitReplayed) {
		t.Fatalf("same command identity with different payload error=%v", err)
	}
	assertDevicePermitRepositoryFacts(
		t,
		fixture.repository,
		fixture.run.RunID,
		baseline,
	)

	newIdentity := command
	newIdentity.CommandID = "new-receipt-command"
	_, err = fixture.service.SubmitDeviceActionReceipt(t.Context(), newIdentity)
	if !errors.Is(err, runruntime.ErrDeviceActionPermitReplayed) {
		t.Fatalf("consumed permit error=%v", err)
	}
	assertDevicePermitRepositoryFacts(
		t,
		fixture.repository,
		fixture.run.RunID,
		baseline,
	)
	changedBinding := newIdentity
	changedBinding.CommandID = "new-receipt-with-mismatched-binding"
	changedBinding.Receipt.DeviceID = "different-consumed-device"
	_, err = fixture.service.SubmitDeviceActionReceipt(t.Context(), changedBinding)
	if !errors.Is(err, runruntime.ErrDeviceActionPermitInvalid) {
		t.Fatalf("consumed permit with changed binding error=%v", err)
	}
	assertDevicePermitRepositoryFacts(
		t,
		fixture.repository,
		fixture.run.RunID,
		baseline,
	)

	useCases := runapplication.NewUseCases(fixture.service)
	_, err = useCases.SubmitDeviceActionReceipt(
		t.Context(),
		newIdentity.UserID,
		newIdentity.RunID,
		newIdentity.ToolInvocationID,
		newIdentity.CommandID,
		devicePermitReceiptInput(newIdentity.Receipt),
	)
	assertAssistantAppError(
		t,
		err,
		"ASSISTANT.USER.device_action_permit_replayed",
		http.StatusConflict,
	)
}

type devicePermitFixture struct {
	repository *memoryRunRepository
	service    *runruntime.CommandService
	clock      *time.Time
	run        runruntime.Run
	permit     runruntime.DeviceActionPermit
}

func newDevicePermitFixture(t *testing.T) devicePermitFixture {
	t.Helper()
	repository := newMemoryRunRepository()
	now := time.Date(2026, 8, 8, 10, 0, 0, 0, time.UTC)
	service := newDevicePermitCommandService(repository, &now)
	run, err := service.Start(t.Context(), runruntime.StartCommand{
		UserID:          "device-permit-owner",
		PersonaID:       "device-permit-owner:persona",
		SessionID:       "device-permit-session",
		ClientRequestID: "device-permit-start",
		InputText:       "创建日历提醒",
	})
	if err != nil {
		t.Fatalf("start device permit Run: %v", err)
	}
	expectedRevision := run.Revision
	for _, state := range []generated.AssistantRunState{
		generated.AssistantRunStateOrienting,
		generated.AssistantRunStatePlanning,
		generated.AssistantRunStateExecuting,
		generated.AssistantRunStateWaitingApproval,
	} {
		now = now.Add(time.Second)
		if err := run.Transition(state, "", now); err != nil {
			t.Fatalf("transition to %s: %v", state, err)
		}
	}
	const toolUseID = "tool-use-device-permit"
	continuationToken := testAssistantRunContinuationToken(run.RunID, toolUseID)
	run.Checkpoint = &runruntime.Checkpoint{
		CheckpointID:       "checkpoint-device-permit",
		Revision:           run.Revision,
		PendingApprovalRef: toolUseID,
		CreatedAt:          now,
	}
	approveTool := map[string]any{
		"runId":            run.RunID,
		"toolInvocationId": toolUseID,
		"decision":         "approved",
		"capability":       "calendar_create_reminder",
		"inputDigest":      "sha256:" + strings.Repeat("a", 64),
		"approvalPermit":   continuationToken,
	}
	run.PresentationDocument = map[string]any{
		"revision": int64(1),
		"nodes": []map[string]any{{
			"nodeId": "device-permit-confirmation",
			"kind":   "confirmation_card",
			"action": map[string]any{
				"kind":          "ApproveTool",
				"approveTool":   approveTool,
				"requestDigest": testActionIntentDigest(approveTool),
				"expiresAt":     now.Add(time.Minute).Format(time.RFC3339Nano),
			},
		}},
	}
	run.JournalSequence++
	if err := repository.Commit(
		t.Context(),
		expectedRevision,
		run,
		[]runruntime.JournalEvent{{
			EventID:   run.RunID + ":waiting-device-permit",
			RunID:     run.RunID,
			Sequence:  run.JournalSequence,
			Revision:  run.Revision,
			Kind:      "tool_use_waiting_approval",
			CreatedAt: now,
		}},
		nil,
	); err != nil {
		t.Fatalf("persist waiting approval: %v", err)
	}
	approved, permit, err := service.ApproveToolUse(
		t.Context(),
		runruntime.ApproveToolUseCommand{
			UserID:           run.UserID,
			RunID:            run.RunID,
			ToolInvocationID: toolUseID,
			CommandID:        "approve-device-permit",
			Decision:         "approved",
			ApprovalPermit:   continuationToken,
			InstallationID:   "installation-device-permit",
			DeviceID:         "device-device-permit",
		},
	)
	if err != nil || permit == nil {
		t.Fatalf("approve device permit: permit=%+v err=%v", permit, err)
	}
	return devicePermitFixture{
		repository: repository,
		service:    service,
		clock:      &now,
		run:        approved,
		permit:     *permit,
	}
}

func newDevicePermitCommandService(
	repository runruntime.Repository,
	clock *time.Time,
) *runruntime.CommandService {
	if clock.IsZero() {
		*clock = time.Date(2026, 8, 8, 9, 0, 0, 0, time.UTC)
	}
	return runruntime.NewCommandService(
		repository,
		runruntime.SessionResolverFunc(func(
			context.Context,
			string,
			string,
		) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		func() time.Time { return *clock },
		nil,
		runruntime.WithPolicyResolver(testPolicyResolver()),
	)
}

func (fixture devicePermitFixture) validCommand() runruntime.SubmitDeviceActionReceiptCommand {
	return runruntime.SubmitDeviceActionReceiptCommand{
		UserID:           fixture.run.UserID,
		RunID:            fixture.run.RunID,
		ToolInvocationID: fixture.permit.ToolInvocationID,
		CommandID:        fixture.permit.IdempotencyKey,
		Receipt: runruntime.DeviceActionExecutionReceipt{
			InstallationID: fixture.permit.InstallationID,
			DeviceID:       fixture.permit.DeviceID,
			Capability:     fixture.permit.Capability,
			InputDigest:    fixture.permit.InputDigest,
			Permit:         fixture.permit.Permit,
			IdempotencyKey: fixture.permit.IdempotencyKey,
			Outcome:        "completed",
			ExecutedAt:     fixture.permit.ExpiresAt.Add(-time.Second),
			DeviceObjectID: "calendar-event-device-permit",
		},
	}
}

type devicePermitFactCount struct {
	events         int
	commandReceipt int
	deviceReceipt  int
	revision       int64
}

func devicePermitRepositoryFacts(
	repository *memoryRunRepository,
	runID string,
) devicePermitFactCount {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	run := repository.runs[runID]
	deviceReceipts := 0
	if run.Checkpoint != nil {
		deviceReceipts = len(run.Checkpoint.DeviceActionReceipts)
	}
	return devicePermitFactCount{
		events:         len(repository.events[runID]),
		commandReceipt: len(repository.receipts),
		deviceReceipt:  deviceReceipts,
		revision:       run.Revision,
	}
}

func assertDevicePermitRepositoryFacts(
	t *testing.T,
	repository *memoryRunRepository,
	runID string,
	want devicePermitFactCount,
) {
	t.Helper()
	if got := devicePermitRepositoryFacts(repository, runID); got != want {
		t.Fatalf("rejected device receipt wrote facts: got=%+v want=%+v", got, want)
	}
}

func devicePermitReceiptInput(
	receipt runruntime.DeviceActionExecutionReceipt,
) runapplication.DeviceActionExecutionReceiptInput {
	return runapplication.DeviceActionExecutionReceiptInput{
		InstallationID: receipt.InstallationID,
		DeviceID:       receipt.DeviceID,
		Capability:     receipt.Capability,
		InputDigest:    receipt.InputDigest,
		Permit:         receipt.Permit,
		IdempotencyKey: receipt.IdempotencyKey,
		Outcome:        receipt.Outcome,
		ExecutedAt:     receipt.ExecutedAt,
		DeviceObjectID: receipt.DeviceObjectID,
		FailureCode:    receipt.FailureCode,
	}
}

func assertAssistantAppError(
	t *testing.T,
	err error,
	wantCode string,
	wantStatus int,
) {
	t.Helper()
	var appError *rterr.AppError
	if !errors.As(err, &appError) {
		t.Fatalf("error=%v is not a canonical AppError", err)
	}
	if appError.Code.String() != wantCode || appError.HTTPStatus != wantStatus {
		t.Fatalf(
			"AppError code/status=%s/%d want=%s/%d",
			appError.Code,
			appError.HTTPStatus,
			wantCode,
			wantStatus,
		)
	}
}
