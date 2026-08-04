package orchestration

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"

	rtfailures "quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/streaming"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	react "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/reasoning"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/streaming"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

// SubagentRun 是一个子代理的执行结果。失败被隔离在这里：单个子代理失败不终止整轮，
// 只让它在聚合里成为阻塞项。
type SubagentRun struct {
	Plan                SubagentPlan
	Selection           SkillSelection
	Result              ReactResult
	ToolNames           []string
	ReferenceCount      int
	RetrievalProcessing map[string]any
	TerminalReceipt     *DurableSubtaskTerminalReceipt
	Err                 error
}

// runSubagentsInParallel 并行执行子代理。每个子代理只看到自己的工具白名单、工具预算与
// 超时；过程事件不在这里发射，避免多个 goroutine 争抢同一条流序号。
func (l *AgentLoop) runSubagentsInParallel(
	ctx context.Context,
	turn assistant.AssistantTurn,
	plans []SubagentPlan,
) []SubagentRun {
	runs := make([]SubagentRun, len(plans))
	type indexedRun struct {
		index int
		run   SubagentRun
	}
	completed := make(chan indexedRun, len(plans))
	for index, plan := range plans {
		go func(index int, plan SubagentPlan) {
			completed <- indexedRun{
				index: index,
				run:   l.runSubagent(ctx, turn, plan),
			}
		}(index, plan)
	}
	// A single Manager goroutine owns the result slice. Child workers never
	// write shared mutable state, even when their model/tool work is parallel.
	for range plans {
		result := <-completed
		runs[result.index] = result.run
	}
	return runs
}

func (l *AgentLoop) runSubagent(
	ctx context.Context,
	turn assistant.AssistantTurn,
	plan SubagentPlan,
) SubagentRun {
	if strings.TrimSpace(turn.ExecutionRunID) == "" {
		return l.executeSubagent(ctx, turn, plan)
	}
	if l == nil || l.DurableSubtasks == nil {
		return SubagentRun{
			Plan: plan,
			Err:  fmt.Errorf("durable subtask coordinator is unavailable"),
		}
	}
	request, err := durableSubtaskRequestFor(turn, plan)
	if err != nil {
		return SubagentRun{Plan: plan, Err: err}
	}
	var liveRun SubagentRun
	receipt, executeErr := l.DurableSubtasks.Execute(
		ctx,
		request,
		func(
			workCtx context.Context,
			_ DurableSubtaskClaim,
		) (DurableSubtaskResult, error) {
			liveRun = l.executeSubagent(workCtx, turn, plan)
			if liveRun.Err != nil {
				return DurableSubtaskResult{}, liveRun.Err
			}
			return durableSubtaskResultFromRun(liveRun), nil
		},
	)
	if strings.TrimSpace(receipt.ReceiptRef) == "" {
		if executeErr != nil {
			liveRun.Plan = plan
			liveRun.Err = executeErr
			return liveRun
		}
		return SubagentRun{
			Plan: plan,
			Err:  fmt.Errorf("durable subtask returned no terminal receipt"),
		}
	}
	recovered, recoveryErr := subagentRunFromTerminal(plan, receipt)
	if recoveryErr != nil {
		recovered.Err = recoveryErr
		return recovered
	}
	if executeErr != nil {
		// The durable receipt owns the public failure. Raw provider/tool errors
		// are logged above and never become Manager synthesis input.
		recovered.Err = fmt.Errorf(
			"durable subtask failed: %s",
			strings.TrimSpace(receipt.FailureCode),
		)
	}
	return recovered
}

