package application

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

func testToolTurn() assistant.AssistantTurn {
	return assistant.AssistantTurn{
		TurnID:         "atn_tool_test",
		ConversationID: "acv_tool_test",
		UserID:         "user_tool_test",
		TurnType:       "user",
		Status:         "running",
		Input:          assistant.AssistantTurnInput{Text: "检索 AI 芯片新闻"},
		Trigger:        assistant.AssistantTurnTrigger{Type: "user_message"},
		TraceID:        "trace_tool_test",
		CreatedAt:      time.Date(2026, 4, 29, 5, 0, 0, 0, time.UTC),
	}
}

func TestDefaultToolCoordinatorExecutesCloudToolAdapters(t *testing.T) {
	coordinator := DefaultToolCoordinator{
		Now: func() time.Time { return time.Date(2026, 4, 29, 5, 0, 0, 0, time.UTC) },
	}
	for _, toolName := range []string{"web_search", "app_search"} {
		t.Run(toolName, func(t *testing.T) {
			execution, err := coordinator.Execute(context.Background(), ToolRequest{
				Turn:     testToolTurn(),
				Skill:    SkillSelection{SkillID: "news_briefing", ToolPolicy: []string{toolName}},
				ToolName: toolName,
				Input:    map[string]any{"query": "AI 芯片新闻"},
			})
			if err != nil {
				t.Fatalf("Execute() error = %v", err)
			}
			if execution.Failure != nil {
				t.Fatalf("unexpected failure: %#v", execution.Failure)
			}
			if execution.Requested.ToolName != toolName || execution.Completed.ToolName != toolName {
				t.Fatalf("toolName mismatch: requested=%s completed=%s", execution.Requested.ToolName, execution.Completed.ToolName)
			}
			if execution.Requested.Placement != "cloud" || execution.Completed.Status != "completed" {
				t.Fatalf("execution=%#v", execution)
			}
			if len(execution.Completed.Result) == 0 {
				t.Fatalf("missing tool result")
			}
		})
	}
}

func TestDefaultToolCoordinatorMapsToolValidationFailures(t *testing.T) {
	coordinator := DefaultToolCoordinator{
		Now: func() time.Time { return time.Date(2026, 4, 29, 5, 0, 0, 0, time.UTC) },
	}
	for _, tc := range []struct {
		name     string
		toolName string
		input    map[string]any
	}{
		{name: "missing input", toolName: "web_search", input: map[string]any{}},
		{name: "unregistered", toolName: "not_registered", input: map[string]any{"query": "x"}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			execution, err := coordinator.Execute(context.Background(), ToolRequest{
				Turn:     testToolTurn(),
				Skill:    SkillSelection{SkillID: "news_briefing", ToolPolicy: []string{tc.toolName}},
				ToolName: tc.toolName,
				Input:    tc.input,
			})
			if err != nil {
				t.Fatalf("Execute() error = %v", err)
			}
			if execution.Failure == nil {
				t.Fatalf("expected runtime failure")
			}
			if execution.Completed.Status != "failed" {
				t.Fatalf("completed status=%q", execution.Completed.Status)
			}
			if execution.Completed.Failure == nil {
				t.Fatalf("completed tool use missing failure")
			}
		})
	}
}

func TestDefaultToolCoordinatorCreatesDeviceActionProposal(t *testing.T) {
	coordinator := DefaultToolCoordinator{
		Now: func() time.Time { return time.Date(2026, 4, 29, 5, 0, 0, 0, time.UTC) },
	}
	execution, err := coordinator.Execute(context.Background(), ToolRequest{
		Turn:     testToolTurn(),
		Skill:    SkillSelection{SkillID: "daily_assistant", ToolPolicy: []string{"app_action"}},
		ToolName: "app_action",
		Input: map[string]any{
			"actionType": "navigate_to_page",
			"args":       map[string]any{"routeId": "assistant.personal"},
		},
	})
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if execution.Failure != nil {
		t.Fatalf("unexpected failure: %#v", execution.Failure)
	}
	if execution.Requested.Placement != "device_action" || !execution.Requested.RequiresConfirmation {
		t.Fatalf("requested=%#v", execution.Requested)
	}
	if execution.Completed.Status != "waiting_confirmation" {
		t.Fatalf("completed status=%q", execution.Completed.Status)
	}
	if _, ok := execution.Completed.Result["proposal"].(map[string]any); !ok {
		t.Fatalf("missing proposal result: %#v", execution.Completed.Result)
	}
}
