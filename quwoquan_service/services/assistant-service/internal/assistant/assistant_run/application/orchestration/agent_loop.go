package orchestration

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"log"
	"strings"
	"time"

	rtfailures "quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/streaming"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	channelpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/channel"
	contextassembly "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/contextassembly"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	skillcontext "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/streaming"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

type AgentLoop struct {
	Skills SkillRuntime
	// SkillCandidates 在路由前把候选集收窄到用户 Setting 或共享 Placement
	// 当前允许的 active-package Skills。nil 表示未配置策略；非 nil 空集合
	// 表示没有可执行 Skill，路由必须 fail closed。
	SkillCandidates SkillCandidateAccessPolicy
	// SkillAccess 在路由完成后、任何 Context/Tool/Model 执行前重新求交
	// 个人设置或共享 Placement，保证隐式路由不能绕过权限门。
	SkillAccess SkillExecutionAccessPolicy
	// ToolAccess 在每次实际工具调用前，用 canonical tool metadata 重新求交
	// Capability、Consent、Setting、Connector grant 与 surface policy。
	ToolAccess ToolExecutionAccessPolicy
	// Catalog resolves only the currently active immutable Skill package. The
	// production composition never falls back to source-tree discovery.
	Catalog skillpkg.Loader
	React   ReactRuntime
	// Subagents 判定多技能并行计划。未配置时所有问题都按单技能执行。
	Subagents SubagentPlanner
	// DurableSubtasks claims each persisted child TaskNode through the owning
	// AssistantRun CAS journal. Durable runs fail closed when this dependency is
	// absent; transient turns may still use the bounded in-process path.
	DurableSubtasks *DurableSubtaskCoordinator
	// PromptAssets 按需解析被选中技能的领域话术。未配置时技能不得声明提示词资产。
	PromptAssets ports.PromptAssetResolver
	// Contexts 在任何执行模型调用前装配授权上下文与槽位。
	Contexts contextassembly.Assembler
	// SkillContexts resolves only the requirements declared by the selected
	// immutable ContextProfile. Large values stay behind Artifact refs.
	SkillContexts *skillcontext.Assembler
	Now           func() time.Time
}

type SkillExecutionAccessPolicy interface {
	AuthorizeSkill(context.Context, assistant.AssistantTurn, string) error
}

type SkillCandidateAccessPolicy interface {
	AllowedSkillIDs(context.Context, assistant.AssistantTurn) ([]string, error)
}

type ToolExecutionAccessPolicy interface {
	AuthorizeTool(
		context.Context,
		assistant.AssistantTurn,
		SkillSelection,
		string,
		toolpkg.Metadata,
	) error
}

type ToolExecutionAccessPolicyFunc func(
	context.Context,
	assistant.AssistantTurn,
	SkillSelection,
	string,
	toolpkg.Metadata,
) error

func (authorize ToolExecutionAccessPolicyFunc) AuthorizeTool(
	ctx context.Context,
	turn assistant.AssistantTurn,
	skill SkillSelection,
	toolName string,
	metadata toolpkg.Metadata,
) error {
	return authorize(ctx, turn, skill, toolName, metadata)
}

type SkillCandidateAccessPolicyFunc func(
	context.Context,
	assistant.AssistantTurn,
) ([]string, error)

func (resolve SkillCandidateAccessPolicyFunc) AllowedSkillIDs(
	ctx context.Context,
	turn assistant.AssistantTurn,
) ([]string, error) {
	return resolve(ctx, turn)
}

type SkillExecutionAccessPolicyFunc func(
	context.Context,
	assistant.AssistantTurn,
	string,
) error

func (authorize SkillExecutionAccessPolicyFunc) AuthorizeSkill(
	ctx context.Context,
	turn assistant.AssistantTurn,
	skillID string,
) error {
	return authorize(ctx, turn, skillID)
}

func NewAgentLoop(skills SkillRuntime, react ReactRuntime, now func() time.Time) *AgentLoop {
	if react.Tools == nil {
		react.Tools = DefaultToolCoordinator{Now: now}
	}
	return &AgentLoop{
		Skills:   skills,
		React:    react,
		Contexts: contextassembly.NewContextOrchestrator(),
		Now:      now,
	}
}

func (l *AgentLoop) RunTurn(ctx context.Context, turn assistant.AssistantTurn) ([]streaming.Envelope, *rtfailures.Failure, error) {
	return l.RunTurnWithSink(ctx, turn, nil)
}

func (l *AgentLoop) RunTurnWithSink(ctx context.Context, turn assistant.AssistantTurn, emit func(streaming.Envelope) error) ([]streaming.Envelope, *rtfailures.Failure, error) {
	return l.RunTurnWithSinkAfterSeq(ctx, turn, 0, emit)
}

func (l *AgentLoop) RunTurnWithSinkAfterSeq(
	ctx context.Context,
	turn assistant.AssistantTurn,
	afterSeq uint64,
	emit func(streaming.Envelope) error,
) ([]streaming.Envelope, *rtfailures.Failure, error) {
	return l.runTurnWithSinkAfterSeq(ctx, turn, afterSeq, emit, nil)
}