func (l *AgentLoop) executeSubagent(
	ctx context.Context,
	turn assistant.AssistantTurn,
	plan SubagentPlan,
) SubagentRun {
	run := SubagentRun{Plan: plan}
	selection, err := l.skillSelectionForSubagent(ctx, turn, plan)
	if err != nil {
		run.Err = err
		return run
	}
	run.Selection = selection
	if selection.ContextAssembly != nil &&
		len(selection.ContextAssembly.FillTasks) > 0 {
		task := selection.ContextAssembly.FillTasks[0]
		run.Result = ReactResult{
			FinalText: strings.TrimSpace(task.Prompt),
			AskUser: &react.AskUser{
				SlotID:      task.SlotID,
				Prompt:      strings.TrimSpace(task.Prompt),
				Required:    task.Required,
				Suggestions: append([]string(nil), task.Suggestions...),
			},
			StopReason: "context_fill_required",
		}
		projectSubagentResult(&run)
		return run
	}
	timeout := time.Duration(plan.TimeoutMs) * time.Millisecond
	if timeout <= 0 {
		timeout = defaultSubagentTimeoutMs * time.Millisecond
	}
	runCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	runCtx = contextWithSubagentExecutionPolicy(runCtx, plan)
	reactRuntime := l.React
	reactRuntime.PrePlanAccess = l.prePlanAccess()
	reactRuntime.PreToolUse = l.preToolUse()
	run.Result, run.Err = reactRuntime.Run(runCtx, turn, selection)
	projectSubagentResult(&run)
	if run.Err != nil {
		log.Printf(
			"assistant agent subagent_failed turnId=%s subagentId=%s err=%v",
			turn.TurnID,
			plan.SubagentID,
			run.Err,
		)
	}
	return run
}

func durableSubtaskRequestFor(
	turn assistant.AssistantTurn,
	plan SubagentPlan,
) (DurableSubtaskRequest, error) {
	runID := strings.TrimSpace(turn.ExecutionRunID)
	idempotencyPrefix := strings.TrimSpace(turn.ClientRequestID)
	skillID := strings.TrimSpace(plan.SkillID)
	subagentID := strings.TrimSpace(plan.SubagentID)
	if runID == "" || idempotencyPrefix == "" || skillID == "" ||
		subagentID == "" {
		return DurableSubtaskRequest{}, fmt.Errorf(
			"durable subtask requires frozen run and plan identity",
		)
	}
	processID := fmt.Sprintf(
		"%s:%s",
		subagentID,
		assistantgenerated.PlannerPhaseIdExecuting.WireName(),
	)
	frozen := struct {
		RunID           string   `json:"runId"`
		TaskID          string   `json:"taskId"`
		SubagentID      string   `json:"subagentId"`
		SkillID         string   `json:"skillId"`
		DomainID        string   `json:"domainId"`
		ProblemClass    string   `json:"problemClass"`
		Goal            string   `json:"goal"`
		Role            string   `json:"role"`
		MaxIterations   int      `json:"maxIterations"`
		ToolBudget      int      `json:"toolBudget"`
		ToolWhitelist   []string `json:"toolWhitelist"`
		SearchIntensity string   `json:"searchIntensity"`
		TimeoutMs       int      `json:"timeoutMs"`
		TokenBudget     int64    `json:"tokenBudget"`
		CostUnitBudget  int64    `json:"costUnitBudget"`
		SourceBudget    int      `json:"sourceBudget"`
	}{
		RunID:           runID,
		TaskID:          idempotencyPrefix + ":task:" + processID,
		SubagentID:      subagentID,
		SkillID:         skillID,
		DomainID:        strings.TrimSpace(plan.DomainID),
		ProblemClass:    strings.TrimSpace(plan.ProblemClass),
		Goal:            strings.TrimSpace(plan.Goal),
		Role:            strings.TrimSpace(plan.Role),
		MaxIterations:   plan.MaxIterations,
		ToolBudget:      plan.ToolBudget,
		ToolWhitelist:   append([]string(nil), plan.ToolWhitelist...),
		SearchIntensity: strings.TrimSpace(plan.SearchIntensity),
		TimeoutMs:       plan.TimeoutMs,
		TokenBudget:     plan.TokenBudget,
		CostUnitBudget:  plan.CostUnitBudget,
		SourceBudget:    plan.SourceBudget,
	}
	encoded, err := json.Marshal(frozen)
	if err != nil {
		return DurableSubtaskRequest{}, err
	}
	digest := sha256.Sum256(encoded)
	return DurableSubtaskRequest{
		RunID:       runID,
		TaskID:      frozen.TaskID,
		OwnerAgent:  "subagent:" + skillID,
		InputDigest: "sha256:" + hex.EncodeToString(digest[:]),
	}, nil
}

