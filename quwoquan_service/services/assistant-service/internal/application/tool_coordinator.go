package application

import (
	"context"
	"strings"
	"time"

	rtfailures "quwoquan_service/runtime/failures"
	rtid "quwoquan_service/runtime/id"
	toolpkg "quwoquan_service/services/assistant-service/internal/application/tool"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type ToolRequest struct {
	Turn      assistant.AssistantTurn
	Skill     SkillSelection
	ToolName  string
	Input     map[string]any
	History   []string
	Reasoning string
}

type ToolExecution struct {
	Requested assistant.ToolUse
	Completed assistant.ToolUse
	Failure   *rtfailures.Failure
}

type ToolExecutor interface {
	Execute(ctx context.Context, req ToolRequest) (ToolExecution, error)
}

type DefaultToolCoordinator struct {
	Now       func() time.Time
	ForceFail bool
	Registry  toolpkg.Registry
}

func (c DefaultToolCoordinator) Execute(ctx context.Context, req ToolRequest) (ToolExecution, error) {
	now := c.now()
	toolName := strings.TrimSpace(req.ToolName)
	if toolName == "" {
		toolName = "mock_search"
	}
	toolUseID, err := rtid.Generate(rtid.PrefixToolUse)
	if err != nil {
		return ToolExecution{}, err
	}
	requested := assistant.ToolUse{
		ToolUseID: toolUseID,
		TurnID:    req.Turn.TurnID,
		ToolName:  toolName,
		Placement: "cloud",
		Input: map[string]any{
			"query":     req.Turn.Input.Text,
			"reasoning": req.Reasoning,
			"skillId":   req.Skill.SkillID,
		},
		Status:               "requested",
		RequiresConfirmation: false,
		CreatedAt:            now,
	}
	completed := requested
	completedAt := now.Add(2 * time.Millisecond)
	completed.CompletedAt = &completedAt
	if c.ForceFail {
		failure := toolFailure(toolName, "mock tool forced failure")
		completed.Status = "failed"
		completed.Failure = &failure
		return ToolExecution{Requested: requested, Completed: completed, Failure: &failure}, nil
	}
	registry := c.Registry
	if registry.IsZero() {
		registry = toolpkg.DefaultRegistry()
	}
	meta, ok := registry.Metadata(toolName)
	if !ok {
		failure := toolFailure(toolName, "tool is not registered")
		completed := requested
		completed.Status = "failed"
		completed.Failure = &failure
		completedAt := now.Add(2 * time.Millisecond)
		completed.CompletedAt = &completedAt
		return ToolExecution{Requested: requested, Completed: completed, Failure: &failure}, nil
	}
	requested.Placement = meta.Placement
	requested.RequiresConfirmation = meta.RequiresConfirmation
	requested.Input = c.input(req)
	if err := registry.ValidateInput(toolName, requested.Input); err != nil {
		failure := toolFailure(toolName, err.Error())
		completed := requested
		completed.Status = "failed"
		completed.Failure = &failure
		completedAt := now.Add(2 * time.Millisecond)
		completed.CompletedAt = &completedAt
		return ToolExecution{Requested: requested, Completed: completed, Failure: &failure}, nil
	}
	if meta.Placement == toolpkg.PlacementDeviceAction {
		completed := requested
		completed.Status = "waiting_confirmation"
		completed.Result = map[string]any{
			"proposal": map[string]any{
				"toolName":             toolName,
				"placement":            meta.Placement,
				"input":                requested.Input,
				"requiresConfirmation": true,
			},
		}
		return ToolExecution{Requested: requested, Completed: completed}, nil
	}
	completed = requested
	completed.CompletedAt = &completedAt
	result, err := registry.Execute(ctx, toolpkg.Request{
		ToolName: toolName,
		Input:    requested.Input,
		History:  append([]string{}, req.History...),
	})
	if err != nil {
		failure := toolFailure(toolName, err.Error())
		completed.Status = "failed"
		completed.Failure = &failure
		return ToolExecution{Requested: requested, Completed: completed, Failure: &failure}, nil
	}
	completed.Status = "completed"
	completed.Result = result.Output
	return ToolExecution{Requested: requested, Completed: completed}, nil
}

func (c DefaultToolCoordinator) now() time.Time {
	if c.Now != nil {
		return c.Now().UTC()
	}
	return time.Now().UTC()
}

func (c DefaultToolCoordinator) input(req ToolRequest) map[string]any {
	if req.Input != nil {
		out := make(map[string]any, len(req.Input)+2)
		for key, value := range req.Input {
			out[key] = value
		}
		if _, ok := out["skillId"]; !ok {
			out["skillId"] = req.Skill.SkillID
		}
		if _, ok := out["userQuestion"]; !ok {
			out["userQuestion"] = req.Turn.Input.Text
		}
		return out
	}
	return map[string]any{
		"query":     req.Turn.Input.Text,
		"reasoning": req.Reasoning,
		"skillId":   req.Skill.SkillID,
	}
}

func toolFailure(toolName, reason string) rtfailures.Failure {
	return rtfailures.Failure{
		Code:   "ASSISTANT.MIDDLEWARE.tool_unavailable",
		Origin: rtfailures.OriginRemoteDependency,
		Kind:   rtfailures.KindUnavailable,
		Nature: rtfailures.NatureTransient,
		Location: rtfailures.Location{
			BusinessObject: "tool_use",
			FunctionModule: "assistant_tool_coordinator",
		},
		Context: rtfailures.Context{Attributes: []rtfailures.ContextAttribute{
			{Key: "toolName", Value: toolName},
			{Key: "reason", Value: reason},
		}},
	}.Normalized()
}