func (l *AgentLoop) runTurnWithSinkAfterSeq(
	ctx context.Context,
	turn assistant.AssistantTurn,
	afterSeq uint64,
	emit func(streaming.Envelope) error,
	observe PreparedExecutionObserver,
) ([]streaming.Envelope, *rtfailures.Failure, error) {
	if l == nil {
		l = NewAgentLoop(nil, ReactRuntime{}, nil)
	}
	turn = sanitizeTurnForSurface(turn)
	turnStartedAt := time.Now()
	log.Printf("assistant agent run_started sessionId=%s turnId=%s traceId=%s", turn.SessionID, turn.TurnID, turn.TraceID)
	projector := assistantstreaming.NewStreamProjectorAt(turn, l.Now, afterSeq)
	events := []streaming.Envelope{}
	appendEvent := func(envelope streaming.Envelope, err error) error {
		if err != nil {
			return err
		}
		events = append(events, envelope)
		if emit != nil {
			if err := emit(envelope); err != nil {
				return err
			}
		}
		return nil
	}
	if err := appendEvent(projector.Event(assistantstreaming.AssistantStreamEventRunStarted, map[string]any{
		"status":            "running",
		"restarted":         afterSeq > 0,
		"policyAttribution": boundedPolicyAttribution(turn),
	})); err != nil {
		return nil, nil, err
	}
	if err := appendEvent(projector.Event(assistantstreaming.AssistantStreamEventProcessReplace, userProcessReplacePayload())); err != nil {
		return nil, nil, err
	}
	if l.React.Model == nil {
		failure := modelFailure("model_provider", fmt.Errorf("model provider is not configured"))
		if appendErr := appendEvent(projector.Failure(
			assistantstreaming.AssistantStreamEventFailed,
			map[string]any{"status": "failed"},
			failure,
		)); appendErr != nil {
			return events, nil, appendErr
		}
		return events, &failure, nil
	}
	skillStartedAt := time.Now()
	skill, err := l.skillSelectionForTurn(ctx, turn)
	skillDurationMs := time.Since(skillStartedAt).Milliseconds()
	if err != nil {
		log.Printf("assistant agent skill_select_failed turnId=%s durationMs=%d err=%v", turn.TurnID, skillDurationMs, err)
		failure := modelFailure("skill_runtime", err)
		if appendErr := appendEvent(projector.Failure(
			assistantstreaming.AssistantStreamEventFailed,
			map[string]any{"status": "failed"},
			failure,
		)); appendErr != nil {
			return events, nil, appendErr
		}
		return events, &failure, nil
	}
	log.Printf("assistant agent skill_selected turnId=%s skillId=%s domainId=%s displayName=%s durationMs=%d", turn.TurnID, skill.SkillID, skill.DomainID, skill.DisplayName, skillDurationMs)
	if err := appendEvent(projector.Event(
		assistantstreaming.AssistantStreamEventProcessAppend,
		userProcessPayload(assistant.AssistantRunVisibleProcess{
			ProcessID:  userProcessID(assistantUserProcessPhaseSkillSelection, 0),
			Scope:      assistantUserProcessScopeRoot,
			Stage:      assistantUserProcessPhaseSkillSelection.WireName(),
			ActionCode: assistantgenerated.PlannerActionCodeClassifyDomain.WireName(),
			Status:     assistantUserProcessStatusCompleted,
			Order:      1,
			SkillID:    skill.SkillID,
			DomainID:   skill.DomainID,
		}),
	)); err != nil {
		return nil, nil, err
	}
	assembly, err := l.assembleContext(ctx, turn, skill)
	if err != nil {
		log.Printf(
			"assistant agent context_assembly_failed turnId=%s skillId=%s err=%v",
			turn.TurnID,
			skill.SkillID,
			err,
		)
		failure := modelFailure("context_orchestrator", err)
		if appendErr := appendEvent(projector.Failure(
			assistantstreaming.AssistantStreamEventFailed,
			map[string]any{"status": "failed"},
			failure,
		)); appendErr != nil {
			return events, nil, appendErr
		}
		return events, &failure, nil
	}
	skill.ContextAssembly = &assembly
	if observe != nil {
		prepared, prepareErr := freezePreparedExecution(skill)
		if prepareErr == nil {
			prepareErr = observe(prepared)
		}
		if prepareErr != nil {
			log.Printf(
				"assistant agent execution_prepare_failed turnId=%s skillId=%s err=%v",
				turn.TurnID,
				skill.SkillID,
				prepareErr,
			)
			failure := modelFailure("execution_prepare", prepareErr)
			if appendErr := appendEvent(projector.Failure(
				assistantstreaming.AssistantStreamEventFailed,
				map[string]any{"status": "failed"},
				failure,
			)); appendErr != nil {
				return events, nil, appendErr
			}
			return events, &failure, nil
		}
	}
	if len(assembly.FillTasks) > 0 {
		if err := streamContextClarification(turn, skill, assembly, projector, appendEvent); err != nil {
			return events, nil, err
		}
		log.Printf(
			"assistant agent context_clarification turnId=%s skillId=%s missingSlots=%v",
			turn.TurnID,
			skill.SkillID,
			assembly.SlotState.MissingSlots,
		)
		return events, nil, nil
	}
	if err := appendEvent(projector.Event(
		assistantstreaming.AssistantStreamEventProcessAppend,
		userProcessPayload(assistant.AssistantRunVisibleProcess{
			ProcessID:  userProcessID(assistantUserProcessPhasePlanning, 1),
			Scope:      assistantUserProcessScopeSkill,
			Stage:      assistantUserProcessPhasePlanning.WireName(),
			ActionCode: assistantgenerated.PlannerActionCodeBuildPlan.WireName(),
			Status:     assistantUserProcessStatusActive,
			Order:      2,
			SkillID:    skill.SkillID,
			DomainID:   skill.DomainID,
		}),
	)); err != nil {
		return nil, nil, err
	}
	if plans := l.subagentPlans(ctx, turn, skill); len(plans) > 1 {
		failure, err := l.streamMultiSkillTurn(ctx, turn, skill, plans, projector, appendEvent)
		if err != nil {
			return events, nil, err
		}
		log.Printf(
			"assistant agent run_completed sessionId=%s turnId=%s events=%d subagents=%d totalMs=%d",
			turn.SessionID,
			turn.TurnID,
			len(events),
			len(plans),
			time.Since(turnStartedAt).Milliseconds(),
		)
		return events, failure, nil
	}
	var streamedFailure *rtfailures.Failure
	var answerStreamStartedAt time.Time
	answerProcessStarted := false
	reactStartedAt := time.Now()
	reactRuntime := l.React
	reactRuntime.PrePlanAccess = l.prePlanAccess()
	reactRuntime.PreToolUse = l.preToolUse()
	ctx = runruntime.WithContextCompactionBoundary(ctx)
	result, err := reactRuntime.RunWithFinalTextSink(ctx, turn, skill, func(step ReactStepResult) error {
		return emitReactReasoning(projector, appendEvent, turn, skill, step)
	}, func(step ReactStepResult) error {
		failure, err := emitReactObservation(projector, appendEvent, turn, skill, step)
		if failure != nil {
			streamedFailure = failure
		}
		return err
	}, func(delta ports.ModelTextDelta) error {
		if answerStreamStartedAt.IsZero() {
			answerStreamStartedAt = time.Now()
		}
		if !answerProcessStarted {
			if err := appendEvent(projector.Event(
				assistantstreaming.AssistantStreamEventProcessAppend,
				userProcessPayload(assistant.AssistantRunVisibleProcess{
					ProcessID:  userProcessID(assistantUserProcessPhaseAnswerGeneration, 0),
					Scope:      assistantUserProcessScopeAggregation,
					Stage:      assistantUserProcessPhaseAnswerGeneration.WireName(),
					ActionCode: assistantgenerated.PlannerActionCodeStreamAnswer.WireName(),
					Status:     assistantUserProcessStatusActive,
					Order:      999,
					SkillID:    skill.SkillID,
					DomainID:   skill.DomainID,
				}),
			)); err != nil {
				return err
			}
			answerProcessStarted = true
		}
		return appendEvent(projector.Event(assistantstreaming.AssistantStreamEventAnswerDelta, map[string]any{
			"text": delta.Text,
		}))
	})
	reactDurationMs := time.Since(reactStartedAt).Milliseconds()
	if err != nil {
		log.Printf("assistant agent react_failed turnId=%s skillId=%s durationMs=%d err=%v", turn.TurnID, skill.SkillID, reactDurationMs, err)
		failure := modelFailure("react_runtime", err)
		if appendErr := appendEvent(projector.Failure(
			assistantstreaming.AssistantStreamEventFailed,
			map[string]any{"status": "failed"},
			failure,
		)); appendErr != nil {
			return events, nil, appendErr
		}
		return events, &failure, nil
	}
	log.Printf("assistant agent react_done turnId=%s skillId=%s steps=%d modelInteractions=%d finalLen=%d stopReason=%s durationMs=%d", turn.TurnID, skill.SkillID, len(result.Steps), resultModelInteractionCount(result), len([]rune(result.FinalText)), result.StopReason, reactDurationMs)
	recordReactOutcome(result)
	if streamedFailure != nil {
		return events, streamedFailure, nil
	}
	if result.StopReason == "waiting_tool_approval" {
		toolUseID := strings.TrimSpace(result.Tool.Completed.ToolUseID)
		proposal, _ := result.Tool.Completed.Result["proposal"].(map[string]any)
		if toolUseID == "" || len(proposal) == 0 {
			return events, nil, fmt.Errorf("device action approval is missing its proposal")
		}
		issuedAt := time.Now().UTC()
		if l.Now != nil {
			issuedAt = l.Now().UTC()
		}
		runID := assistantContinuationRunID(turn)
		if err := appendEvent(projector.Event(
			assistantstreaming.AssistantStreamEventWaitingApproval,
			map[string]any{
				"reason":    "waiting_tool_approval",
				"runId":     runID,
				"toolUseId": toolUseID,
				"continuationToken": assistantContinuationToken(
					runID,
					toolUseID,
				),
				"issuedAt":  issuedAt.Format(time.RFC3339Nano),
				"expiresAt": issuedAt.Add(time.Minute).Format(time.RFC3339Nano),
				"proposal":  proposal,
			},
		)); err != nil {
			return events, nil, err
		}
		return events, nil, nil
	}
	skillRuns := []SkillRunOutcome{
		skillRunOutcomeFrom(skillRunID(0, skill.SkillID), skill, result),
	}
	aggregation := ResolveAggregation(skillRuns)
	closingPhase := assistantUserProcessPhaseAnswerGeneration
	closingAction := assistantgenerated.PlannerActionCodeComposeAnswer
	if aggregation.ClarificationNeeded {
		closingPhase = assistantUserProcessPhaseClarifying
		closingAction = assistantgenerated.PlannerActionCodeAskClarification
	}
	if !result.FinalStreamed {
		answerStreamStartedAt = time.Now()
		if !answerProcessStarted {
			if err := appendEvent(projector.Event(
				assistantstreaming.AssistantStreamEventProcessAppend,
				userProcessPayload(assistant.AssistantRunVisibleProcess{
					ProcessID:  userProcessID(closingPhase, 0),
					Scope:      assistantUserProcessScopeAggregation,
					Stage:      closingPhase.WireName(),
					ActionCode: closingAction.WireName(),
					Status:     assistantUserProcessStatusActive,
					Order:      999,
					SkillID:    skill.SkillID,
					DomainID:   skill.DomainID,
				}),
			)); err != nil {
				return nil, nil, err
			}
			answerProcessStarted = true
		}
		if err := appendEvent(projector.Event(assistantstreaming.AssistantStreamEventAnswerDelta, map[string]any{
			"text": result.FinalText,
		})); err != nil {
			return nil, nil, err
		}
	}
	if answerProcessStarted {
		if err := appendEvent(projector.Event(
			assistantstreaming.AssistantStreamEventProcessCommit,
			userProcessPayload(assistant.AssistantRunVisibleProcess{
				ProcessID:  userProcessID(closingPhase, 0),
				Scope:      assistantUserProcessScopeAggregation,
				Stage:      closingPhase.WireName(),
				ActionCode: closingAction.WireName(),
				Status:     assistantUserProcessStatusCompleted,
				Order:      999,
				SkillID:    skill.SkillID,
				DomainID:   skill.DomainID,
			}),
		)); err != nil {
			return nil, nil, err
		}
	}
	completedPayload := map[string]any{
		"status":            "completed",
		"finalAnswer":       result.FinalText,
		"emergedTags":       collectEmergedTags(result),
		"policyAttribution": boundedPolicyAttribution(turn),
		"messageKind":       aggregation.MessageKind().WireName(),
		"finalAnswerMode":   aggregation.FinalAnswerMode.WireName(),
		"aggregationState":  aggregation.payload(),
		"skillRuns":         skillRunPayloads(skillRuns),
	}
	if ask := askUserPayload(result.AskUser); ask != nil {
		completedPayload["askUser"] = ask
	}
	if err := appendEvent(projector.Event(assistantstreaming.AssistantStreamEventCompleted, completedPayload)); err != nil {
		return nil, nil, err
	}
	answerStreamDurationMs := time.Since(answerStreamStartedAt).Milliseconds()
	totalDurationMs := time.Since(turnStartedAt).Milliseconds()
	log.Printf("assistant agent latency_summary turnId=%s skillMs=%d reactMs=%d answerStreamMs=%d totalMs=%d modelInteractions=%d steps=%d", turn.TurnID, skillDurationMs, reactDurationMs, answerStreamDurationMs, totalDurationMs, resultModelInteractionCount(result), len(result.Steps))
	log.Printf("assistant agent run_completed sessionId=%s turnId=%s events=%d answerLen=%d", turn.SessionID, turn.TurnID, len(events), len([]rune(result.FinalText)))
	return events, nil, nil
}