func projectSubagentResult(run *SubagentRun) {
	if run == nil {
		return
	}
	toolNames := []string{}
	seenTools := map[string]struct{}{}
	referenceCount := 0
	processing := map[string]any{}
	for _, step := range run.Result.Steps {
		if toolName := strings.TrimSpace(step.Tool.Requested.ToolName); toolName != "" {
			if _, duplicate := seenTools[toolName]; !duplicate {
				seenTools[toolName] = struct{}{}
				toolNames = append(toolNames, toolName)
			}
		}
		processing = buildRetrievalProcessingForStep(step)
		referenceCount += intValue(processing["acceptedDocumentCount"])
	}
	run.ToolNames = toolNames
	run.ReferenceCount = referenceCount
	run.RetrievalProcessing = cloneSubtaskPayload(processing)
}

func durableSubtaskResultFromRun(run SubagentRun) DurableSubtaskResult {
	summary := firstLine(run.Result.FinalText)
	if summary == "" && run.Result.AskUser != nil {
		summary = firstLine(run.Result.AskUser.Prompt)
	}
	if summary == "" {
		summary = "subagent completed without a final answer"
	}
	payload := map[string]any{
		"finalText":           strings.TrimSpace(run.Result.FinalText),
		"stopReason":          strings.TrimSpace(run.Result.StopReason),
		"toolNames":           append([]string(nil), run.ToolNames...),
		"referenceCount":      run.ReferenceCount,
		"retrievalProcessing": cloneSubtaskPayload(run.RetrievalProcessing),
	}
	if ask := askUserPayload(run.Result.AskUser); ask != nil {
		payload["askUser"] = ask
	}
	return DurableSubtaskResult{
		Outcome: DurableSubtaskCompleted,
		Summary: summary,
		Payload: payload,
	}
}

func subagentRunFromTerminal(
	plan SubagentPlan,
	receipt DurableSubtaskTerminalReceipt,
) (SubagentRun, error) {
	run := SubagentRun{
		Plan:            plan,
		TerminalReceipt: &receipt,
	}
	if receipt.Outcome != DurableSubtaskCompleted &&
		receipt.Outcome != DurableSubtaskFailed {
		return run, fmt.Errorf("durable subtask receipt is not terminal")
	}
	payload := cloneSubtaskPayload(receipt.Payload)
	run.Result.FinalText = strings.TrimSpace(stringValue(payload["finalText"]))
	run.Result.StopReason = strings.TrimSpace(stringValue(payload["stopReason"]))
	run.ToolNames = stringSliceFromAny(payload["toolNames"])
	run.ReferenceCount = intValue(payload["referenceCount"])
	if processing, ok := payload["retrievalProcessing"].(map[string]any); ok {
		run.RetrievalProcessing = cloneSubtaskPayload(processing)
	}
	if rawAsk, ok := payload["askUser"].(map[string]any); ok {
		required, _ := rawAsk["required"].(bool)
		run.Result.AskUser = &react.AskUser{
			SlotID:      strings.TrimSpace(stringValue(rawAsk["slotId"])),
			Prompt:      strings.TrimSpace(stringValue(rawAsk["prompt"])),
			Required:    required,
			Suggestions: stringSliceFromAny(rawAsk["suggestions"]),
		}
	}
	if receipt.Outcome == DurableSubtaskFailed {
		run.Err = fmt.Errorf(
			"durable subtask failed: %s",
			strings.TrimSpace(receipt.FailureCode),
		)
	}
	return run, nil
}

