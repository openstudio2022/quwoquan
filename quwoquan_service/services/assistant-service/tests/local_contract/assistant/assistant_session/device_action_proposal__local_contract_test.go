package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	runerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_run"
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	assistantruntest "quwoquan_service/services/assistant-service/tests/support/assistantrun"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

type calendarDeviceActionModel struct {
	calls int
}

func (*calendarDeviceActionModel) ModelExecutionCapabilities() orchestration.ModelExecutionCapabilities {
	return durableTestModelCapabilities()
}

type calendarDeviceActionSkillRuntime struct{}

func (calendarDeviceActionSkillRuntime) SelectSkill(
	context.Context,
	assistant.AssistantTurn,
) (orchestration.SkillSelection, error) {
	return orchestration.SkillSelection{
		SkillID:      "calendar_task",
		DomainID:     "calendar_task",
		ToolPolicy:   []string{"calendar_create_reminder"},
		MaxToolCalls: 1,
	}, nil
}

func (m *calendarDeviceActionModel) Complete(
	_ context.Context,
	request orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	m.calls++
	return orchestration.ModelResponse{StructuredDelta: map[string]any{
		"nextAction": "tool_call",
		"toolName":   "calendar_create_reminder",
		"toolInput": map[string]any{
			"title":           "产品评审",
			"startsAt":        "2026-08-01T09:00:00+08:00",
			"durationMinutes": 60,
			"reminderMinutes": 10,
			"notes":           "确认 M0 准出",
		},
	}}, nil
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-003
func TestCalendarDeviceActionStopsAtExplicitConfirmation(t *testing.T) {
	model := &calendarDeviceActionModel{}
	registry := toolpkg.BaseRegistry()
	registry.RegisterDeviceAction(toolpkg.CalendarCreateReminderMetadata())
	runtime := orchestration.ReactRuntime{
		Model: model,
		Tools: orchestration.DefaultToolCoordinator{
			Registry: registry,
		},
	}
	result, err := runtime.Run(
		t.Context(),
		assistant.AssistantTurn{
			TurnID: "arn_calendar_action",
			Input:  assistant.AssistantTurnInput{Text: "明早九点提醒我参加产品评审"},
		},
		orchestration.SkillSelection{
			SkillID:      "calendar_task",
			DomainID:     "calendar_task",
			ToolPolicy:   []string{"calendar_create_reminder"},
			MaxToolCalls: 1,
		},
	)
	if err != nil {
		t.Fatalf("run calendar proposal: %v", err)
	}
	if result.StopReason != "waiting_tool_approval" {
		t.Fatalf("stopReason=%q tool=%+v", result.StopReason, result.Tool)
	}
	if result.FinalText != "" || model.calls != 1 {
		t.Fatalf("device action must not synthesize success before confirmation: %+v", result)
	}
	if result.Tool.Completed.Status != "waiting_confirmation" {
		t.Fatalf("tool status=%q", result.Tool.Completed.Status)
	}
	proposal, _ := result.Tool.Completed.Result["proposal"].(map[string]any)
	if proposal["toolName"] != "calendar_create_reminder" ||
		proposal["requiresConfirmation"] != true {
		t.Fatalf("proposal=%#v", proposal)
	}
}

func TestToolBoundaryRechecksDynamicSkillAccessBeforeExecution(t *testing.T) {
	model := &calendarDeviceActionModel{}
	tools := &countingDeviceActionTools{}
	revoked := errors.New("shared Skill placement was revoked")
	checks := 0
	runtime := orchestration.ReactRuntime{
		Model: model,
		Tools: tools,
		PreToolUse: func(
			context.Context,
			assistant.AssistantTurn,
			orchestration.SkillSelection,
			string,
			toolpkg.Metadata,
		) error {
			checks++
			if checks == 1 {
				return nil
			}
			return revoked
		},
	}
	_, err := runtime.Run(
		t.Context(),
		assistant.AssistantTurn{
			TurnID: "arn_revoked_before_tool",
			Input:  assistant.AssistantTurnInput{Text: "明早九点提醒我"},
		},
		orchestration.SkillSelection{
			SkillID:      "calendar_task",
			ToolPolicy:   []string{"calendar_create_reminder"},
			MaxToolCalls: 1,
		},
	)
	if !errors.Is(err, revoked) || tools.executions != 0 || checks != 2 {
		t.Fatalf("error=%v tool executions=%d policy checks=%d", err, tools.executions, checks)
	}
}

func TestAgentLoopProjectsCanonicalConnectorCapabilityFailure(t *testing.T) {
	tools := &countingDeviceActionTools{}
	loop := orchestration.NewAgentLoop(
		calendarDeviceActionSkillRuntime{},
		orchestration.ReactRuntime{Model: &calendarDeviceActionModel{}, Tools: tools},
		nil,
	)
	loop.Catalog = skillfixture.Loader{}
	checks := 0
	loop.ToolAccess = orchestration.ToolExecutionAccessPolicyFunc(func(
		context.Context,
		assistant.AssistantTurn,
		orchestration.SkillSelection,
		string,
		toolpkg.Metadata,
	) error {
		checks++
		// calendar_task exposes app_search and calendar_create_reminder. Both
		// pass the planning boundary; revocation lands before execution.
		if checks <= 2 {
			return nil
		}
		return runerrors.AppErrorFromConnectorCapabilityRequired("calendar connection revoked")
	})
	frozen := testFrozenPolicySelection("assistant-default", "calendar_task", "calendar_task")
	frozen.Template.AllowedTools = []string{"calendar_create_reminder"}
	_, failure, err := loop.RunTurn(t.Context(), assistant.AssistantTurn{
		TurnID: "arn_connector_revoked", SessionID: "session-connector-revoked",
		UserID: "account-1", Input: assistant.AssistantTurnInput{Text: "明早九点提醒我"},
		FrozenPolicySelection: frozen, TraceID: "trace-connector-revoked",
	})
	if err != nil {
		t.Fatal(err)
	}
	if failure == nil || failure.Code != runerrors.ErrConnectorCapabilityRequired.Error() {
		t.Fatalf("failure=%+v", failure)
	}
	if tools.executions != 0 || checks != 3 {
		t.Fatalf("revoked capability executed tool %d time(s), checks=%d", tools.executions, checks)
	}
}

type countingDeviceActionTools struct {
	executions int
}

func (tools *countingDeviceActionTools) ToolMetadata(
	toolName string,
) (toolpkg.Metadata, bool) {
	return toolpkg.LookupCanonicalMetadata(toolName)
}

func (tools *countingDeviceActionTools) ModelToolDeclarations(
	allowed []string,
) []ports.ModelToolDefinition {
	return canonicalTestModelToolDefinitions(allowed)
}

func (tools *countingDeviceActionTools) Execute(
	context.Context,
	orchestration.ToolRequest,
) (orchestration.ToolExecution, error) {
	tools.executions++
	return orchestration.ToolExecution{}, nil
}

func TestCalendarSkillAllowsOnlyCanonicalDeviceActionTool(t *testing.T) {
	catalog, err := skillfixture.Load()
	if err != nil {
		t.Fatalf("load skill catalog: %v", err)
	}
	for _, manifest := range catalog {
		if manifest.SkillID != "calendar_task" {
			continue
		}
		found := false
		for _, toolName := range manifest.ToolPolicy.AllowedTools {
			found = found || toolName == "calendar_create_reminder"
		}
		if !found || !manifest.ToolPolicy.AllowDeviceActionProposal {
			t.Fatalf("calendar tool policy=%+v", manifest.ToolPolicy)
		}
		return
	}
	t.Fatal("calendar_task skill not found")
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-003
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
func TestCalendarContinuationUsesRunIdentityAndRequiresNativeExecutionReceipt(
	t *testing.T,
) {
	runtime := assistantruntest.NewMemoryRuntime()
	commands := runruntime.NewCommandService(
		runtime,
		runruntime.SessionResolverFunc(func(
			context.Context,
			string,
			string,
		) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		time.Now,
		nil,
		runruntime.WithPolicyResolver(runruntime.PolicyResolverFunc(func(
			_ context.Context,
			policyID string,
			_ string,
			_ string,
			_ string,
		) (runruntime.FrozenPolicySelection, error) {
			selection, err := testRunPolicyResolver().ResolveFrozenPolicy(
				t.Context(),
				policyID,
				"persona-device",
				"calendar_task",
				"calendar_task",
			)
			selection.Template.AllowedTools = []string{"calendar_create_reminder"}
			return selection, err
		})),
	)
	registry := canonicalTestToolRegistry(nil)
	model := &calendarDeviceActionModel{}
	loop := orchestration.NewAgentLoop(
		calendarDeviceActionSkillRuntime{},
		orchestration.ReactRuntime{
			Model: model,
			Tools: orchestration.DefaultToolCoordinator{
				Registry: registry,
			},
		},
		nil,
	)
	loop.Catalog = skillfixture.Loader{}
	worker := runruntime.NewDurableWorker(
		runtime,
		runtime,
		orchestration.NewDurableRunExecutor(loop),
		"calendar-device-action-worker",
	)
	workerContext, cancelWorker := context.WithCancel(t.Context())
	defer cancelWorker()
	go worker.Run(workerContext)

	run, err := commands.Start(t.Context(), runruntime.StartCommand{
		UserID:            "user-calendar",
		SessionID:         "session-calendar",
		ClientRequestID:   "calendar-device-action-run",
		TraceID:           "trace-calendar",
		IntentKind:        "answer",
		InputText:         "明早九点提醒我参加产品评审",
		RequestedSkillID:  "calendar_task",
		RequestedDomainID: "calendar_task",
		SurfaceCapabilities: map[string]any{
			"surfaceId":     "assistant_personal",
			"viewportClass": "any",
			"supportedNodeKinds": []string{
				"confirmation_card",
				"comparison_table",
				"action_group",
			},
		},
		ReasoningProfile: generated.AssistantReasoningProfileBalanced,
	})
	if err != nil {
		t.Fatalf("start calendar run: %v", err)
	}
	waiting := waitForCalendarRunState(
		t,
		commands,
		run.RunID,
		generated.AssistantRunStateWaitingApproval,
	)
	toolUseID := waiting.Checkpoint.PendingApprovalRef
	token := calendarContinuationToken(waiting.PresentationDocument)
	if toolUseID == "" || token == "" {
		t.Fatalf(
			"waiting approval is missing continuation identity: checkpoint=%+v presentation=%#v",
			waiting.Checkpoint,
			waiting.PresentationDocument,
		)
	}

	approved, permit, err := commands.ApproveToolUse(
		t.Context(),
		runruntime.ApproveToolUseCommand{
			UserID:           "user-calendar",
			RunID:            run.RunID,
			ToolInvocationID: toolUseID,
			CommandID:        "approve-device-action",
			Decision:         "approved",
			ApprovalPermit:   token,
			InstallationID:   "installation-calendar-1",
			DeviceID:         "device-calendar-1",
		},
	)
	if err != nil || permit == nil ||
		approved.State != generated.AssistantRunStateWaitingExternal {
		t.Fatalf(
			"approval did not yield a pending device permit: run=%+v permit=%+v err=%v",
			approved,
			permit,
			err,
		)
	}

	executedAt := time.Now().UTC()
	continued, err := commands.SubmitDeviceActionReceipt(
		t.Context(),
		runruntime.SubmitDeviceActionReceiptCommand{
			UserID:           "user-calendar",
			RunID:            run.RunID,
			ToolInvocationID: toolUseID,
			CommandID:        toolUseID,
			Receipt: runruntime.DeviceActionExecutionReceipt{
				InstallationID: permit.InstallationID,
				DeviceID:       permit.DeviceID,
				Capability:     permit.Capability,
				InputDigest:    permit.InputDigest,
				Permit:         permit.Permit,
				IdempotencyKey: permit.IdempotencyKey,
				Outcome:        "completed",
				ExecutedAt:     executedAt,
				DeviceObjectID: "calendar-event-1",
			},
		},
	)
	if err != nil {
		t.Fatalf("continue calendar run with native receipt: %v", err)
	}
	if continued.State != generated.AssistantRunStateExecuting {
		t.Fatalf("continued state=%q", continued.State)
	}
	completed := waitForCalendarRunState(
		t,
		commands,
		run.RunID,
		generated.AssistantRunStateCompleted,
	)
	if completed.Checkpoint == nil ||
		len(completed.Checkpoint.DeviceActionReceipts) != 1 ||
		completed.Checkpoint.DeviceActionReceipts[0].DeviceObjectID != "calendar-event-1" {
		t.Fatalf("native execution receipt was not durably preserved: %+v", completed.Checkpoint)
	}

	replayed, err := commands.SubmitDeviceActionReceipt(
		t.Context(),
		runruntime.SubmitDeviceActionReceiptCommand{
			UserID:           "user-calendar",
			RunID:            run.RunID,
			ToolInvocationID: toolUseID,
			CommandID:        toolUseID,
			Receipt: runruntime.DeviceActionExecutionReceipt{
				InstallationID: permit.InstallationID,
				DeviceID:       permit.DeviceID,
				Capability:     permit.Capability,
				InputDigest:    permit.InputDigest,
				Permit:         permit.Permit,
				IdempotencyKey: permit.IdempotencyKey,
				Outcome:        "completed",
				ExecutedAt:     executedAt,
				DeviceObjectID: "calendar-event-1",
			},
		},
	)
	if err != nil || replayed.Checkpoint == nil ||
		len(replayed.Checkpoint.DeviceActionReceipts) != 1 {
		t.Fatalf("idempotent continuation duplicated receipt: run=%+v err=%v", replayed, err)
	}
}

func waitForCalendarRunState(
	t *testing.T,
	commands *runruntime.CommandService,
	runID string,
	expected generated.AssistantRunState,
) runruntime.Run {
	t.Helper()
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		run, err := commands.Get(t.Context(), "user-calendar", runID)
		if err == nil && run.State == expected {
			return run
		}
		time.Sleep(10 * time.Millisecond)
	}
	run, err := commands.Get(t.Context(), "user-calendar", runID)
	var terminalFailure any
	if run.TerminalSnapshot != nil {
		terminalFailure = run.TerminalSnapshot.Failure
	}
	t.Fatalf(
		"run %s did not reach %s: state=%s terminal=%#v failure=%+v err=%v",
		runID,
		expected,
		run.State,
		run.TerminalSnapshot,
		terminalFailure,
		err,
	)
	return runruntime.Run{}
}

func calendarContinuationToken(presentation map[string]any) string {
	for _, node := range presentationNodes(presentation["nodes"]) {
		action, _ := node["action"].(map[string]any)
		approveTool, _ := action["approveTool"].(map[string]any)
		if token, _ := approveTool["approvalPermit"].(string); token != "" {
			return token
		}
	}
	return ""
}

func presentationNodes(value any) []map[string]any {
	switch nodes := value.(type) {
	case []map[string]any:
		return nodes
	case []any:
		result := make([]map[string]any, 0, len(nodes))
		for _, node := range nodes {
			if object, ok := node.(map[string]any); ok {
				result = append(result, object)
			}
		}
		return result
	default:
		return nil
	}
}