func sanitizeTurnForSurface(turn assistant.AssistantTurn) assistant.AssistantTurn {
	channel := channelpkg.ResolveForSurface(
		turn.TurnType,
		turn.Trigger,
		turn.RequestContext.SurfaceKind,
	)
	if channel.ContextPersistence() != channelpkg.ContextPersistenceChannelOnly {
		return turn
	}
	// Shared channels keep only owner-backed conversation/domain facts admitted
	// later by ContextProfile readers. Caller/session personal state must not be
	// forwarded to routing, subagents, model prompting or presentation.
	turn.ContextTurns = nil
	turn.ContextSummary = nil
	turn.PageContext = nil
	turn.SessionPreferences = nil
	turn.LongTermPreferences = nil
	turn.FeedbackContextSnapshot = assistant.AssistantFeedbackContextSnapshot{
		Decision: "shared_surface_excluded",
	}
	return turn
}

func assistantContinuationToken(runID string, toolUseID string) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(runID) + "\x00" + strings.TrimSpace(toolUseID)))
	return "ct_" + hex.EncodeToString(digest[:16])
}

func assistantContinuationRunID(turn assistant.AssistantTurn) string {
	if runID := strings.TrimSpace(turn.ExecutionRunID); runID != "" {
		return runID
	}
	return strings.TrimSpace(turn.TurnID)
}