// subagentPlans 只在配置了编排器时判定多技能；未配置或判定为单技能时返回空。
func (l *AgentLoop) subagentPlans(
	ctx context.Context,
	turn assistant.AssistantTurn,
	primary SkillSelection,
) []SubagentPlan {
	if l == nil || l.Subagents == nil {
		return nil
	}
	plans, err := l.Subagents.PlanSubagents(ctx, turn, primary)
	if err != nil {
		log.Printf("assistant agent subagent_plan_error turnId=%s err=%v", turn.TurnID, err)
		return nil
	}
	policy, ok := executionPolicyFromContext(ctx)
	if !ok {
		if len(plans) > maxSubagentPlans {
			plans = plans[:maxSubagentPlans]
		}
		return cloneSubagentPlans(plans)
	}
	return boundedSubagentPlans(plans, policy)
}

func boundedSubagentPlans(
	plans []SubagentPlan,
	policy AgentExecutionPolicy,
) []SubagentPlan {
	limit := policy.maxSubagentCount(len(plans))
	if limit <= 0 {
		return nil
	}
	plans = cloneSubagentPlans(plans[:limit])
	remainingTools := policy.MaxToolCalls
	remainingTokens := policy.MaxTokens
	remainingCostUnits := policy.MaxCostUnits
	remainingSources := policy.MaxSources
	for index := range plans {
		remainingPlans := len(plans) - index
		allocation := 0
		if remainingPlans > 0 && remainingTools > 0 {
			allocation = remainingTools / remainingPlans
			if allocation == 0 {
				allocation = 1
			}
		}
		if plans[index].ToolBudget <= 0 || plans[index].ToolBudget > allocation {
			plans[index].ToolBudget = allocation
		}
		if plans[index].ToolBudget < 0 {
			plans[index].ToolBudget = 0
		}
		plans[index].MaxIterations = plans[index].ToolBudget + 1
		plans[index].TokenBudget = boundedSubagentInt64Allocation(
			remainingTokens,
			remainingPlans,
		)
		plans[index].CostUnitBudget = boundedSubagentInt64Allocation(
			remainingCostUnits,
			remainingPlans,
		)
		plans[index].SourceBudget = boundedSubagentIntAllocation(
			remainingSources,
			remainingPlans,
		)
		remainingTools -= plans[index].ToolBudget
		remainingTokens -= plans[index].TokenBudget
		remainingCostUnits -= plans[index].CostUnitBudget
		remainingSources -= plans[index].SourceBudget
		if remainingTools < 0 {
			remainingTools = 0
		}
	}
	return plans
}

func boundedSubagentIntAllocation(remaining int, branches int) int {
	if remaining <= 0 || branches <= 0 {
		return 0
	}
	allocation := remaining / branches
	if allocation == 0 {
		return 1
	}
	return allocation
}

func boundedSubagentInt64Allocation(remaining int64, branches int) int64 {
	if remaining <= 0 || branches <= 0 {
		return 0
	}
	allocation := remaining / int64(branches)
	if allocation == 0 {
		return 1
	}
	return allocation
}

func contextWithSubagentExecutionPolicy(
	ctx context.Context,
	plan SubagentPlan,
) context.Context {
	policy, ok := executionPolicyFromContext(ctx)
	if !ok {
		return ctx
	}
	if plan.ToolBudget < policy.MaxToolCalls {
		policy.MaxToolCalls = plan.ToolBudget
	}
	if plan.TokenBudget < policy.MaxTokens {
		policy.MaxTokens = plan.TokenBudget
	}
	if plan.CostUnitBudget < policy.MaxCostUnits {
		policy.MaxCostUnits = plan.CostUnitBudget
	}
	if plan.SourceBudget < policy.MaxSources {
		policy.MaxSources = plan.SourceBudget
	}
	policy.MaxSubagents = 0
	return withExecutionPolicyValue(ctx, policy)
}

