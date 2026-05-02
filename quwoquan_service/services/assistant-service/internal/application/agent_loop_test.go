package application

import (
	"context"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type recordingModelProvider struct {
	calls []ModelRequest
}

func (p *recordingModelProvider) Complete(_ context.Context, req ModelRequest) (ModelResponse, error) {
	p.calls = append(p.calls, req)
	switch req.Stage {
	case "reasoning":
		toolName := "web_search"
		if req.SkillID == "calendar_task" || req.SkillID == "daily_assistant" {
			toolName = "app_search"
		}
		delta := map[string]any{
			"nextAction": "call_tool",
			"toolName":   toolName,
			"toolInput":  map[string]any{"query": "mock"},
			"understandingSnapshot": map[string]any{
				"userFacingSummary":        "录制模型：理解用户问题。",
				"retrievalDesignNarrative": "录制模型：准备检索可验证信息。",
			},
		}
		return ModelResponse{Text: "reasoning-json", StructuredDelta: delta}, nil
	case "evidence_processing":
		delta := map[string]any{
			"retrievalProcessing": map[string]any{
				"processingSummary": "录制模型：证据处理叙事。",
			},
		}
		return ModelResponse{Text: "evidence-json", StructuredDelta: delta}, nil
	case "final":
		return ModelResponse{Text: "最终回答：已结合工具观察完成云端回答。"}, nil
	default:
		return ModelResponse{Text: "模型响应"}, nil
	}
}

func TestAgentLoop_RunTurnStream_CompletesNarrativeAnswer(t *testing.T) {
	now := time.Date(2026, 4, 29, 3, 0, 0, 0, time.UTC)
	model := &recordingModelProvider{}
	loop := NewAgentLoop(
		DefaultSkillRuntime{},
		ReactRuntime{
			Model: model,
			Tools: DefaultToolCoordinator{
				Now: func() time.Time { return now },
			},
		},
		func() time.Time { return now },
	)
	turn := assistant.AssistantTurn{
		TurnID:         "atn_test_m5",
		ConversationID: "acv_test_m5",
		UserID:         "user_m5",
		TurnType:       "user",
		Status:         "running",
		Input:          assistant.AssistantTurnInput{Text: "帮我总结今天的安排"},
		Trigger:        assistant.AssistantTurnTrigger{Type: "user_message"},
		TraceID:        "trace_m5",
		CreatedAt:      now,
	}

	events, failure, err := loop.RunTurn(context.Background(), turn)
	if err != nil {
		t.Fatalf("RunTurn error: %v", err)
	}
	if failure != nil {
		t.Fatalf("failure=%#v", failure)
	}
	if len(events) < 20 {
		t.Fatalf("events=%d, want at least 20", len(events))
	}
	for i, event := range events {
		if event.Seq != uint64(i+1) {
			t.Fatalf("event %d seq=%d", i, event.Seq)
		}
		if event.TraceID != "trace_m5" {
			t.Fatalf("event %d traceId=%q", i, event.TraceID)
		}
	}
	wantEvents := []string{
		"assistant.turn.started",
		"assistant.trace",
		"assistant.trace",
		"assistant.trace",
		"assistant.trace",
		"assistant.trace",
		"assistant.trace",
		"assistant.trace",
		"assistant.journey.updated",
		"assistant.process_timeline.updated",
		"assistant.skill.selected",
		"assistant.reasoning.started",
		"assistant.plan.updated",
		"assistant.model.delta",
		"assistant.search_query.generated",
		"assistant.tool.requested",
		"assistant.tool.completed",
		"assistant.observation.assessed",
		"assistant.answer.delta",
	}
	cursor := 0
	for _, want := range wantEvents {
		found := false
		for cursor < len(events) {
			if events[cursor].Event == want {
				found = true
				cursor++
				break
			}
			cursor++
		}
		if !found {
			t.Fatalf("missing event %q in %#v", want, events)
		}
	}
	if len(model.calls) != 3 {
		t.Fatalf("model calls=%d, want 3", len(model.calls))
	}
	if model.calls[0].Stage != "reasoning" || model.calls[1].Stage != "evidence_processing" || model.calls[2].Stage != "final" {
		t.Fatalf("model stages=%q,%q,%q", model.calls[0].Stage, model.calls[1].Stage, model.calls[2].Stage)
	}
	finalText := ""
	for _, event := range events {
		if event.Event == "assistant.answer.final" {
			finalText, _ = event.Payload["text"].(string)
		}
	}
	if !strings.Contains(finalText, "最终回答") {
		t.Fatalf("final text=%q", finalText)
	}
	var toolUse assistant.ToolUse
	for _, event := range events {
		if event.Event == "assistant.tool.requested" {
			toolUse, _ = event.Payload["toolUse"].(assistant.ToolUse)
			break
		}
	}
	if toolUse.ToolName == "" {
		t.Fatalf("toolUse payload missing")
	}
	if toolUse.Status != "requested" {
		t.Fatalf("toolUse=%#v", toolUse)
	}
}

func TestAgentLoop_RunTurnStream_ToolFailureReturnsRuntimeFailure(t *testing.T) {
	now := time.Date(2026, 4, 29, 3, 10, 0, 0, time.UTC)
	loop := NewAgentLoop(
		DefaultSkillRuntime{},
		ReactRuntime{
			Model: &recordingModelProvider{},
			Tools: DefaultToolCoordinator{
				Now:       func() time.Time { return now },
				ForceFail: true,
			},
		},
		func() time.Time { return now },
	)
	turn := assistant.AssistantTurn{
		TurnID:         "atn_test_fail",
		ConversationID: "acv_test_fail",
		UserID:         "user_m5",
		TurnType:       "user",
		Status:         "running",
		Input:          assistant.AssistantTurnInput{Text: "触发工具失败"},
		Trigger:        assistant.AssistantTurnTrigger{Type: "user_message"},
		TraceID:        "trace_fail",
		CreatedAt:      now,
	}

	events, failure, err := loop.RunTurn(context.Background(), turn)
	if err != nil {
		t.Fatalf("RunTurn error: %v", err)
	}
	if failure == nil {
		t.Fatal("expected failure")
	}
	if got := events[len(events)-1].Event; got != "assistant.turn.failed" {
		t.Fatalf("last event=%q", got)
	}
	if events[len(events)-1].RuntimeFailure == nil {
		t.Fatalf("turn failed event missing runtimeFailure")
	}
}

type structuredToolModelProvider struct {
	toolName  string
	toolInput map[string]any
}

func (p structuredToolModelProvider) Complete(_ context.Context, req ModelRequest) (ModelResponse, error) {
	switch req.Stage {
	case "reasoning":
		return ModelResponse{
			Text: "结构化请求调用工具。",
			StructuredDelta: map[string]any{
				"nextAction": "call_tool",
				"toolName":   p.toolName,
				"toolInput":  p.input(),
				"understandingSnapshot": map[string]any{
					"userFacingSummary":        "结构化模型：问题理解。",
					"retrievalDesignNarrative": "结构化模型：检索设计。",
				},
			},
			FinishReason: "tool_use",
		}, nil
	case "evidence_processing":
		return ModelResponse{
			Text: "结构化证据处理。",
			StructuredDelta: map[string]any{
				"retrievalProcessing": map[string]any{
					"processingSummary": "结构化模型：证据摘要。",
				},
			},
			FinishReason: "stop",
		}, nil
	case "final":
		return ModelResponse{Text: "已结合结构化工具结果回答。", FinishReason: "stop"}, nil
	default:
		return ModelResponse{Text: "ok", FinishReason: "stop"}, nil
	}
}

func (p structuredToolModelProvider) input() map[string]any {
	if p.toolInput != nil {
		return p.toolInput
	}
	return map[string]any{"query": "站内 AI 内容"}
}

func TestReactRuntime_UsesStructuredToolDeltaWithinPolicy(t *testing.T) {
	now := time.Date(2026, 4, 29, 5, 10, 0, 0, time.UTC)
	runtime := ReactRuntime{
		Model: structuredToolModelProvider{toolName: "app_search"},
		Tools: DefaultToolCoordinator{
			Now: func() time.Time { return now },
		},
	}
	result, err := runtime.Run(context.Background(), assistant.AssistantTurn{
		TurnID:         "atn_structured_tool",
		ConversationID: "acv_structured_tool",
		UserID:         "user_structured",
		TurnType:       "user",
		Status:         "running",
		Input:          assistant.AssistantTurnInput{Text: "找站内 AI 内容"},
		Trigger:        assistant.AssistantTurnTrigger{Type: "user_message"},
		TraceID:        "trace_structured_tool",
		CreatedAt:      now,
	}, SkillSelection{
		SkillID:    "content_search",
		DomainID:   "content",
		ToolPolicy: []string{"app_search"},
	})
	if err != nil {
		t.Fatalf("Run() error = %v", err)
	}
	if result.Tool.Requested.ToolName != "app_search" {
		t.Fatalf("toolName=%q", result.Tool.Requested.ToolName)
	}
	if result.Tool.Completed.Status != "completed" {
		t.Fatalf("tool status=%q", result.Tool.Completed.Status)
	}
	if _, ok := result.Tool.Completed.Result["results"]; !ok {
		t.Fatalf("missing app_search results: %#v", result.Tool.Completed.Result)
	}
}

func TestReactRuntime_RejectsStructuredToolOutsidePolicy(t *testing.T) {
	now := time.Date(2026, 4, 29, 5, 11, 0, 0, time.UTC)
	runtime := ReactRuntime{
		Model: structuredToolModelProvider{toolName: "app_search"},
		Tools: DefaultToolCoordinator{
			Now: func() time.Time { return now },
		},
	}
	_, err := runtime.Run(context.Background(), assistant.AssistantTurn{
		TurnID:         "atn_rejected_tool",
		ConversationID: "acv_rejected_tool",
		UserID:         "user_structured",
		TurnType:       "user",
		Status:         "running",
		Input:          assistant.AssistantTurnInput{Text: "找站内 AI 内容"},
		Trigger:        assistant.AssistantTurnTrigger{Type: "user_message"},
		TraceID:        "trace_rejected_tool",
		CreatedAt:      now,
	}, SkillSelection{
		SkillID:    "content_search",
		DomainID:   "content",
		ToolPolicy: []string{"web_search"},
	})
	if err == nil {
		t.Fatalf("expected policy rejection")
	}
}

type staticSkillRuntime struct {
	selection SkillSelection
}

func (r staticSkillRuntime) SelectSkill(context.Context, assistant.AssistantTurn) (SkillSelection, error) {
	return r.selection, nil
}

func TestAgentLoop_RunTurnStream_DeviceActionEmitsConfirmation(t *testing.T) {
	now := time.Date(2026, 4, 29, 5, 20, 0, 0, time.UTC)
	loop := NewAgentLoop(
		staticSkillRuntime{selection: SkillSelection{
			SkillID:    "daily_assistant",
			DomainID:   "assistant",
			ToolPolicy: []string{"app_action"},
		}},
		ReactRuntime{
			Model: structuredToolModelProvider{
				toolName: "app_action",
				toolInput: map[string]any{
					"actionType": "navigate_to_page",
					"args":       map[string]any{"routeId": "assistant.personal"},
				},
			},
			Tools: DefaultToolCoordinator{
				Now: func() time.Time { return now },
			},
		},
		func() time.Time { return now },
	)
	events, failure, err := loop.RunTurn(context.Background(), assistant.AssistantTurn{
		TurnID:         "atn_device_action",
		ConversationID: "acv_device_action",
		UserID:         "user_device_action",
		TurnType:       "user",
		Status:         "running",
		Input:          assistant.AssistantTurnInput{Text: "打开找私助页面"},
		Trigger:        assistant.AssistantTurnTrigger{Type: "user_message"},
		TraceID:        "trace_device_action",
		CreatedAt:      now,
	})
	if err != nil {
		t.Fatalf("RunTurn() error = %v", err)
	}
	if failure != nil {
		t.Fatalf("unexpected failure: %#v", failure)
	}
	found := false
	for _, event := range events {
		if event.EventType == "user_confirmation_requested" {
			found = true
			toolUse, ok := event.Payload["toolUse"].(assistant.ToolUse)
			if !ok {
				t.Fatalf("toolUse payload type=%T", event.Payload["toolUse"])
			}
			if toolUse.Placement != "device_action" || !toolUse.RequiresConfirmation {
				t.Fatalf("toolUse=%#v", toolUse)
			}
		}
	}
	if !found {
		t.Fatalf("missing user_confirmation_requested event in %#v", events)
	}
}