func (l *AgentLoop) assembleContext(
	ctx context.Context,
	turn assistant.AssistantTurn,
	skill SkillSelection,
) (contextassembly.AssemblyResult, error) {
	assembler := l.Contexts
	if assembler == nil {
		defaultAssembler := contextassembly.NewContextOrchestrator()
		assembler = defaultAssembler
	}
	surfaceID := strings.TrimSpace(turn.RequestContext.SurfaceID)
	if surfaceID == "" && turn.PageContext != nil {
		surfaceID = strings.TrimSpace(turn.PageContext.PageType)
	}
	channel := channelpkg.ResolveForSurface(
		turn.TurnType,
		turn.Trigger,
		turn.RequestContext.SurfaceKind,
	)
	assembly, err := assembler.Assemble(ctx, contextassembly.AssemblyInput{
		Turn: turn,
		Client: contextassembly.ClientContext{
			SurfaceID: surfaceID,
		},
		Device: contextassembly.DeviceContextResponse{
			Status: "unavailable",
			Reason: "device context was not supplied for this run",
		},
		DomainID:     skill.DomainID,
		ProblemClass: skill.ProblemClass,
		SlotSchema:   skill.SlotSchema,
		Channel:      channel,
	})
	if err != nil || l.SkillContexts == nil || strings.TrimSpace(skill.ContextProfile.ProfileID) == "" {
		return assembly, err
	}
	profile, err := canonicalSkillContextProfile(skill.ContextProfile)
	if err != nil {
		return contextassembly.AssemblyResult{}, err
	}
	visibility := skillcontext.DeliveryPersonal
	maximumSensitivity := assistantgenerated.AssistantContextSensitivityPrivate
	if sharedAssistantSurface(turn.RequestContext.SurfaceKind) {
		// Conversation/Circle 是成员可见的共享面，不是公开互联网。
		// 允许 owner-backed internal 事实进入，但 delivery policy 仍会拒绝
		// private/restricted memory 与个人 Connector。
		visibility = skillcontext.DeliveryShared
		maximumSensitivity = assistantgenerated.AssistantContextSensitivityInternal
	} else if channel.AnswerBoundary().Public {
		visibility = skillcontext.DeliveryPublic
		maximumSensitivity = assistantgenerated.AssistantContextSensitivityPublic
	}
	contextRunID := strings.TrimSpace(turn.ExecutionRunID)
	if contextRunID == "" {
		contextRunID = strings.TrimSpace(turn.TurnID)
	}
	snapshot, err := l.SkillContexts.Assemble(ctx, profile, skillcontext.AssembleRequest{
		RunID:              contextRunID,
		OwnerID:            turn.UserID,
		SkillID:            skill.SkillID,
		Visibility:         visibility,
		AllowedSensitivity: maximumSensitivity,
	})
	if err != nil {
		return contextassembly.AssemblyResult{}, err
	}
	for _, missing := range snapshot.Missing {
		if missing.FallbackPolicy == "block" {
			return contextassembly.AssemblyResult{}, fmt.Errorf(
				"required skill context %q is unavailable",
				missing.SlotID,
			)
		}
	}
	assembly.SkillContextSnapshot = &snapshot
	return assembly, nil
}

