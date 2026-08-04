package orchestration

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	rtfailures "quwoquan_service/runtime/failures"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

type ToolRequest struct {
	Turn      assistant.AssistantTurn
	Skill     SkillSelection
	Iteration int
	StepID    string
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
	// Registry 是当前进程的 runtime-availability 边界。Canonical catalog 只能
	// 证明工具名已定义，不能证明 handler/device continuation 已经装配。
	return registry.Metadata(toolName)
}

func modelToolDeclarationsFor(
	tools ToolExecutor,
	allowedToolNames []string,
) ([]ports.ModelToolDefinition, error) {
	if len(allowedToolNames) == 0 {
		return nil, nil
	}
	provider, ok := tools.(ToolCatalogProvider)
	if !ok {
		return nil, errors.New(
			"allowed model tools require a runtime catalog provider",
		)
	}
	expected := make(map[string]struct{}, len(allowedToolNames))
	for _, rawName := range allowedToolNames {
		name := strings.TrimSpace(rawName)
		if name == "" {
			return nil, errors.New("allowed model tool has an empty name")
		}
		if _, duplicated := expected[name]; duplicated {
			return nil, fmt.Errorf("allowed model tool %q is duplicated", name)
		}
		expected[name] = struct{}{}
	}
	declarations := provider.ModelToolDeclarations(allowedToolNames)
	declared := make(map[string]struct{}, len(declarations))
	for _, declaration := range declarations {
		name := strings.TrimSpace(declaration.Name)
		if _, allowed := expected[name]; !allowed {
			return nil, fmt.Errorf(
				"runtime catalog declared tool %q outside the frozen allowlist",
				name,
			)
		}
		if _, duplicated := declared[name]; duplicated {
			return nil, fmt.Errorf("runtime catalog declared tool %q more than once", name)
		}
		declared[name] = struct{}{}
	}
	for name := range expected {
		if _, found := declared[name]; !found {
			return nil, fmt.Errorf(
				"allowed model tool %q is unavailable in the runtime catalog",
				name,
			)
		}
	}
	return declarations, nil
}

func frozenToolMetadataFor(
	tools ToolExecutor,
	declarations []ports.ModelToolDefinition,
) (map[string]toolpkg.Metadata, error) {
	if len(declarations) == 0 {
		return map[string]toolpkg.Metadata{}, nil
	}
	provider, ok := tools.(ToolMetadataProvider)
	if !ok {
		return nil, errors.New(
			"declared model tools require a canonical metadata provider",
		)
	}
	frozen := make(map[string]toolpkg.Metadata, len(declarations))
	for _, declaration := range declarations {
		name := strings.TrimSpace(declaration.Name)
		if name == "" {
			return nil, errors.New("model tool declaration has an empty name")
		}
		if _, duplicated := frozen[name]; duplicated {
			return nil, fmt.Errorf("model tool %q is declared more than once", name)
		}
		metadata, found := provider.ToolMetadata(name)
		if !found || strings.TrimSpace(metadata.ToolName) != name {
			return nil, fmt.Errorf(
				"model tool %q has no matching canonical metadata",
				name,
			)
		}
		cloned, err := metadata.Clone()
		if err != nil {
			return nil, err
		}
		frozen[name] = cloned
	}
	return frozen, nil
}

type DefaultToolCoordinator struct {
	Now       func() time.Time
	ForceFail bool
	Registry  toolpkg.Registry
}