func cloneSubagentPlans(plans []SubagentPlan) []SubagentPlan {
	cloned := make([]SubagentPlan, len(plans))
	for index, plan := range plans {
		cloned[index] = plan
		cloned[index].ToolWhitelist = append([]string(nil), plan.ToolWhitelist...)
	}
	return cloned
}

// streamMultiSkillTurn 走并行子代理通道：派发、隔离执行、聚合裁决、合成回答。
func (l *AgentLoop) streamMultiSkillTurn(
	ctx context.Context,
	turn assistant.AssistantTurn,
	primary SkillSelection,
	plans []SubagentPlan,
	projector *assistantstreaming.StreamProjector,
	appendEvent func(streaming.Envelope, error) error,
) (*rtfailures.Failure, error) {
	dispatch := assistant.AssistantRunVisibleProcess{
		ProcessID:  userProcessID(assistantgenerated.PlannerPhaseIdDispatching, 0),
		Scope:      assistantUserProcessScopeAggregation,
		Stage:      assistantgenerated.PlannerPhaseIdDispatching.WireName(),
		ActionCode: assistantgenerated.PlannerActionCodeDispatchSubagents.WireName(),
		Status:     assistantUserProcessStatusActive,
		Order:      99,
		SkillID:    primary.SkillID,
		DomainID:   primary.DomainID,
	}
	if err := appendEvent(projector.Event(
		assistantstreaming.AssistantStreamEventProcessAppend,
		userProcessPayload(dispatch),
	)); err != nil {
		return nil, err
	}
	if err := emitSubagentProcessStarts(projector, appendEvent, plans); err != nil {
		return nil, err
	}
	runs := l.runSubagentsInParallel(ctx, turn, plans)
	if err := emitSubagentProcessCompletions(projector, appendEvent, runs); err != nil {
		return nil, err
	}
	dispatch.Status = assistantUserProcessStatusCompleted
	if err := appendEvent(projector.Event(
		assistantstreaming.AssistantStreamEventProcessCommit,
		userProcessPayload(dispatch),
	)); err != nil {
		return nil, err
	}
	outcomes := subagentSkillRunOutcomes(runs)
	aggregation := ResolveAggregation(outcomes)
	if aggregation.FinalAnswerMode == assistantgenerated.FinalAnswerModeBlocked {
		failure := modelFailure("subagent_runtime", firstSubagentError(runs))
		if err := appendEvent(projector.Failure(
			assistantstreaming.AssistantStreamEventFailed,
			map[string]any{"status": "failed"},
			failure,
		)); err != nil {
			return nil, err
		}
		return &failure, nil
	}
	closingPhase := assistantgenerated.PlannerPhaseIdAnswering
	closingAction := assistantgenerated.PlannerActionCodeMergeResults
	answerText := ""
	streamed := false
	var askUser *react.AskUser
	if clarification := firstSubagentClarification(runs); clarification != nil {
		closingPhase = assistantUserProcessPhaseClarifying
		closingAction = assistantgenerated.PlannerActionCodeAskClarification
		askUser = clarification
		answerText = askUserPromptText(*clarification)
	} else {
		merging := assistant.AssistantRunVisibleProcess{
			ProcessID:  userProcessID(assistantgenerated.PlannerPhaseIdMerging, 0),
			Scope:      assistantUserProcessScopeAggregation,
			Stage:      assistantgenerated.PlannerPhaseIdMerging.WireName(),
			ActionCode: assistantgenerated.PlannerActionCodeMergeParallelResult.WireName(),
			Status:     assistantUserProcessStatusActive,
			Order:      998,
			SkillID:    primary.SkillID,
			DomainID:   primary.DomainID,
		}
		if err := appendEvent(projector.Event(
			assistantstreaming.AssistantStreamEventProcessAppend,
			userProcessPayload(merging),
		)); err != nil {
			return nil, err
		}
		mergeRuntime := l.React
		mergeRuntime.PrePlanAccess = l.prePlanAccess()
		response, didStream, err := mergeRuntime.SynthesizeSubagentAnswer(
			ctx,
			turn,
			primary,
			subagentMergeObservation(runs),
			func(delta ports.ModelTextDelta) error {
				return appendEvent(projector.Event(assistantstreaming.AssistantStreamEventAnswerDelta, map[string]any{
					"text": delta.Text,
				}))
			},
		)
		if err != nil {
			failure := modelFailure("subagent_merge", err)
			if appendErr := appendEvent(projector.Failure(
				assistantstreaming.AssistantStreamEventFailed,
				map[string]any{"status": "failed"},
				failure,
			)); appendErr != nil {
				return nil, appendErr
			}
			return &failure, nil
		}
		merging.Status = assistantUserProcessStatusCompleted
		if err := appendEvent(projector.Event(
			assistantstreaming.AssistantStreamEventProcessCommit,
			userProcessPayload(merging),
		)); err != nil {
			return nil, err
		}
		answerText = response.Text
		streamed = didStream
	}
	closing := assistant.AssistantRunVisibleProcess{
		ProcessID:  userProcessID(closingPhase, 0),
		Scope:      assistantUserProcessScopeAggregation,
		Stage:      closingPhase.WireName(),
		ActionCode: closingAction.WireName(),
		Status:     assistantUserProcessStatusActive,
		Order:      999,
		SkillID:    primary.SkillID,
		DomainID:   primary.DomainID,
	}
	if err := appendEvent(projector.Event(
		assistantstreaming.AssistantStreamEventProcessAppend,
		userProcessPayload(closing),
	)); err != nil {
		return nil, err
	}
	if !streamed {
		if err := appendEvent(projector.Event(assistantstreaming.AssistantStreamEventAnswerDelta, map[string]any{
			"text": answerText,
		})); err != nil {
			return nil, err
		}
	}
	closing.Status = assistantUserProcessStatusCompleted
	if err := appendEvent(projector.Event(
		assistantstreaming.AssistantStreamEventProcessCommit,
		userProcessPayload(closing),
	)); err != nil {
		return nil, err
	}
	payload := map[string]any{
		"status":            "completed",
		"finalAnswer":       answerText,
		"emergedTags":       []map[string]any{},
		"policyAttribution": boundedPolicyAttribution(turn),
		"messageKind":       aggregation.MessageKind().WireName(),
		"finalAnswerMode":   aggregation.FinalAnswerMode.WireName(),
		"aggregationState":  aggregation.payload(),
		"skillRuns":         skillRunPayloads(outcomes),
		"subagentPlan":      subagentPlanPayloads(plans),
	}
	if ask := askUserPayload(askUser); ask != nil {
		payload["askUser"] = ask
	}
	if err := appendEvent(projector.Event(assistantstreaming.AssistantStreamEventCompleted, payload)); err != nil {
		return nil, err
	}
	return nil, nil
}