func canonicalSkillContextProfile(
	profile skillpkg.ContextProfile,
) (skillcontext.Profile, error) {
	result := skillcontext.Profile{
		ProfileID:    strings.TrimSpace(profile.ProfileID),
		AssetDigest:  strings.TrimSpace(profile.AssetDigest),
		Requirements: make([]skillcontext.Requirement, 0, len(profile.Requirements)),
	}
	for _, requirement := range profile.Requirements {
		authority, err := assistantgenerated.ParseAssistantContextAuthority(requirement.Authority)
		if err != nil || authority == assistantgenerated.AssistantContextAuthorityUnknown {
			return skillcontext.Profile{}, fmt.Errorf("context requirement %q has invalid authority", requirement.SlotID)
		}
		sensitivity, err := assistantgenerated.ParseAssistantContextSensitivity(requirement.Sensitivity)
		if err != nil {
			return skillcontext.Profile{}, fmt.Errorf("context requirement %q has invalid sensitivity", requirement.SlotID)
		}
		result.Requirements = append(result.Requirements, skillcontext.Requirement{
			SlotID:              requirement.SlotID,
			Required:            requirement.Required,
			AcceptedSourceKinds: append([]string(nil), requirement.AcceptedSourceKinds...),
			Authority:           authority,
			Sensitivity:         sensitivity,
			ConsentScopes:       append([]string(nil), requirement.ConsentScopes...),
			Freshness:           time.Duration(requirement.FreshnessSeconds) * time.Second,
			TokenBudget:         requirement.TokenBudget,
			ResolverRef:         requirement.ResolverRef,
			FallbackPolicy:      requirement.FallbackPolicy,
		})
	}
	return result, nil
}