func (c DefaultToolCoordinator) Execute(ctx context.Context, req ToolRequest) (ToolExecution, error) {
	now := c.now()
	toolName := strings.TrimSpace(req.ToolName)
	registry := c.Registry
	if registry.IsZero() {
		registry = toolpkg.BaseRegistry()
	}
	meta, registered := registry.Metadata(toolName)
	input := c.rawInput(req)
	placement := toolpkg.PlacementCloud
	requiresConfirmation := false
	if registered {
		input = c.input(req, meta)
		placement = meta.Placement
		requiresConfirmation = meta.RequiresConfirmation
	}
	toolUseID, err := stableToolUseID(req, toolName, input)
	if err != nil {
		return ToolExecution{}, err
	}
	requested := assistant.ToolUse{
		ToolUseID:            toolUseID,
		TurnID:               req.Turn.TurnID,
		ToolName:             toolName,
		Placement:            placement,
		Input:                input,
		Status:               "requested",
		RequiresConfirmation: requiresConfirmation,
		CreatedAt:            now,
	}
	completed := requested
	completedAt := now.Add(2 * time.Millisecond)
	completed.CompletedAt = &completedAt
	if c.ForceFail {
		failure := toolFailure(toolName, meta, errors.New("mock tool forced failure"))
		completed.Status = "failed"
		completed.Failure = &failure
		return ToolExecution{Requested: requested, Completed: completed, Failure: &failure}, nil
	}
	if !registered {
		failure := toolFailure(toolName, toolpkg.Metadata{}, errors.New("tool is not registered"))
		completed := requested
		completed.Status = "failed"
		completed.Failure = &failure
		completedAt := now.Add(2 * time.Millisecond)
		completed.CompletedAt = &completedAt
		return ToolExecution{Requested: requested, Completed: completed, Failure: &failure}, nil
	}
	if err := registry.ValidateInput(toolName, requested.Input); err != nil {
		failure := toolFailure(toolName, meta, err)
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
		ToolUseID:      toolUseID,
		IdempotencyKey: toolUseID,
		ToolName:       toolName,
		Input:          requested.Input,
		History:        append([]string{}, req.History...),
	})
	if err != nil {
		failure := toolFailure(toolName, meta, err)
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

func stableToolUseID(
	req ToolRequest,
	toolName string,
	input map[string]any,
) (string, error) {
	executionScope := strings.TrimSpace(req.Turn.ClientRequestID)
	if executionScope == "" {
		if runID := strings.TrimSpace(req.Turn.ExecutionRunID); runID != "" {
			executionScope = "run:" + runID
		} else if turnID := strings.TrimSpace(req.Turn.TurnID); turnID != "" {
			executionScope = "turn:" + turnID
		}
	}
	if executionScope == "" {
		return "", errors.New("tool execution identity is missing run/turn scope")
	}
	iteration := req.Iteration
	if iteration <= 0 {
		iteration = 1
	}
	stepID := strings.TrimSpace(req.StepID)
	if stepID == "" {
		stepID = "tool:1"
	}
	payload, err := json.Marshal(struct {
		ExecutionScope string         `json:"executionScope"`
		Iteration      int            `json:"iteration"`
		StepID         string         `json:"stepId"`
		ToolName       string         `json:"toolName"`
		Input          map[string]any `json:"input"`
	}{
		ExecutionScope: executionScope,
		Iteration:      iteration,
		StepID:         stepID,
		ToolName:       strings.TrimSpace(toolName),
		Input:          input,
	})
	if err != nil {
		return "", fmt.Errorf("encode canonical tool identity: %w", err)
	}
	digest := sha256.Sum256(append([]byte("assistant-tool-use\x00"), payload...))
	// ToolUse uses the registered tu_ identity family. The 104-bit digest is
	// rendered as 26 uppercase hex characters, which is a legal Crockford ULID
	// suffix while remaining stable across process and provider retries.
	return "tu_" + strings.ToUpper(hex.EncodeToString(digest[:13])), nil
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
	out := c.rawInput(req)
	if req.Input == nil {
		for _, field := range metadata.RequiredInputKeys() {
			if field == "query" {
				out[field] = req.Turn.Input.Text
			}
		}
	}
	availableServerInputs := map[string]any{
		"runId":   assistantContinuationRunID(req.Turn),
		"skillId": req.Skill.SkillID,
	}
	for _, field := range metadata.ServerInjectedInputs {
		if value, available := availableServerInputs[field]; available {
			out[field] = value
		}
	}
	return out
}

func (c DefaultToolCoordinator) rawInput(req ToolRequest) map[string]any {
	out := map[string]any{}
	for key, value := range req.Input {
		out[key] = value
	}
	if req.Input == nil && strings.TrimSpace(req.Turn.Input.Text) != "" {
		out["query"] = req.Turn.Input.Text
	}
	return out
}

func toolFailure(
	toolName string,
	metadata toolpkg.Metadata,
	cause error,
) rtfailures.Failure {
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
		if configured := strings.TrimSpace(metadata.Failure.ProviderFailureCode); configured != "" {
			code = configured
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