func firstSubagentClarification(runs []SubagentRun) *react.AskUser {
	for _, run := range runs {
		if run.Err == nil && run.Result.AskUser != nil {
			return run.Result.AskUser
		}
	}
	return nil
}

func firstSubagentError(runs []SubagentRun) error {
	for _, run := range runs {
		if run.Err != nil {
			return run.Err
		}
	}
	return fmt.Errorf("no subagent produced a usable answer")
}

func subagentPlanPayloads(plans []SubagentPlan) []map[string]any {
	payloads := make([]map[string]any, 0, len(plans))
	for _, plan := range plans {
		payloads = append(payloads, map[string]any{
			"subagentId":    plan.SubagentID,
			"skillId":       plan.SkillID,
			"domainId":      plan.DomainID,
			"problemClass":  plan.ProblemClass,
			"goal":          plan.Goal,
			"role":          plan.Role,
			"maxIterations": plan.MaxIterations,
			"toolBudget":    plan.ToolBudget,
			"toolWhitelist": plan.ToolWhitelist,
			"timeoutMs":     plan.TimeoutMs,
		})
	}
	return payloads
}

// skillSelectionForSubagent 在冻结策略的话术之上叠加该子任务的技能话术与目标。
func (l *AgentLoop) skillSelectionForSubagent(
	ctx context.Context,
	turn assistant.AssistantTurn,
	plan SubagentPlan,
) (SkillSelection, error) {
	base, err := skillSelectionFromFrozenPolicy(turn)
	if err != nil {
		return SkillSelection{}, err
	}
	manifest, found, err := l.resolveSkillManifest(ctx, plan.SkillID)
	if err != nil {
		return SkillSelection{}, err
	}
	if !found {
		return SkillSelection{}, fmt.Errorf("subagent skill %q has no manifest", plan.SkillID)
	}
	selection := SkillSelection{
		SkillID:         plan.SkillID,
		DomainID:        plan.DomainID,
		DisplayName:     manifest.DisplayName,
		ToolPolicy:      append([]string{}, plan.ToolWhitelist...),
		PromptPolicy:    base.PromptPolicy,
		PromptAssetIDs:  append([]string{}, manifest.PromptAssets...),
		SearchIntensity: base.SearchIntensity,
		ProblemClass:    manifest.ProblemClass,
		SlotSchema:      manifest.SlotSchema,
		MaxToolCalls:    plan.ToolBudget,
	}
	guidance, err := resolveSkillPromptGuidance(ctx, l.PromptAssets, manifest)
	if err != nil {
		return SkillSelection{}, err
	}
	selection.PromptPolicy = composePromptPolicy(selection.PromptPolicy, guidance)
	if goal := strings.TrimSpace(plan.Goal); goal != "" {
		selection.PromptPolicy = composePromptPolicy(
			selection.PromptPolicy,
			"该子任务只需完成一件事："+goal,
		)
	}
	assembly, err := l.assembleContext(ctx, turn, selection)
	if err != nil {
		return SkillSelection{}, err
	}
	selection.ContextAssembly = &assembly
	return selection, nil
}