// skillSelectionForTurn 以 Run 冻结的 active Skill package 为唯一 Skill 真相源。
// AssistantPolicyRelease 只保留模型 cohort、学习策略与通用执行边界，不能覆盖 Skill
// 身份、领域、工具或完成条件。
func (l *AgentLoop) skillSelectionForTurn(
	ctx context.Context,
	turn assistant.AssistantTurn,
) (SkillSelection, error) {
	policySelection, err := skillSelectionFromFrozenPolicy(turn)
	if err != nil {
		return SkillSelection{}, err
	}
	skillID := strings.TrimSpace(turn.SkillID)
	if skillID == "" {
		var allowedSkillIDs []string
		if l.SkillCandidates != nil {
			allowedSkillIDs, err = l.SkillCandidates.AllowedSkillIDs(ctx, turn)
			if err != nil {
				return SkillSelection{}, err
			}
		}
		if l.Skills != nil {
			var selection SkillSelection
			var selectErr error
			if l.SkillCandidates != nil {
				scoped, ok := l.Skills.(ScopedSkillRuntime)
				if !ok {
					return SkillSelection{}, fmt.Errorf("Skill runtime does not support access-scoped routing")
				}
				selection, selectErr = scoped.SelectSkillWithin(ctx, turn, allowedSkillIDs)
			} else {
				selection, selectErr = l.Skills.SelectSkill(ctx, turn)
			}
			if selectErr != nil {
				return SkillSelection{}, selectErr
			}
			skillID = strings.TrimSpace(selection.SkillID)
		} else {
			loader := l.Catalog
			if loader == nil {
				return SkillSelection{}, fmt.Errorf("active Skill package is not configured")
			}
			catalog, loadErr := loader.Load(ctx)
			if loadErr != nil {
				return SkillSelection{}, loadErr
			}
			catalog = restrictSkillCatalog(reactiveSkillCatalog(catalog), allowedSkillIDs)
			if l.SkillCandidates != nil && len(catalog) == 0 {
				return SkillSelection{}, ErrNoEligibleSkill
			}
			skillID = skillpkg.NewRouter(catalog).Route(turn).SkillID
		}
	}
	manifest, found, err := l.resolveSkillManifest(ctx, skillID)
	if err != nil {
		return SkillSelection{}, err
	}
	if !found {
		return SkillSelection{}, fmt.Errorf(
			"turn %s frozen Skill %q is absent from active package",
			turn.TurnID,
			skillID,
		)
	}
	if l.SkillAccess != nil {
		if err := l.SkillAccess.AuthorizeSkill(ctx, turn, skillID); err != nil {
			return SkillSelection{}, err
		}
	}
	selection := selectionFromManifest(manifest)
	selection.SearchIntensity = policySelection.SearchIntensity
	guidance, err := resolveSkillPromptGuidance(ctx, l.PromptAssets, manifest)
	if err != nil {
		return SkillSelection{}, err
	}
	selection.PromptPolicy = composePromptPolicy(policySelection.PromptPolicy, guidance)
	return selection, nil
}

func skillSelectionFromFrozenPolicy(
	turn assistant.AssistantTurn,
) (SkillSelection, error) {
	frozen := turn.FrozenPolicySelection
	template := frozen.Template
	if strings.TrimSpace(frozen.PolicyID) == "" ||
		strings.TrimSpace(frozen.ReleaseDigest) == "" ||
		strings.TrimSpace(frozen.Cohort) == "" ||
		frozen.RolloutRevision <= 0 ||
		strings.TrimSpace(template.TemplateID) == "" ||
		strings.TrimSpace(template.SkillID) == "" ||
		strings.TrimSpace(template.DomainID) == "" ||
		strings.TrimSpace(template.PromptPolicy) == "" {
		return SkillSelection{}, fmt.Errorf(
			"turn %s has no complete frozen policy selection",
			turn.TurnID,
		)
	}
	toolPolicy, err := canonicalToolPolicy(template.AllowedTools)
	if err != nil {
		return SkillSelection{}, fmt.Errorf(
			"turn %s frozen policy template %s: %w",
			turn.TurnID,
			template.TemplateID,
			err,
		)
	}
	return SkillSelection{
		SkillID:         strings.TrimSpace(template.SkillID),
		DomainID:        strings.TrimSpace(template.DomainID),
		DisplayName:     strings.TrimSpace(template.SkillID),
		ToolPolicy:      toolPolicy,
		PromptPolicy:    strings.TrimSpace(template.PromptPolicy),
		SearchIntensity: strings.TrimSpace(template.SearchIntensity),
	}, nil
}

// canonicalToolPolicy 拒绝已发布策略里不存在的工具名。允许集为空表示该策略不开放工具，
// 而不是开放全部；这一层校验让策略发布错误在进入 ToolExecutionGuard 之前就暴露。
func canonicalToolPolicy(allowedTools []string) ([]string, error) {
	canonical := map[string]bool{}
	for _, name := range toolpkg.CanonicalToolNames() {
		canonical[name] = true
	}
	policy := make([]string, 0, len(allowedTools))
	for _, name := range allowedTools {
		trimmed := strings.TrimSpace(name)
		if trimmed == "" {
			continue
		}
		if !canonical[trimmed] {
			return nil, fmt.Errorf(
				"allows unregistered tool %q; registered tools are %v",
				trimmed,
				toolpkg.CanonicalToolNames(),
			)
		}
		policy = append(policy, trimmed)
	}
	return policy, nil
}

func boundedPolicyAttribution(turn assistant.AssistantTurn) map[string]any {
	frozen := turn.FrozenPolicySelection
	return map[string]any{
		"policyId":        frozen.PolicyID,
		"releaseDigest":   frozen.ReleaseDigest,
		"cohort":          frozen.Cohort,
		"rolloutRevision": frozen.RolloutRevision,
		"ruleId":          frozen.RuleID,
		"templateId":      frozen.Template.TemplateID,
	}
}

