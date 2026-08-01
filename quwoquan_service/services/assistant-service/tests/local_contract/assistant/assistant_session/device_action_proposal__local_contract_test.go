package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	assistantruntest "quwoquan_service/services/assistant-service/tests/support/assistantrun"
)

type calendarDeviceActionModel struct {
	calls int
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

func TestCalendarSkillAllowsOnlyCanonicalDeviceActionTool(t *testing.T) {
	catalog, err := orchestration.LoadAssistantDomainSkillCatalog()
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
		runruntime.SessionAuthorizerFunc(func(
			context.Context,
			string,
			string,
		) error {
			return nil
		}),
		time.Now,
		nil,
	)
	registry := toolpkg.BaseRegistry()
	registry.RegisterDeviceAction(toolpkg.CalendarCreateReminderMetadata())
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
	worker := runruntime.NewDurableWorker(
		runtime,
		runtime,
		orchestration.NewDurableRunExecutorWithPolicyResolver(
			loop,
			func(
				context.Context,
				runruntime.ExecutionRequest,
			) (assistant.AssistantFrozenPolicySelection, error) {
				selection := testFrozenPolicySelection(
					"assistant-default",
					"calendar_task",
					"calendar_task",
				)
				selection.Template.AllowedTools = []string{
					"calendar_create_reminder",
				}
				return selection, nil
			},
		),
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
			"surfaceId":          "assistant_personal",
			"supportedNodeKinds": []string{"confirmation_card", "action_group"},
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

	_, err = commands.ContinueToolUse(
		t.Context(),
		runruntime.ContinueToolUseCommand{
			UserID:            "user-calendar",
			RunID:             run.RunID,
			ToolUseID:         toolUseID,
			CommandID:         "continue-without-receipt",
			Decision:          "approved",
			ContinuationToken: token,
		},
	)
	if !errors.Is(err, runruntime.ErrInvalidRun) {
		t.Fatalf("approval without native receipt err=%v", err)
	}

	executedAt := time.Now().UTC()
	continued, err := commands.ContinueToolUse(
		t.Context(),
		runruntime.ContinueToolUseCommand{
			UserID:            "user-calendar",
			RunID:             run.RunID,
			ToolUseID:         toolUseID,
			CommandID:         "continue-with-receipt",
			Decision:          "approved",
			ContinuationToken: token,
			ExecutionReceipt: &runruntime.DeviceActionExecutionReceipt{
				ActionKind:     "calendar_create_reminder",
				IdempotencyKey: toolUseID,
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

	replayed, err := commands.ContinueToolUse(
		t.Context(),
		runruntime.ContinueToolUseCommand{
			UserID:            "user-calendar",
			RunID:             run.RunID,
			ToolUseID:         toolUseID,
			CommandID:         "continue-with-receipt",
			Decision:          "approved",
			ContinuationToken: token,
			ExecutionReceipt: &runruntime.DeviceActionExecutionReceipt{
				ActionKind:     "calendar_create_reminder",
				IdempotencyKey: toolUseID,
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
	t.Fatalf("run %s did not reach %s: state=%s err=%v", runID, expected, run.State, err)
	return runruntime.Run{}
}

func calendarContinuationToken(presentation map[string]any) string {
	nodes, _ := presentation["nodes"].([]map[string]any)
	for _, node := range nodes {
		action, _ := node["action"].(map[string]any)
		payload, _ := action["payload"].(map[string]any)
		if token, _ := payload["continuationToken"].(string); token != "" {
			return token
		}
	}
	return ""
}
