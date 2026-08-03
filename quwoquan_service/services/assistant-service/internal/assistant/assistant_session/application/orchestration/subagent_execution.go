package orchestration

import (
	"context"
	"fmt"
	"log"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/streaming"
	"strings"
	"sync"
	"time"

	rtfailures "quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/streaming"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	react "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/reasoning"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
)

// SubagentRun 是一个子代理的执行结果。失败被隔离在这里：单个子代理失败不终止整轮，
// 只让它在聚合里成为阻塞项。
type SubagentRun struct {
	Plan      SubagentPlan
	Selection SkillSelection
	Result    ReactResult
	Err       error
}

// runSubagentsInParallel 并行执行子代理。每个子代理只看到自己的工具白名单、工具预算与
// 超时；过程事件不在这里发射，避免多个 goroutine 争抢同一条流序号。
func (l *AgentLoop) runSubagentsInParallel(
	ctx context.Context,
	turn assistant.AssistantTurn,
	plans []SubagentPlan,
) []SubagentRun {
	runs := make([]SubagentRun, len(plans))
	var wait sync.WaitGroup
	for index, plan := range plans {
		runs[index].Plan = plan
		wait.Add(1)
		go func(index int, plan SubagentPlan) {
			defer wait.Done()
			selection, err := l.skillSelectionForSubagent(ctx, turn, plan)
			if err != nil {
				runs[index].Err = err
				return
			}
			runs[index].Selection = selection
			if selection.ContextAssembly != nil &&
				len(selection.ContextAssembly.FillTasks) > 0 {
				task := selection.ContextAssembly.FillTasks[0]
				runs[index].Result = ReactResult{
					FinalText: strings.TrimSpace(task.Prompt),
					AskUser: &react.AskUser{
						SlotID:      task.SlotID,
						Prompt:      strings.TrimSpace(task.Prompt),
						Required:    task.Required,
						Suggestions: append([]string(nil), task.Suggestions...),
					},
					StopReason: "context_fill_required",
				}
				return
			}
			timeout := time.Duration(plan.TimeoutMs) * time.Millisecond
			if timeout <= 0 {
				timeout = defaultSubagentTimeoutMs * time.Millisecond
			}
			runCtx, cancel := context.WithTimeout(ctx, timeout)
			defer cancel()
			reactRuntime := l.React
			reactRuntime.PreToolUse = l.preToolUse()
			result, err := reactRuntime.Run(runCtx, turn, selection)
			runs[index].Result = result
			runs[index].Err = err
			if err != nil {
				log.Printf(
					"assistant agent subagent_failed turnId=%s subagentId=%s err=%v",
					turn.TurnID,
					plan.SubagentID,
					err,
				)
			}
		}(index, plan)
	}
	wait.Wait()
	return runs
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
	return plans
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
	runs := l.runSubagentsInParallel(ctx, turn, plans)
	if err := emitSubagentProcesses(projector, appendEvent, runs); err != nil {
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
		response, didStream, err := l.React.SynthesizeSubagentAnswer(
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
		if len(run.Result.Steps) > 0 {
			processing := buildRetrievalProcessingForStep(
				run.Result.Steps[len(run.Result.Steps)-1],
			)
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

// emitSubagentProcesses 在所有子代理结束后按计划顺序补齐过程条目，保证过程时间线稳定。
func emitSubagentProcesses(
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
		if run.Err == nil && len(run.Result.Steps) > 0 {
			processing := buildRetrievalProcessingForStep(
				run.Result.Steps[len(run.Result.Steps)-1],
			)
			process.SearchedDocumentCount = intValue(processing["searchedDocumentCount"])
			process.ProcessedDocumentCount = intValue(processing["processedDocumentCount"])
			process.AcceptedDocumentCount = intValue(processing["acceptedDocumentCount"])
			process.AcceptedReferences = UserProcessReferences(processing["acceptedReferences"])
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