func resultModelInteractionCount(result ReactResult) int {
	count := 0
	for _, step := range result.Steps {
		count += len(step.ModelInteractions)
	}
	if len(result.Steps) == 0 && len(result.ModelDelta) > 0 {
		count++
	}
	if len(result.FinalClientTrace) > 0 {
		count++
	}
	return count
}

func emitReactReasoning(projector *assistantstreaming.StreamProjector, appendEvent func(streaming.Envelope, error) error, turn assistant.AssistantTurn, skill SkillSelection, step ReactStepResult) error {
	log.Printf("assistant agent react_reasoning turnId=%s skillId=%s iteration=%d tool=%s", turn.TurnID, skill.SkillID, step.Iteration, step.Tool.Requested.ToolName)
	snapshot := buildUnderstandingSnapshotForStep(turn, step)
	if err := appendEvent(projector.Event(
		assistantstreaming.AssistantStreamEventProcessCommit,
		userProcessPayload(assistant.AssistantRunVisibleProcess{
			ProcessID:  userProcessID(assistantUserProcessPhasePlanning, step.Iteration),
			Scope:      assistantUserProcessScopeSkill,
			Stage:      assistantUserProcessPhasePlanning.WireName(),
			ActionCode: plannerActionCode(step, assistantgenerated.PlannerActionCodeBuildPlan),
			Status:     assistantUserProcessStatusCompleted,
			Order:      step.Iteration*10 + 2,
			Summary: userProcessSummary(
				stringValue(snapshot["userFacingSummary"]),
			),
			SkillID:  skill.SkillID,
			DomainID: skill.DomainID,
		}),
	)); err != nil {
		return err
	}
	if toolName := strings.TrimSpace(step.Tool.Requested.ToolName); toolName != "" {
		if err := appendEvent(projector.Event(
			assistantstreaming.AssistantStreamEventProcessAppend,
			userProcessPayload(assistant.AssistantRunVisibleProcess{
				ProcessID:  userProcessID(assistantUserProcessPhaseToolExecution, step.Iteration),
				Scope:      assistantUserProcessScopeSkill,
				Stage:      assistantUserProcessPhaseToolExecution.WireName(),
				ActionCode: assistantgenerated.PlannerActionCodeStartRetrieval.WireName(),
				Status:     assistantUserProcessStatusActive,
				Order:      step.Iteration*10 + 3,
				SkillID:    skill.SkillID,
				DomainID:   skill.DomainID,
			}),
		)); err != nil {
			return err
		}
	}
	return nil
}

// plannerActionCode 取 planner 决策自带的动作码；决策没有给出时退回该阶段的默认动作。
func plannerActionCode(
	step ReactStepResult,
	fallback assistantgenerated.PlannerActionCode,
) string {
	if step.Decision.ActionCode != assistantgenerated.PlannerActionCodeUnknown {
		return step.Decision.ActionCode.WireName()
	}
	return fallback.WireName()
}