func subagentSkillRunOutcomes(runs []SubagentRun) []SkillRunOutcome {
	outcomes := make([]SkillRunOutcome, 0, len(runs))
	for index, run := range runs {
		skill := run.Selection
		if strings.TrimSpace(skill.SkillID) == "" {
			skill = SkillSelection{
				SkillID:      run.Plan.SkillID,
				DomainID:     run.Plan.DomainID,
				ProblemClass: run.Plan.ProblemClass,
			}
		}
		outcome := skillRunOutcomeFrom(skillRunID(index, run.Plan.SkillID), skill, run.Result)
		outcome.Goal = run.Plan.Goal
		outcome.Role = run.Plan.Role
		outcome.ToolNames = append([]string(nil), run.ToolNames...)
		outcome.ReferenceCount = run.ReferenceCount
		if run.Err != nil {
			outcome.AnswerReady = false
			outcome.ResultSummary = ""
			outcome.StopReason = "subagent_failed"
		}
		outcomes = append(outcomes, outcome)
	}
	return outcomes
}

// subagentMergeObservation 只把子代理的可展示结论与检索处理交给合成阶段，不外传工具输入
// 与模型推理。
func subagentMergeObservation(runs []SubagentRun) map[string]any {
	entries := make([]map[string]any, 0, len(runs))
	references := []map[string]any{}
	for _, run := range runs {
		entry := map[string]any{
			"skillId": run.Plan.SkillID,
			"goal":    run.Plan.Goal,
			"role":    run.Plan.Role,
		}
		if run.Err != nil {
			entry["unavailableReason"] = "subagent_failed"
			entries = append(entries, entry)
			continue
		}
		entry["answer"] = strings.TrimSpace(run.Result.FinalText)
		if len(run.RetrievalProcessing) > 0 {
			processing := run.RetrievalProcessing
			entry["keyPoints"] = processing["selectedKeyPoints"]
			if accepted, ok := processing["acceptedReferences"].([]map[string]any); ok {
				references = MergeReferences(references, accepted)
			}
		}
		entries = append(entries, entry)
	}
	return map[string]any{
		"subagentRuns": entries,
		"retrievalProcessing": map[string]any{
			"acceptedReferences": references,
		},
	}
}

