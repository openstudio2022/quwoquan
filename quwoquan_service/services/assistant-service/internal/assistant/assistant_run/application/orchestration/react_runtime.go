package orchestration

import (
	"context"
	"errors"
	"fmt"
	"strings"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	react "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/reasoning"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

type ReactRuntime struct {
	Model ModelProvider
	Tools ToolExecutor
	// PrePlanAccess 在每次模型调用前重验当前 Skill Setting/
	// Placement。它不依赖工具 metadata，因此零工具 Skill 也不能绕过撤权。
	PrePlanAccess func(
		context.Context,
		assistant.AssistantTurn,
		SkillSelection,
	) error
	// PreToolUse 在每个工具调用的安全边界重新检查动态 Setting、Consent、
	// Placement 与共享资格。它同时用于每轮规划前过滤模型可见工具，
	// 并在执行前二次校验，关闭 plan-to-call 撤权竞态。
	PreToolUse func(
		context.Context,
		assistant.AssistantTurn,
		SkillSelection,
		string,
		toolpkg.Metadata,
	) error
	Planner   react.ReactPlanner
	Reflector react.ReactReflector
	Guard     react.ToolExecutionGuard
	Assessor  react.ToolResultAssessor
	Truncator react.ToolResultTruncator
	Budget    react.Budget
}

type ReactResult struct {
	ReasoningText   string
	ModelDelta      string
	StructuredDelta map[string]any
	Usage           map[string]any
	Tool            ToolExecution
	Steps           []ReactStepResult
	FinalText       string
	FinalStreamed   bool
	StopReason      string
	// AskUser 非空表示该次运行以反问收尾：没有最终回答，等用户补齐关键槽位。
	AskUser          *react.AskUser
	FinalClientTrace map[string]any
}

type ReactStepResult struct {
	Iteration               int
	ReasoningText           string
	ModelDelta              string
	StructuredDelta         map[string]any
	EvidenceModelDelta      string
	EvidenceStructuredDelta map[string]any
	ModelInteractions       []map[string]any
	Decision                react.Decision
	DecisionRejection       *react.ToolDecisionRejection
	Plan                    []react.PlanStep
	Tool                    ToolExecution
	Observation             react.Observation
	ReflectionApplied       bool
	Replan                  bool
	ReplanReason            string
}

func (r ReactRuntime) Run(ctx context.Context, turn assistant.AssistantTurn, skill SkillSelection) (ReactResult, error) {
	return r.RunWithStepSink(ctx, turn, skill, nil)
}

func (r ReactRuntime) RunWithStepSink(ctx context.Context, turn assistant.AssistantTurn, skill SkillSelection, stepSink func(ReactStepResult) error) (ReactResult, error) {
	return r.RunWithSinks(ctx, turn, skill, nil, stepSink)
}

func (r ReactRuntime) RunWithSinks(ctx context.Context, turn assistant.AssistantTurn, skill SkillSelection, reasoningSink func(ReactStepResult) error, stepSink func(ReactStepResult) error) (ReactResult, error) {
	return r.RunWithFinalTextSink(ctx, turn, skill, reasoningSink, stepSink, nil)
}

func (r ReactRuntime) RunWithFinalTextSink(
	ctx context.Context,
	turn assistant.AssistantTurn,
	skill SkillSelection,
	reasoningSink func(ReactStepResult) error,
	stepSink func(ReactStepResult) error,
	finalTextSink func(ports.ModelTextDelta) error,
) (ReactResult, error) {
	model := r.Model
	if model == nil {
		return ReactResult{}, fmt.Errorf("assistant model provider is not configured")
	}
	tools := r.Tools
	if tools == nil {
		tools = DefaultToolCoordinator{}
	}
	budget := r.Budget
	if budget.MaxIterations == 0 {
		budget = skill.Budget()
	}
	executionPolicy, hasExecutionPolicy := executionPolicyFromContext(ctx)
	if hasExecutionPolicy {
		budget = executionPolicy.reactBudget(budget)
	}
	usageBudget := newExecutionUsageBudget(
		ctx,
		executionPolicy,
		hasExecutionPolicy,
	)
	explorationBudget := newExecutionExplorationBudget(
		ctx,
		executionPolicy,
		hasExecutionPolicy,
	)
	planner := r.Planner
	guard := r.Guard
	declaredToolCatalog, err := modelToolDeclarationsFor(tools, skill.ToolPolicy)
	if err != nil {
		return ReactResult{}, err
	}
	runtimeToolMetadata, err := frozenToolMetadataFor(tools, declaredToolCatalog)
	if err != nil {
		return ReactResult{}, err
	}
	assessor := r.Assessor
	truncator := r.Truncator
	reflector := r.Reflector
	contextState, contextCheckpoint, hasContextRuntime :=
		runruntime.RestoreContextExecution(ctx)
	toolHistory := append([]string(nil), contextState.ToolHistory...)
	stepsOut := []ReactStepResult{}
	usage := map[string]any{}
	finalObservation := map[string]any(nil)
	finalReasoningText := ""
	finalModelDelta := ""
	finalStructuredDelta := map[string]any(nil)
	previousObservations := restoredContextObservations(
		contextState,
		contextCheckpoint,
	)
	stopReason := "max_iterations"
	startIteration := contextState.PlanCursor + 1
	if !hasContextRuntime {
		startIteration = 1
	}
	persistContextBoundary := func(
		iteration int,
		toolName string,
		status string,
		summary string,
		reflectionApplied bool,
	) error {
		status = strings.TrimSpace(status)
		if status == "" {
			status = "completed"
		}
		summary = strings.TrimSpace(summary)
		if summary == "" {
			summary = "context boundary completed"
		}
		sourceIDs, navigationDepth := explorationBudget.snapshot()
		contextState.PlanCursor = iteration
		contextState.ToolIteration = len(toolHistory)
		contextState.NavigationDepth = navigationDepth
		contextState.SourceIDs = sourceIDs
		contextState.ToolHistory = append([]string(nil), toolHistory...)
		if reflectionApplied {
			contextState.ReflectionIteration = iteration
		}
		contextState = runruntime.AppendContextObservation(
			contextState,
			runruntime.ContextObservationSnapshot{
				Iteration: iteration,
				ToolName:  toolName,
				Status:    status,
				Summary:   summary,
				SourceIDs: sourceIDs,
			},
		)
		if err := runruntime.PersistContextProgress(ctx, contextState); err != nil {
			return err
		}
		if !runruntime.ContextCompactionDue(ctx) {
			return nil
		}
		response, err := r.compactContext(
			ctx,
			turn,
			skill,
			contextState,
			contextCheckpoint,
			usageBudget,
		)
		if err != nil {
			return err
		}
		usage[fmt.Sprintf("compaction_%d", iteration)] = response.Usage
		contextState, contextCheckpoint, _ =
			runruntime.RestoreContextExecution(ctx)
		previousObservations = restoredContextObservations(
			contextState,
			contextCheckpoint,
		)
		return nil
	}
	for iteration := startIteration; iteration <= budget.MaxIterations; iteration++ {
		authorizationRevalidated := false
		if r.PrePlanAccess != nil {
			if err := r.PrePlanAccess(ctx, turn, skill); err != nil {
				return ReactResult{}, err
			}
			authorizationRevalidated = true
		}
		// Dynamic capability state is evaluated at every planning boundary so a
		// long Run never keeps presenting a tool after Setting/Consent/Connector
		// or surface access was revoked. Execution performs the same check again
		// below, closing the plan-to-call race.
		toolCatalog, runtimeToolPolicy := authorizedModelToolCatalog(
			ctx,
			turn,
			skill,
			declaredToolCatalog,
			runtimeToolMetadata,
			guard,
			r.PreToolUse,
		)
		reasoning := fmt.Sprintf("第 %d 轮：根据 skill=%s 规划工具、评估观察，再决定是否重规划。", iteration, skill.SkillID)
		prePlan, err := runruntime.InvokeExecutionHook(
			ctx,
			runruntime.HookPrePlan,
			"task_root",
			"",
			map[string]any{
				"iteration":                iteration,
				"skillId":                  skill.SkillID,
				"toolNames":                append([]string(nil), runtimeToolPolicy...),
				"prompt":                   reasoning,
				"authorizationRevalidated": authorizationRevalidated,
			},
		)
		if err != nil {
			return ReactResult{}, err
		}
		if err := rejectNonAllowHookDecision(runruntime.HookPrePlan, prePlan); err != nil {
			return ReactResult{}, err
		}
		if transformed := hookString(prePlan.Data, "prompt"); transformed != "" {
			reasoning = transformed
		}
		reasoningResp, err := model.Complete(ctx, frozenPolicyModelRequest(turn, skill, ModelRequest{
			TurnID:               turn.TurnID,
			TraceID:              turn.TraceID,
			SkillID:              skill.SkillID,
			Stage:                "reasoning",
			Prompt:               reasoning,
			Observation:          reasoningObservation(previousObservations),
			ToolCatalog:          toolCatalog,
			UserQuestion:         turn.Input.Text,
			ContextTurns:         turn.ContextTurns,
			ContextSummary:       turn.ContextSummary,
			PageContext:          turn.PageContext,
			IntersectionEvidence: turn.IntersectionEvidence,
			SessionPreferences:   turn.SessionPreferences,
			LongTermPreferences:  turn.LongTermPreferences,
			ContextAssembly:      skill.ContextAssembly,
		}))
		if err != nil {
			return ReactResult{}, err
		}
		if err := usageBudget.consume(reasoningResp); err != nil {
			return ReactResult{}, err
		}
		stepInteractions := collectModelInteraction(reasoningResp)
		contextState.ModelHistory = appendModelHistory(
			contextState.ModelHistory,
			stepInteractions,
		)
		usage[fmt.Sprintf("reasoning_%d", iteration)] = reasoningResp.Usage
		finalReasoningText = reasoning
		finalModelDelta = reasoningResp.Text
		finalStructuredDelta = reasoningResp.StructuredDelta
		decision := planner.Decide(react.PlanInput{
			ReasoningText:   reasoningResp.Text,
			StructuredDelta: reasoningResp.StructuredDelta,
			ToolPolicy:      runtimeToolPolicy,
			Budget: react.Budget{
				MaxIterations: budget.MaxIterations - iteration + 1,
				MaxToolCalls:  budget.MaxToolCalls - len(toolHistory),
			},
		})
		effectiveRepairTools := explorationBudget.repairTools(
			guardAllowedTools(runtimeToolPolicy, guard),
			runtimeToolMetadata,
		)
		if decision.Rejected() {
			decision = decision.RejectTool(
				decision.Rejection.ReasonCode,
				effectiveRepairTools,
			)
		} else if decision.CallsTool() {
			switch {
			case !stringSliceContains(runtimeToolPolicy, decision.ToolName):
				decision = decision.RejectTool(
					"tool_unavailable",
					effectiveRepairTools,
				)
			case guard.Allow(decision.ToolName) != nil:
				decision = decision.RejectTool(
					"tool_not_allowed",
					effectiveRepairTools,
				)
			}
		}
		if decision.CallsTool() {
			metadata := runtimeToolMetadata[decision.ToolName]
			boundedInput, rejectionReason := explorationBudget.prepareTool(
				metadata.Research,
				decision.ToolInput,
			)
			if rejectionReason != "" {
				decision = decision.RejectTool(
					rejectionReason,
					effectiveRepairTools,
				)
			} else {
				decision.ToolInput = boundedInput
			}
		}
		postPlan, err := runruntime.InvokeExecutionHook(
			ctx,
			runruntime.HookPostPlan,
			"task_root",
			decision.ToolName,
			map[string]any{
				"iteration": iteration,
				"skillId":   skill.SkillID,
				"nextAction": func() string {
					switch {
					case decision.CallsTool():
						return "tool_call"
					case decision.AsksUser():
						return "ask_user"
					case decision.Aborts():
						return "abort"
					default:
						return "answer"
					}
				}(),
				"toolName":  decision.ToolName,
				"toolInput": cloneObjectMap(decision.ToolInput),
			},
		)
		if err != nil {
			return ReactResult{}, err
		}
		postPlanRequiresConfirmation := false
		switch postPlan.Decision {
		case runruntime.HookAllow:
		case runruntime.HookBlock:
			return ReactResult{}, hookDecisionError(runruntime.HookPostPlan, postPlan)
		case runruntime.HookRequireConfirmation:
			if !decision.CallsTool() {
				return ReactResult{}, fmt.Errorf(
					"post_plan hook confirmation requires a planned tool call",
				)
			}
			postPlanRequiresConfirmation = true
		}
		if decision.CallsTool() {
			transformedTool := hookString(postPlan.Data, "toolName")
			if transformedTool == "" {
				transformedTool = decision.ToolName
			}
			transformedInput := hookObjectMap(postPlan.Data, "toolInput")
			if transformedInput == nil {
				transformedInput = decision.ToolInput
			}
			if !stringSliceContains(runtimeToolPolicy, transformedTool) ||
				guard.Allow(transformedTool) != nil {
				return ReactResult{}, fmt.Errorf(
					"post_plan hook selected unavailable tool %q",
					transformedTool,
				)
			}
			metadata := runtimeToolMetadata[transformedTool]
			boundedInput, rejectionReason := explorationBudget.prepareTool(
				metadata.Research,
				transformedInput,
			)
			if rejectionReason != "" {
				return ReactResult{}, fmt.Errorf(
					"post_plan hook produced invalid tool input: %s",
					rejectionReason,
				)
			}
			decision.ToolName = transformedTool
			decision.ToolInput = boundedInput
		}
		planned := decision.PlanSteps()
		toolName := decision.ToolName
		toolInput := decision.ToolInput
		if !decision.CallsTool() {
			toolName = ""
			toolInput = nil
		}
		if reasoningSink != nil {
			if err := reasoningSink(ReactStepResult{
				Iteration:         iteration,
				ReasoningText:     reasoning,
				ModelDelta:        reasoningResp.Text,
				StructuredDelta:   reasoningResp.StructuredDelta,
				ModelInteractions: stepInteractions,
				Decision:          decision,
				DecisionRejection: decision.Rejection,
				Plan:              planned,
				Tool: ToolExecution{Requested: assistant.ToolUse{
					ToolName: toolName,
					Input:    toolInput,
				}},
			}); err != nil {
				return ReactResult{}, err
			}
		}
		if decision.AsksUser() {
			askUser := decision.AskUser
			if err := persistContextBoundary(
				iteration,
				"",
				"waiting_user",
				askUserPromptText(askUser),
				false,
			); err != nil {
				return ReactResult{}, err
			}
			return ReactResult{
				ReasoningText:   reasoning,
				ModelDelta:      reasoningResp.Text,
				StructuredDelta: reasoningResp.StructuredDelta,
				Usage:           usage,
				Steps:           stepsOut,
				FinalText:       askUserPromptText(askUser),
				StopReason:      "ask_user_clarification",
				AskUser:         &askUser,
			}, nil
		}
		if decision.Aborts() {
			if err := persistContextBoundary(
				iteration,
				"",
				"aborted",
				"planner stopped execution before a tool call",
				false,
			); err != nil {
				return ReactResult{}, err
			}
			stopReason = "planner_aborted"
			break
		}
		if decision.Rejected() {
			rejectionObservation := toolDecisionRejectionObservation(
				decision.Rejection,
			)
			previousObservations = append(
				previousObservations,
				rejectionObservation,
			)
			replan := decision.Rejection.Retryable && iteration < budget.MaxIterations
			stepOut := ReactStepResult{
				Iteration:         iteration,
				ReasoningText:     reasoning,
				ModelDelta:        reasoningResp.Text,
				StructuredDelta:   reasoningResp.StructuredDelta,
				ModelInteractions: stepInteractions,
				Decision:          decision,
				DecisionRejection: decision.Rejection,
				Plan:              planned,
				Observation: react.Observation{
					Empty:   true,
					Summary: "tool decision rejected before execution",
				},
				Replan:       replan,
				ReplanReason: decision.Rejection.ReasonCode,
			}
			stepsOut = append(stepsOut, stepOut)
			if stepSink != nil {
				if err := stepSink(stepOut); err != nil {
					return ReactResult{}, err
				}
			}
			if err := persistContextBoundary(
				iteration,
				decision.Rejection.RequestedTool,
				"rejected",
				"tool decision rejected: "+decision.Rejection.ReasonCode,
				false,
			); err != nil {
				return ReactResult{}, err
			}
			if replan {
				stopReason = "decision_rejected_replanning"
				continue
			}
			if decision.Rejection.Retryable {
				stopReason = "decision_rejected_budget_exhausted"
			} else {
				stopReason = "decision_rejected"
			}
			break
		}
		if toolName == "" || len(toolHistory) >= budget.MaxToolCalls {
			if err := persistContextBoundary(
				iteration,
				"",
				"answered",
				"model answered without another tool call",
				false,
			); err != nil {
				return ReactResult{}, err
			}
			stopReason = "model_answered_without_tools"
			break
		}
		metadata, found := runtimeToolMetadata[toolName]
		if !found {
			return ReactResult{}, fmt.Errorf(
				"tool %q is absent from the frozen metadata snapshot", toolName,
			)
		}
		toolAuthorizationRevalidated := false
		if r.PreToolUse != nil {
			if err := r.PreToolUse(ctx, turn, skill, toolName, metadata); err != nil {
				return ReactResult{}, err
			}
			toolAuthorizationRevalidated = true
		}
		preTool, err := runruntime.InvokeExecutionHook(
			ctx,
			runruntime.HookPreToolUse,
			plannedToolStepID(planned, toolName),
			toolName,
			map[string]any{
				"iteration":                iteration,
				"skillId":                  skill.SkillID,
				"toolName":                 toolName,
				"toolInput":                cloneObjectMap(toolInput),
				"authorizationRevalidated": toolAuthorizationRevalidated,
			},
		)
		if err != nil {
			return ReactResult{}, err
		}
		preToolRequiresConfirmation := false
		switch preTool.Decision {
		case runruntime.HookAllow:
		case runruntime.HookBlock:
			return ReactResult{}, hookDecisionError(runruntime.HookPreToolUse, preTool)
		case runruntime.HookRequireConfirmation:
			preToolRequiresConfirmation = true
		}
		if transformed := hookObjectMap(preTool.Data, "toolInput"); transformed != nil {
			boundedInput, rejectionReason := explorationBudget.prepareTool(
				metadata.Research,
				transformed,
			)
			if rejectionReason != "" {
				return ReactResult{}, fmt.Errorf(
					"pre_tool_use hook produced invalid tool input: %s",
					rejectionReason,
				)
			}
			toolInput = boundedInput
		}
		hookRequiresConfirmation := postPlanRequiresConfirmation ||
			preToolRequiresConfirmation
		if hookRequiresConfirmation && !metadata.RequiresConfirmation {
			return ReactResult{}, fmt.Errorf(
				"hook confirmation is unsupported for non-confirmable tool %q",
				toolName,
			)
		}
		// Reserve at the final policy/consent boundary. The shared request state
		// prevents parallel Subagents from overcommitting; the durable count is
		// written only after ToolExecutor actually returns.
		toolReservation, err := usageBudget.reserveToolCall()
		if err != nil {
			return ReactResult{}, err
		}
		toolExecution, executionErr := tools.Execute(ctx, ToolRequest{
			Turn:      turn,
			Skill:     skill,
			Iteration: iteration,
			StepID:    plannedToolStepID(planned, toolName),
			ToolName:  toolName,
			Input:     toolInput,
			History:   toolHistory,
			Reasoning: reasoningResp.Text,
		})
		consumptionErr := toolReservation.Commit()
		if executionErr != nil || consumptionErr != nil {
			postTool, hookErr := runruntime.InvokeExecutionHook(
				ctx,
				runruntime.HookPostToolUse,
				plannedToolStepID(planned, toolName),
				toolName,
				map[string]any{
					"iteration": iteration,
					"skillId":   skill.SkillID,
					"toolName":  toolName,
					"status":    "executor_error",
				},
			)
			if hookErr == nil {
				hookErr = rejectNonAllowHookDecision(
					runruntime.HookPostToolUse,
					postTool,
				)
			}
			return ReactResult{}, errors.Join(executionErr, consumptionErr, hookErr)
		}
		if hookRequiresConfirmation &&
			toolExecution.Completed.Status != "waiting_confirmation" {
			return ReactResult{}, fmt.Errorf(
				"confirmable tool %q executed before hook confirmation",
				toolName,
			)
		}
		if toolExecution.Completed.Status != "waiting_confirmation" {
			explorationBudget.commitTool(metadata.Research, toolInput)
		}
		postTool, err := runruntime.InvokeExecutionHook(
			ctx,
			runruntime.HookPostToolUse,
			plannedToolStepID(planned, toolName),
			toolName,
			map[string]any{
				"iteration": iteration,
				"skillId":   skill.SkillID,
				"toolName":  toolName,
				"status":    toolExecution.Completed.Status,
				"result":    cloneObjectMap(toolExecution.Completed.Result),
			},
		)
		if err != nil {
			return ReactResult{}, err
		}
		if err := rejectNonAllowHookDecision(runruntime.HookPostToolUse, postTool); err != nil {
			return ReactResult{}, err
		}
		if transformed := hookObjectMap(postTool.Data, "result"); transformed != nil {
			toolExecution.Completed.Result = transformed
		}
		toolHistory = append(toolHistory, toolName)
		if toolExecution.Failure != nil {
			recovery := toolExecution.RecoveryAction
			if recovery == "" {
				recovery = assistantgenerated.ToolRecoveryActionFailTurn
			}
			stepOut := ReactStepResult{
				Iteration:         iteration,
				ReasoningText:     reasoning,
				ModelDelta:        reasoningResp.Text,
				StructuredDelta:   reasoningResp.StructuredDelta,
				ModelInteractions: stepInteractions,
				Decision:          decision,
				Plan:              planned,
				Tool:              toolExecution,
				Observation:       react.Observation{Empty: true, Summary: "tool failed"},
				Replan:            recovery == assistantgenerated.ToolRecoveryActionSkipTool,
				ReplanReason:      "tool_failed",
			}
			stepsOut = append(stepsOut, stepOut)
			previousObservations = append(previousObservations, map[string]any{
				"tool": toolName, "status": "failed",
				"failure": toolExecution.Completed.Failure,
			})
			if stepSink != nil {
				if err := stepSink(stepOut); err != nil {
					return ReactResult{}, err
				}
			}
			if err := persistContextBoundary(
				iteration,
				toolName,
				"failed",
				"tool execution failed",
				false,
			); err != nil {
				return ReactResult{}, err
			}
			switch recovery {
			case assistantgenerated.ToolRecoveryActionSkipTool:
				// 跳过该工具后继续本轮：预算仍受 MaxIterations / MaxToolCalls 约束。
				stopReason = "tool_skipped"
				continue
			case assistantgenerated.ToolRecoveryActionDegradeAnswer:
				// 带着已有证据进入 final，明确告知用户哪一部分没有拿到。
				stopReason = "tool_failed_degraded_answer"
			default:
				return ReactResult{
					ReasoningText:   reasoning,
					ModelDelta:      reasoningResp.Text,
					StructuredDelta: reasoningResp.StructuredDelta,
					Usage:           usage,
					Tool:            toolExecution,
					Steps:           stepsOut,
					StopReason:      "tool_failed",
				}, nil
			}
			break
		}
		if toolExecution.Completed.Status == "waiting_confirmation" {
			stepOut := ReactStepResult{
				Iteration:         iteration,
				ReasoningText:     reasoning,
				ModelDelta:        reasoningResp.Text,
				StructuredDelta:   reasoningResp.StructuredDelta,
				ModelInteractions: stepInteractions,
				Decision:          decision,
				Plan:              planned,
				Tool:              toolExecution,
				Observation: react.Observation{
					Summary: "device action proposal awaits explicit user confirmation",
				},
			}
			stepsOut = append(stepsOut, stepOut)
			if stepSink != nil {
				if err := stepSink(stepOut); err != nil {
					return ReactResult{}, err
				}
			}
			if err := persistContextBoundary(
				iteration,
				toolName,
				"waiting_confirmation",
				"device action proposal awaits explicit confirmation",
				false,
			); err != nil {
				return ReactResult{}, err
			}
			return ReactResult{
				ReasoningText:   reasoning,
				ModelDelta:      reasoningResp.Text,
				StructuredDelta: reasoningResp.StructuredDelta,
				Usage:           usage,
				Tool:            toolExecution,
				Steps:           stepsOut,
				StopReason:      "waiting_tool_approval",
			}, nil
		}
		toolExecution.Completed.Result = truncator.Truncate(toolExecution.Completed.Result)
		toolExecution.Completed.Result = explorationBudget.boundResult(
			metadata.Research,
			toolExecution.Completed.Result,
		)
		observation := assessor.Assess(toolExecution.Completed.Result)
		finalObservation = toolExecution.Completed.Result
		evidenceObservation := map[string]any{
			"tool":         toolName,
			"toolInput":    toolInput,
			"result":       toolExecution.Completed.Result,
			"observation":  map[string]any{"summary": observation.Summary, "empty": observation.Empty},
			"userQuestion": turn.Input.Text,
		}
		if r.PrePlanAccess != nil {
			if err := r.PrePlanAccess(ctx, turn, skill); err != nil {
				return ReactResult{}, err
			}
		}
		evidenceResp, err := model.Complete(ctx, frozenPolicyModelRequest(turn, skill, ModelRequest{
			TurnID:               turn.TurnID,
			TraceID:              turn.TraceID,
			SkillID:              skill.SkillID,
			Stage:                "evidence_processing",
			Prompt:               "基于工具返回的结构化结果，生成面向用户的证据处理叙事（processingSummary）与要点（selectedKeyPoints）；references 仅摘录你认为可靠且相关的条目。",
			Observation:          evidenceObservation,
			UserQuestion:         turn.Input.Text,
			ContextTurns:         turn.ContextTurns,
			ContextSummary:       turn.ContextSummary,
			PageContext:          turn.PageContext,
			IntersectionEvidence: turn.IntersectionEvidence,
			SessionPreferences:   turn.SessionPreferences,
			LongTermPreferences:  turn.LongTermPreferences,
			ContextAssembly:      skill.ContextAssembly,
		}))
		if err != nil {
			return ReactResult{}, err
		}
		if err := usageBudget.consume(evidenceResp); err != nil {
			return ReactResult{}, err
		}
		usage[fmt.Sprintf("evidence_%d", iteration)] = evidenceResp.Usage
		evidenceInteractions := collectModelInteraction(evidenceResp)
		stepInteractions = append(stepInteractions, evidenceInteractions...)
		contextState.ModelHistory = appendModelHistory(
			contextState.ModelHistory,
			evidenceInteractions,
		)
		remainingBudget := react.Budget{
			MaxIterations: budget.MaxIterations - iteration,
			MaxToolCalls:  budget.MaxToolCalls - len(toolHistory),
		}
		reflectionApplied := !hasExecutionPolicy ||
			len(toolHistory)%executionPolicy.ReflectionEverySteps == 0
		replan := false
		if reflectionApplied {
			replan = reflector.ShouldReplan(observation, remainingBudget)
		}
		reason := replanReason(observation, remainingBudget)
		hasReplanBudget := remainingBudget.MaxIterations > 0 &&
			remainingBudget.MaxToolCalls > 0
		evidenceGap := false
		if sufficient, required, assessmentReason, declared :=
			toolEvidenceAssessment(toolExecution.Completed.Result); declared &&
			(required || !sufficient) {
			evidenceGap = true
			replan = hasReplanBudget
			reason = assessmentReason
		} else if sufficient, declared :=
			evidenceSufficiency(evidenceResp.StructuredDelta); declared {
			evidenceGap = !sufficient
			replan = evidenceGap && hasReplanBudget
			if evidenceGap {
				reason = "evidence_gap"
			}
		}
		if evidenceGap && !hasReplanBudget {
			reason = "evidence_gap_budget_exhausted"
		}
		previousObservations = append(previousObservations, map[string]any{
			"tool":               toolName,
			"toolInput":          toolInput,
			"result":             toolExecution.Completed.Result,
			"evidenceAssessment": evidenceResp.StructuredDelta,
		})
		stepOut := ReactStepResult{
			Iteration:               iteration,
			ReasoningText:           reasoning,
			ModelDelta:              reasoningResp.Text,
			StructuredDelta:         reasoningResp.StructuredDelta,
			EvidenceModelDelta:      evidenceResp.Text,
			EvidenceStructuredDelta: evidenceResp.StructuredDelta,
			ModelInteractions:       stepInteractions,
			Decision:                decision,
			Plan:                    planned,
			Tool:                    toolExecution,
			Observation:             observation,
			ReflectionApplied:       reflectionApplied,
			Replan:                  replan,
			ReplanReason:            reason,
		}
		stepsOut = append(stepsOut, stepOut)
		if stepSink != nil {
			if err := stepSink(stepOut); err != nil {
				return ReactResult{}, err
			}
		}
		if err := persistContextBoundary(
			iteration,
			toolName,
			"completed",
			observation.Summary,
			reflectionApplied,
		); err != nil {
			return ReactResult{}, err
		}
		if !replan {
			if reason == "evidence_gap_budget_exhausted" {
				stopReason = "replan_budget_exhausted"
			} else {
				stopReason = "observation_sufficient"
			}
			break
		}
		stopReason = "replan_budget_exhausted"
	}
	if r.PrePlanAccess != nil {
		if err := r.PrePlanAccess(ctx, turn, skill); err != nil {
			return ReactResult{}, err
		}
	}
	finalObservation = attachContextRecovery(
		finalObservation,
		contextState,
		contextCheckpoint,
	)
	finalRequest := frozenPolicyModelRequest(turn, skill, ModelRequest{
		TurnID:               turn.TurnID,
		TraceID:              turn.TraceID,
		SkillID:              skill.SkillID,
		Stage:                "final",
		Prompt:               "结合工具观察生成最终回答",
		Observation:          buildFinalObservationPayload(finalObservation, stepsOut),
		UserQuestion:         turn.Input.Text,
		ContextTurns:         turn.ContextTurns,
		ContextSummary:       turn.ContextSummary,
		PageContext:          turn.PageContext,
		IntersectionEvidence: turn.IntersectionEvidence,
		ContextAssembly:      skill.ContextAssembly,
		SessionPreferences:   turn.SessionPreferences,
		LongTermPreferences:  turn.LongTermPreferences,
	})
	finalResp, finalStreamed, err := completeFinalModelResponse(ctx, model, finalRequest, finalTextSink)
	if err != nil {
		return ReactResult{}, err
	}
	if !finalAnswerUsable(finalResp) {
		if finalStreamed {
			return ReactResult{}, fmt.Errorf("streamed final answer is not displayable")
		}
		if r.PrePlanAccess != nil {
			if err := r.PrePlanAccess(ctx, turn, skill); err != nil {
				return ReactResult{}, err
			}
		}
		finalResp, err = model.Complete(ctx, frozenPolicyModelRequest(turn, skill, ModelRequest{
			TurnID:               turn.TurnID,
			TraceID:              turn.TraceID,
			SkillID:              skill.SkillID,
			Stage:                "final",
			Prompt:               "上一次 final 输出不可用于展示。请基于同一输入证据重新生成非空 userMarkdown，直接回答用户问题；开头不要提内部证据来源或生成过程。",
			Observation:          buildFinalObservationPayload(finalObservation, stepsOut),
			UserQuestion:         turn.Input.Text,
			ContextTurns:         turn.ContextTurns,
			ContextSummary:       turn.ContextSummary,
			PageContext:          turn.PageContext,
			IntersectionEvidence: turn.IntersectionEvidence,
			ContextAssembly:      skill.ContextAssembly,
			SessionPreferences:   turn.SessionPreferences,
			LongTermPreferences:  turn.LongTermPreferences,
		}))
		if err != nil {
			return ReactResult{}, err
		}
		if err := usageBudget.consume(finalResp); err != nil {
			return ReactResult{}, err
		}
	}
	usage["final"] = finalResp.Usage
	contextState.ModelHistory = appendModelHistory(
		contextState.ModelHistory,
		collectModelInteraction(finalResp),
	)
	if err := runruntime.PersistContextProgress(ctx, contextState); err != nil {
		return ReactResult{}, err
	}
	toolExecution := ToolExecution{}
	if len(stepsOut) > 0 {
		toolExecution = stepsOut[len(stepsOut)-1].Tool
	}
	return ReactResult{
		ReasoningText:    finalReasoningText,
		ModelDelta:       finalModelDelta,
		StructuredDelta:  finalStructuredDelta,
		Usage:            usage,
		Tool:             toolExecution,
		Steps:            stepsOut,
		FinalText:        finalResp.Text,
		FinalStreamed:    finalStreamed,
		StopReason:       stopReason,
		FinalClientTrace: finalResp.ClientModelInteraction,
	}, nil
}