func emitReactObservation(projector *assistantstreaming.StreamProjector, appendEvent func(streaming.Envelope, error) error, turn assistant.AssistantTurn, skill SkillSelection, step ReactStepResult) (*rtfailures.Failure, error) {
	log.Printf("assistant agent react_step turnId=%s skillId=%s iteration=%d tool=%s observationLen=%d replan=%t", turn.TurnID, skill.SkillID, step.Iteration, step.Tool.Requested.ToolName, len([]rune(step.Observation.Summary)), step.Replan)
	if step.DecisionRejection != nil {
		log.Printf(
			"assistant agent decision_rejected turnId=%s skillId=%s iteration=%d reason=%s retryable=%t",
			turn.TurnID,
			skill.SkillID,
			step.Iteration,
			step.DecisionRejection.ReasonCode,
			step.DecisionRejection.Retryable,
		)
		if step.Replan {
			if err := appendEvent(projector.Event(
				assistantstreaming.AssistantStreamEventProcessAppend,
				userProcessPayload(assistant.AssistantRunVisibleProcess{
					ProcessID:  userProcessID(assistantUserProcessPhasePlanning, step.Iteration+1),
					Scope:      assistantUserProcessScopeSkill,
					Stage:      assistantUserProcessPhasePlanning.WireName(),
					ActionCode: assistantgenerated.PlannerActionCodeRecoverRetrieval.WireName(),
					Status:     assistantUserProcessStatusActive,
					Order:      (step.Iteration+1)*10 + 2,
					SkillID:    skill.SkillID,
					DomainID:   skill.DomainID,
				}),
			)); err != nil {
				return nil, err
			}
		}
		return nil, nil
	}
	if step.Tool.Failure != nil {
		log.Printf("assistant agent tool_failed turnId=%s skillId=%s iteration=%d tool=%s code=%s", turn.TurnID, skill.SkillID, step.Iteration, step.Tool.Requested.ToolName, step.Tool.Failure.Code)
		if err := appendEvent(projector.Event(
			assistantstreaming.AssistantStreamEventProcessCommit,
			userProcessPayload(assistant.AssistantRunVisibleProcess{
				ProcessID:  userProcessID(assistantUserProcessPhaseToolExecution, step.Iteration),
				Scope:      assistantUserProcessScopeSkill,
				Stage:      assistantUserProcessPhaseToolExecution.WireName(),
				ActionCode: assistantgenerated.PlannerActionCodeRecoverRetrieval.WireName(),
				Status:     assistantUserProcessStatusFailed,
				Order:      step.Iteration*10 + 3,
				SkillID:    skill.SkillID,
				DomainID:   skill.DomainID,
			}),
		)); err != nil {
			return nil, err
		}
		if err := appendEvent(projector.Failure(assistantstreaming.AssistantStreamEventFailed, map[string]any{
			"status": "failed",
		}, *step.Tool.Failure)); err != nil {
			return nil, err
		}
		return step.Tool.Failure, nil
	}
	retrievalProcessing := buildRetrievalProcessingForStep(step)
	if err := appendEvent(projector.Event(
		assistantstreaming.AssistantStreamEventProcessCommit,
		userProcessPayload(assistant.AssistantRunVisibleProcess{
			ProcessID:              userProcessID(assistantUserProcessPhaseToolExecution, step.Iteration),
			Scope:                  assistantUserProcessScopeSkill,
			Stage:                  assistantUserProcessPhaseToolExecution.WireName(),
			ActionCode:             assistantgenerated.PlannerActionCodeExecuteSearch.WireName(),
			Status:                 assistantUserProcessStatusCompleted,
			Order:                  step.Iteration*10 + 3,
			SkillID:                skill.SkillID,
			DomainID:               skill.DomainID,
			SearchedDocumentCount:  intValue(retrievalProcessing["searchedDocumentCount"]),
			ProcessedDocumentCount: intValue(retrievalProcessing["processedDocumentCount"]),
			AcceptedDocumentCount:  intValue(retrievalProcessing["acceptedDocumentCount"]),
		}),
	)); err != nil {
		return nil, err
	}
	log.Printf("assistant agent tool_completed turnId=%s skillId=%s iteration=%d tool=%s status=%s", turn.TurnID, skill.SkillID, step.Iteration, step.Tool.Completed.ToolName, step.Tool.Completed.Status)
	if err := appendEvent(projector.Event(
		assistantstreaming.AssistantStreamEventProcessAppend,
		userProcessPayload(assistant.AssistantRunVisibleProcess{
			ProcessID:  userProcessID(assistantUserProcessPhaseEvidenceReview, step.Iteration),
			Scope:      assistantUserProcessScopeSkill,
			Stage:      assistantUserProcessPhaseEvidenceReview.WireName(),
			ActionCode: assistantgenerated.PlannerActionCodeReviewSources.WireName(),
			Status:     assistantUserProcessStatusActive,
			Order:      step.Iteration*10 + 4,
			SkillID:    skill.SkillID,
			DomainID:   skill.DomainID,
		}),
	)); err != nil {
		return nil, err
	}
	if err := appendEvent(projector.Event(
		assistantstreaming.AssistantStreamEventProcessCommit,
		userProcessPayload(assistant.AssistantRunVisibleProcess{
			ProcessID:              userProcessID(assistantUserProcessPhaseEvidenceReview, step.Iteration),
			Scope:                  assistantUserProcessScopeSkill,
			Stage:                  assistantUserProcessPhaseEvidenceReview.WireName(),
			ActionCode:             assistantgenerated.PlannerActionCodeAssessEvidence.WireName(),
			Status:                 assistantUserProcessStatusCompleted,
			Order:                  step.Iteration*10 + 4,
			Summary:                userProcessSummary(stringValue(retrievalProcessing["processingSummary"])),
			SkillID:                skill.SkillID,
			DomainID:               skill.DomainID,
			SearchedDocumentCount:  intValue(retrievalProcessing["searchedDocumentCount"]),
			ProcessedDocumentCount: intValue(retrievalProcessing["processedDocumentCount"]),
			AcceptedDocumentCount:  intValue(retrievalProcessing["acceptedDocumentCount"]),
			AcceptedReferences:     UserProcessReferences(retrievalProcessing["acceptedReferences"]),
		}),
	)); err != nil {
		return nil, err
	}
	if step.Replan {
		log.Printf("assistant agent replan_requested turnId=%s skillId=%s iteration=%d reason=%s", turn.TurnID, skill.SkillID, step.Iteration, step.ReplanReason)
		if err := appendEvent(projector.Event(
			assistantstreaming.AssistantStreamEventProcessAppend,
			userProcessPayload(assistant.AssistantRunVisibleProcess{
				ProcessID:  userProcessID(assistantUserProcessPhasePlanning, step.Iteration+1),
				Scope:      assistantUserProcessScopeSkill,
				Stage:      assistantUserProcessPhasePlanning.WireName(),
				ActionCode: assistantgenerated.PlannerActionCodeExpandSearch.WireName(),
				Status:     assistantUserProcessStatusActive,
				Order:      (step.Iteration+1)*10 + 2,
				SkillID:    skill.SkillID,
				DomainID:   skill.DomainID,
			}),
		)); err != nil {
			return nil, err
		}
	}
	return nil, nil
}

func (l *AgentLoop) skills() SkillRuntime {
	if l != nil && l.Skills != nil {
		return l.Skills
	}
	return DefaultSkillRuntime{}
}
