package orchestration

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	rtfailures "quwoquan_service/runtime/failures"
	rtid "quwoquan_service/runtime/id"
	runerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_run"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
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
	// RecoveryAction 是该工具元数据声明的失败恢复语义，运行时据此决定是否继续本轮。
	RecoveryAction assistantgenerated.ToolRecoveryAction
}

type ToolExecutor interface {
	Execute(ctx context.Context, req ToolRequest) (ToolExecution, error)
}

// ToolCatalogProvider 让运行时按允许集合取得可提交给模型的工具声明。未实现该接口的
// executor 表示没有可声明工具，运行时据此走结构化输出协议。
type ToolCatalogProvider interface {
	ModelToolDeclarations(allowedToolNames []string) []ports.ModelToolDefinition
}

type ToolMetadataProvider interface {
	ToolMetadata(toolName string) (toolpkg.Metadata, bool)
}

func (c DefaultToolCoordinator) ModelToolDeclarations(
	allowedToolNames []string,
) []ports.ModelToolDefinition {
	declarations := c.Registry.ModelDeclarations(allowedToolNames)
	if len(declarations) == 0 {
		return nil
	}
	definitions := make([]ports.ModelToolDefinition, 0, len(declarations))
	for _, declaration := range declarations {
		definitions = append(definitions, ports.ModelToolDefinition{
			Name:        declaration.Name,
			Description: declaration.Description,
			Parameters:  declaration.Parameters,
		})
	}
	return definitions
}

func (c DefaultToolCoordinator) ToolMetadata(toolName string) (toolpkg.Metadata, bool) {
	registry := c.Registry
	if registry.IsZero() {
		registry = toolpkg.BaseRegistry()
	}
	return registry.Metadata(toolName)
}

func modelToolDeclarationsFor(
	tools ToolExecutor,
	allowedToolNames []string,
) []ports.ModelToolDefinition {
	provider, ok := tools.(ToolCatalogProvider)
	if !ok {
		return nil
	}
	return provider.ModelToolDeclarations(allowedToolNames)
}

type DefaultToolCoordinator struct {
	Now       func() time.Time
	ForceFail bool
	Registry  toolpkg.Registry
}

func (c DefaultToolCoordinator) Execute(ctx context.Context, req ToolRequest) (ToolExecution, error) {
	now := c.now()
	toolName := strings.TrimSpace(req.ToolName)
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
		failure := toolFailure(toolName, errors.New("mock tool forced failure"))
		completed.Status = "failed"
		completed.Failure = &failure
		return ToolExecution{Requested: requested, Completed: completed, Failure: &failure}, nil
	}
	registry := c.Registry
	if registry.IsZero() {
		registry = toolpkg.BaseRegistry()
	}
	meta, ok := registry.Metadata(toolName)
	if !ok {
		failure := toolFailure(toolName, errors.New("tool is not registered"))
		completed := requested
		completed.Status = "failed"
		completed.Failure = &failure
		completedAt := now.Add(2 * time.Millisecond)
		completed.CompletedAt = &completedAt
		return ToolExecution{Requested: requested, Completed: completed, Failure: &failure}, nil
	}
	requested.Placement = meta.Placement
	requested.RequiresConfirmation = meta.RequiresConfirmation
	requested.Input = c.input(req, meta)
	if err := registry.ValidateInput(toolName, requested.Input); err != nil {
		failure := toolFailure(toolName, err)
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
				"confirmation": map[string]any{
					"templateRef":       meta.Confirmation.TemplateRef,
					"title":             meta.Confirmation.Title,
					"description":       meta.Confirmation.Description,
					"completionSummary": meta.Confirmation.CompletionSummary,
					"displayFields":     confirmationDisplayFields(meta.Confirmation.DisplayFields),
				},
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
		failure := toolFailure(toolName, err)
		completed.Status = "failed"
		completed.Failure = &failure
		return ToolExecution{
			Requested:      requested,
			Completed:      completed,
			Failure:        &failure,
			RecoveryAction: toolFailureRecoveryAction(err),
		}, nil
	}
	completed.Status = "completed"
	completed.Result = result.Output
	return ToolExecution{Requested: requested, Completed: completed}, nil
}