// emitSubagentProcessStarts first persists every sibling as active. Their
// TaskGraph nodes therefore share one predecessor frontier instead of being
// serialized merely because completion events are projected in a stable order.
func emitSubagentProcessStarts(
	projector *assistantstreaming.StreamProjector,
	appendEvent func(streaming.Envelope, error) error,
	plans []SubagentPlan,
) error {
	for index, plan := range plans {
		process := assistant.AssistantRunVisibleProcess{
			ProcessID: fmt.Sprintf(
				"%s:%s",
				plan.SubagentID,
				assistantgenerated.PlannerPhaseIdExecuting.WireName(),
			),
			Scope:      assistantUserProcessScopeSkill,
			Stage:      assistantgenerated.PlannerPhaseIdExecuting.WireName(),
			ActionCode: assistantgenerated.PlannerActionCodeParallelProbe.WireName(),
			Status:     assistantUserProcessStatusActive,
			Order:      100 + index,
			Summary:    userProcessSummary(plan.Goal),
			SkillID:    plan.SkillID,
			DomainID:   plan.DomainID,
		}
		if err := appendEvent(projector.Event(
			assistantstreaming.AssistantStreamEventProcessAppend,
			userProcessPayload(process),
		)); err != nil {
			return err
		}
	}
	return nil
}

// emitSubagentProcessCompletions closes the already-persisted sibling tasks in
// plan order after the bounded parallel executions have joined.
func emitSubagentProcessCompletions(
	projector *assistantstreaming.StreamProjector,
	appendEvent func(streaming.Envelope, error) error,
	runs []SubagentRun,
) error {
	for index, run := range runs {
		status := assistantUserProcessStatusCompleted
		if run.Err != nil || strings.TrimSpace(run.Result.FinalText) == "" {
			status = assistantUserProcessStatusFailed
		}
		process := assistant.AssistantRunVisibleProcess{
			ProcessID:  fmt.Sprintf("%s:%s", run.Plan.SubagentID, assistantgenerated.PlannerPhaseIdExecuting.WireName()),
			Scope:      assistantUserProcessScopeSkill,
			Stage:      assistantgenerated.PlannerPhaseIdExecuting.WireName(),
			ActionCode: assistantgenerated.PlannerActionCodeParallelProbe.WireName(),
			Status:     status,
			Order:      100 + index,
			Summary:    userProcessSummary(run.Plan.Goal),
			SkillID:    run.Plan.SkillID,
			DomainID:   run.Plan.DomainID,
		}
		if run.Err == nil && len(run.RetrievalProcessing) > 0 {
			processing := run.RetrievalProcessing
			process.SearchedDocumentCount = intValue(processing["searchedDocumentCount"])
			process.ProcessedDocumentCount = intValue(processing["processedDocumentCount"])
			process.AcceptedDocumentCount = intValue(processing["acceptedDocumentCount"])
			process.AcceptedReferences = UserProcessReferences(processing["acceptedReferences"])
		}
		if err := appendEvent(projector.Event(
			assistantstreaming.AssistantStreamEventProcessCommit,
			userProcessPayload(process),
		)); err != nil {
			return err
		}
	}
	return nil
}