func confirmationDisplayFields(fields []toolpkg.ConfirmationDisplayField) []any {
	result := make([]any, 0, len(fields))
	for _, field := range fields {
		result = append(result, map[string]any{
			"inputKey": field.InputKey,
			"label":    field.Label,
		})
	}
	return result
}

func (c DefaultToolCoordinator) now() time.Time {
	if c.Now != nil {
		return c.Now().UTC()
	}
	return time.Now().UTC()
}

func (c DefaultToolCoordinator) input(req ToolRequest, metadata toolpkg.Metadata) map[string]any {
	out := map[string]any{}
	if req.Input != nil {
		for key, value := range req.Input {
			out[key] = value
		}
	} else {
		for _, field := range metadata.RequiredInputKeys() {
			if field == "query" {
				out[field] = req.Turn.Input.Text
			}
		}
	}
	for _, field := range metadata.ServerInjectedInputs {
		switch field {
		case "runId":
			out[field] = req.Turn.TurnID
		case "skillId":
			out[field] = req.Skill.SkillID
		}
	}
	return out
}

func toolFailure(toolName string, cause error) rtfailures.Failure {
	code := "ASSISTANT.MIDDLEWARE.tool_unavailable"
	origin := rtfailures.OriginRemoteDependency
	kind := rtfailures.KindUnavailable
	nature := rtfailures.NatureTransient
	var canonical toolpkg.CanonicalFailure
	if errors.As(cause, &canonical) {
		code = strings.TrimSpace(canonical.Code)
		origin = canonical.Origin
		kind = canonical.Kind
		nature = canonical.Nature
	}
	var providerFailure ports.ProviderFailure
	if code == "ASSISTANT.MIDDLEWARE.tool_unavailable" && errors.As(cause, &providerFailure) {
		switch providerFailure.Capability {
		case "public_search":
			code = runerrors.ErrPublicSearchProviderUnavailable.Error()
		case "weather":
			code = runerrors.ErrWeatherProviderUnavailable.Error()
		case "finance":
			code = runerrors.ErrFinanceProviderUnavailable.Error()
		case "model":
			code = runerrors.ErrModelProviderUnavailable.Error()
		}
	}
	attributes := []rtfailures.ContextAttribute{
		{Key: "toolName", Value: toolName},
		{Key: "reason", Value: safeToolFailureReason(cause)},
	}
	var execution toolpkg.ExecutionFailure
	if errors.As(cause, &execution) {
		attributes = append(
			attributes,
			rtfailures.ContextAttribute{
				Key:   "attempts",
				Value: strconv.Itoa(execution.Attempts),
			},
			rtfailures.ContextAttribute{
				Key:   "recoveryAction",
				Value: string(execution.Recovery.ResolvedAction()),
			},
			rtfailures.ContextAttribute{
				Key:   "disruptionLevel",
				Value: string(execution.Recovery.ResolvedDisruptionLevel()),
			},
		)
		if summary := strings.TrimSpace(execution.Recovery.UserVisibleSummary); summary != "" {
			attributes = append(attributes, rtfailures.ContextAttribute{
				Key:   "userVisibleSummary",
				Value: summary,
			})
		}
	}
	return rtfailures.Failure{
		Code:   code,
		Origin: origin,
		Kind:   kind,
		Nature: nature,
		Location: rtfailures.Location{
			BusinessObject: "tool_use",
			FunctionModule: "assistant_tool_coordinator",
		},
		Context: rtfailures.Context{Attributes: attributes},
	}.Normalized()
}

// toolFailureRecoveryAction 让运行时按工具声明决定失败后走「失败本轮 / 跳过该工具 /
// 降级作答」，默认 fail_turn 保持既有行为。
func toolFailureRecoveryAction(cause error) assistantgenerated.ToolRecoveryAction {
	var execution toolpkg.ExecutionFailure
	if errors.As(cause, &execution) {
		return execution.Recovery.ResolvedAction()
	}
	return assistantgenerated.ToolRecoveryActionFailTurn
}

func safeToolFailureReason(cause error) string {
	var canonical toolpkg.CanonicalFailure
	if errors.As(cause, &canonical) {
		if reason := strings.TrimSpace(canonical.Reason); reason != "" {
			return reason
		}
		return "canonical_failure"
	}
	var providerFailure ports.ProviderFailure
	if errors.As(cause, &providerFailure) {
		return string(providerFailure.Reason)
	}
	return fmt.Sprintf("%T", cause)
}
