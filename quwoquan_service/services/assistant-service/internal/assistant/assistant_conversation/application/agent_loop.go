package application

import (
	"context"
	"fmt"
	"log"
	"strings"
	"time"

	rtfailures "quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/streaming"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_conversation"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

type AgentLoop struct {
	Skills SkillRuntime
	React  ReactRuntime
	Now    func() time.Time
}

func NewAgentLoop(skills SkillRuntime, react ReactRuntime, now func() time.Time) *AgentLoop {
	if skills == nil {
		skills = DefaultSkillRuntime{}
	}
	if react.Tools == nil {
		react.Tools = DefaultToolCoordinator{Now: now}
	}
	return &AgentLoop{Skills: skills, React: react, Now: now}
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
	if l == nil {
		l = NewAgentLoop(nil, ReactRuntime{}, nil)
	}
	turnStartedAt := time.Now()
	log.Printf("assistant agent run_started conversationId=%s turnId=%s traceId=%s", turn.ConversationID, turn.TurnID, turn.TraceID)
	projector := NewStreamProjectorAt(turn, l.Now, afterSeq)
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
	if err := appendEvent(projector.Event(AssistantStreamEventRunStarted, map[string]any{
		"status":    "running",
		"restarted": afterSeq > 0,
	})); err != nil {
		return nil, nil, err
	}
	if err := appendEvent(projector.Event(AssistantStreamEventProcessReplace, userProcessReplacePayload())); err != nil {
		return nil, nil, err
	}
	if l.React.Model == nil {
		failure := modelFailure("model_provider", fmt.Errorf("model provider is not configured"))
		if appendErr := appendEvent(projector.Failure(
			AssistantStreamEventFailed,
			map[string]any{"status": "failed"},
			failure,
		)); appendErr != nil {
			return events, nil, appendErr
		}
		return events, &failure, nil
	}
	skillStartedAt := time.Now()
	skill, err := l.skills().SelectSkill(ctx, turn)
	skillDurationMs := time.Since(skillStartedAt).Milliseconds()
	if err != nil {
		log.Printf("assistant agent skill_select_failed turnId=%s durationMs=%d err=%v", turn.TurnID, skillDurationMs, err)
		failure := modelFailure("skill_runtime", err)
		if appendErr := appendEvent(projector.Failure(
			AssistantStreamEventFailed,
			map[string]any{"status": "failed"},
			failure,
		)); appendErr != nil {
			return events, nil, appendErr
		}
		return events, &failure, nil
	}
	log.Printf("assistant agent skill_selected turnId=%s skillId=%s domainId=%s displayName=%s durationMs=%d", turn.TurnID, skill.SkillID, skill.DomainID, skill.DisplayName, skillDurationMs)
	if err := appendEvent(projector.Event(
		AssistantStreamEventProcessAppend,
		userProcessPayload(assistant.AssistantRunVisibleProcess{
			ProcessID: userProcessID(assistantUserProcessStageSkillSelection, 0),
			Scope:     assistantUserProcessScopeRoot,
			Stage:     assistantUserProcessStageSkillSelection,
			Status:    assistantUserProcessStatusCompleted,
			Order:     1,
			SkillID:   skill.SkillID,
			DomainID:  skill.DomainID,
		}),
	)); err != nil {
		return nil, nil, err
	}
	if err := appendEvent(projector.Event(
		AssistantStreamEventProcessAppend,
		userProcessPayload(assistant.AssistantRunVisibleProcess{
			ProcessID: userProcessID(assistantUserProcessStagePlanning, 1),
			Scope:     assistantUserProcessScopeSkill,
			Stage:     assistantUserProcessStagePlanning,
			Status:    assistantUserProcessStatusActive,
			Order:     2,
			SkillID:   skill.SkillID,
			DomainID:  skill.DomainID,
		}),
	)); err != nil {
		return nil, nil, err
	}
	var streamedFailure *rtfailures.Failure
	var answerStreamStartedAt time.Time
	answerProcessStarted := false
	reactStartedAt := time.Now()
	result, err := l.React.RunWithFinalTextSink(ctx, turn, skill, func(step ReactStepResult) error {
		return emitReactReasoning(projector, appendEvent, turn, skill, step)
	}, func(step ReactStepResult) error {
		failure, err := emitReactObservation(projector, appendEvent, turn, skill, step)
		if failure != nil {
			streamedFailure = failure
		}
		return err
	}, func(delta ModelTextDelta) error {
		if answerStreamStartedAt.IsZero() {
			answerStreamStartedAt = time.Now()
		}
		if !answerProcessStarted {
			if err := appendEvent(projector.Event(
				AssistantStreamEventProcessAppend,
				userProcessPayload(assistant.AssistantRunVisibleProcess{
					ProcessID: userProcessID(assistantUserProcessStageAnswerGeneration, 0),
					Scope:     assistantUserProcessScopeAggregation,
					Stage:     assistantUserProcessStageAnswerGeneration,
					Status:    assistantUserProcessStatusActive,
					Order:     999,
					SkillID:   skill.SkillID,
					DomainID:  skill.DomainID,
				}),
			)); err != nil {
				return err
			}
			answerProcessStarted = true
		}
		return appendEvent(projector.Event(AssistantStreamEventAnswerDelta, map[string]any{
			"text": delta.Text,
		}))
	})
	reactDurationMs := time.Since(reactStartedAt).Milliseconds()
	if err != nil {
		log.Printf("assistant agent react_failed turnId=%s skillId=%s durationMs=%d err=%v", turn.TurnID, skill.SkillID, reactDurationMs, err)
		failure := modelFailure("react_runtime", err)
		if appendErr := appendEvent(projector.Failure(
			AssistantStreamEventFailed,
			map[string]any{"status": "failed"},
			failure,
		)); appendErr != nil {
			return events, nil, appendErr
		}
		return events, &failure, nil
	}
	log.Printf("assistant agent react_done turnId=%s skillId=%s steps=%d modelInteractions=%d finalLen=%d stopReason=%s durationMs=%d", turn.TurnID, skill.SkillID, len(result.Steps), resultModelInteractionCount(result), len([]rune(result.FinalText)), result.StopReason, reactDurationMs)
	if streamedFailure != nil {
		return events, streamedFailure, nil
	}
	if !result.FinalStreamed {
		answerStreamStartedAt = time.Now()
		if !answerProcessStarted {
			if err := appendEvent(projector.Event(
				AssistantStreamEventProcessAppend,
				userProcessPayload(assistant.AssistantRunVisibleProcess{
					ProcessID: userProcessID(assistantUserProcessStageAnswerGeneration, 0),
					Scope:     assistantUserProcessScopeAggregation,
					Stage:     assistantUserProcessStageAnswerGeneration,
					Status:    assistantUserProcessStatusActive,
					Order:     999,
					SkillID:   skill.SkillID,
					DomainID:  skill.DomainID,
				}),
			)); err != nil {
				return nil, nil, err
			}
			answerProcessStarted = true
		}
		if err := appendEvent(projector.Event(AssistantStreamEventAnswerDelta, map[string]any{
			"text": result.FinalText,
		})); err != nil {
			return nil, nil, err
		}
	}
	if answerProcessStarted {
		if err := appendEvent(projector.Event(
			AssistantStreamEventProcessCommit,
			userProcessPayload(assistant.AssistantRunVisibleProcess{
				ProcessID: userProcessID(assistantUserProcessStageAnswerGeneration, 0),
				Scope:     assistantUserProcessScopeAggregation,
				Stage:     assistantUserProcessStageAnswerGeneration,
				Status:    assistantUserProcessStatusCompleted,
				Order:     999,
				SkillID:   skill.SkillID,
				DomainID:  skill.DomainID,
			}),
		)); err != nil {
			return nil, nil, err
		}
	}
	if err := appendEvent(projector.Event(AssistantStreamEventCompleted, map[string]any{
		"status":      "completed",
		"finalAnswer": result.FinalText,
		"emergedTags": collectEmergedTags(result),
	})); err != nil {
		return nil, nil, err
	}
	answerStreamDurationMs := time.Since(answerStreamStartedAt).Milliseconds()
	totalDurationMs := time.Since(turnStartedAt).Milliseconds()
	log.Printf("assistant agent latency_summary turnId=%s skillMs=%d reactMs=%d answerStreamMs=%d totalMs=%d modelInteractions=%d steps=%d", turn.TurnID, skillDurationMs, reactDurationMs, answerStreamDurationMs, totalDurationMs, resultModelInteractionCount(result), len(result.Steps))
	log.Printf("assistant agent run_completed conversationId=%s turnId=%s events=%d answerLen=%d", turn.ConversationID, turn.TurnID, len(events), len([]rune(result.FinalText)))
	return events, nil, nil
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

func emitReactReasoning(projector *StreamProjector, appendEvent func(streaming.Envelope, error) error, turn assistant.AssistantTurn, skill SkillSelection, step ReactStepResult) error {
	log.Printf("assistant agent react_reasoning turnId=%s skillId=%s iteration=%d tool=%s", turn.TurnID, skill.SkillID, step.Iteration, step.Tool.Requested.ToolName)
	snapshot := buildUnderstandingSnapshotForStep(turn, step)
	if err := appendEvent(projector.Event(
		AssistantStreamEventProcessCommit,
		userProcessPayload(assistant.AssistantRunVisibleProcess{
			ProcessID: userProcessID(assistantUserProcessStagePlanning, step.Iteration),
			Scope:     assistantUserProcessScopeSkill,
			Stage:     assistantUserProcessStagePlanning,
			Status:    assistantUserProcessStatusCompleted,
			Order:     step.Iteration*10 + 2,
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
			AssistantStreamEventProcessAppend,
			userProcessPayload(assistant.AssistantRunVisibleProcess{
				ProcessID: userProcessID(assistantUserProcessStageToolExecution, step.Iteration),
				Scope:     assistantUserProcessScopeSkill,
				Stage:     assistantUserProcessStageToolExecution,
				Status:    assistantUserProcessStatusActive,
				Order:     step.Iteration*10 + 3,
				SkillID:   skill.SkillID,
				DomainID:  skill.DomainID,
			}),
		)); err != nil {
			return err
		}
	}
	return nil
}

func emitReactObservation(projector *StreamProjector, appendEvent func(streaming.Envelope, error) error, turn assistant.AssistantTurn, skill SkillSelection, step ReactStepResult) (*rtfailures.Failure, error) {
	log.Printf("assistant agent react_step turnId=%s skillId=%s iteration=%d tool=%s observationLen=%d replan=%t", turn.TurnID, skill.SkillID, step.Iteration, step.Tool.Requested.ToolName, len([]rune(step.Observation.Summary)), step.Replan)
	if step.Tool.Failure != nil {
		log.Printf("assistant agent tool_failed turnId=%s skillId=%s iteration=%d tool=%s code=%s", turn.TurnID, skill.SkillID, step.Iteration, step.Tool.Requested.ToolName, step.Tool.Failure.Code)
		if err := appendEvent(projector.Event(
			AssistantStreamEventProcessCommit,
			userProcessPayload(assistant.AssistantRunVisibleProcess{
				ProcessID: userProcessID(assistantUserProcessStageToolExecution, step.Iteration),
				Scope:     assistantUserProcessScopeSkill,
				Stage:     assistantUserProcessStageToolExecution,
				Status:    assistantUserProcessStatusFailed,
				Order:     step.Iteration*10 + 3,
				SkillID:   skill.SkillID,
				DomainID:  skill.DomainID,
			}),
		)); err != nil {
			return nil, err
		}
		if err := appendEvent(projector.Failure(AssistantStreamEventFailed, map[string]any{
			"status": "failed",
		}, *step.Tool.Failure)); err != nil {
			return nil, err
		}
		return step.Tool.Failure, nil
	}
	retrievalProcessing := buildRetrievalProcessingForStep(step)
	if err := appendEvent(projector.Event(
		AssistantStreamEventProcessCommit,
		userProcessPayload(assistant.AssistantRunVisibleProcess{
			ProcessID:              userProcessID(assistantUserProcessStageToolExecution, step.Iteration),
			Scope:                  assistantUserProcessScopeSkill,
			Stage:                  assistantUserProcessStageToolExecution,
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
		AssistantStreamEventProcessAppend,
		userProcessPayload(assistant.AssistantRunVisibleProcess{
			ProcessID: userProcessID(assistantUserProcessStageEvidenceReview, step.Iteration),
			Scope:     assistantUserProcessScopeSkill,
			Stage:     assistantUserProcessStageEvidenceReview,
			Status:    assistantUserProcessStatusActive,
			Order:     step.Iteration*10 + 4,
			SkillID:   skill.SkillID,
			DomainID:  skill.DomainID,
		}),
	)); err != nil {
		return nil, err
	}
	if err := appendEvent(projector.Event(
		AssistantStreamEventProcessCommit,
		userProcessPayload(assistant.AssistantRunVisibleProcess{
			ProcessID:              userProcessID(assistantUserProcessStageEvidenceReview, step.Iteration),
			Scope:                  assistantUserProcessScopeSkill,
			Stage:                  assistantUserProcessStageEvidenceReview,
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
			AssistantStreamEventProcessAppend,
			userProcessPayload(assistant.AssistantRunVisibleProcess{
				ProcessID: userProcessID(assistantUserProcessStagePlanning, step.Iteration+1),
				Scope:     assistantUserProcessScopeSkill,
				Stage:     assistantUserProcessStagePlanning,
				Status:    assistantUserProcessStatusActive,
				Order:     (step.Iteration+1)*10 + 2,
				SkillID:   skill.SkillID,
				DomainID:  skill.DomainID,
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

func modelFailure(stage string, err error) rtfailures.Failure {
	return rtfailures.Failure{
		Code:   "ASSISTANT.MIDDLEWARE.model_runtime_failed",
		Origin: rtfailures.OriginRemoteDependency,
		Kind:   rtfailures.KindModel,
		Nature: rtfailures.NatureTransient,
		Location: rtfailures.Location{
			BusinessObject: "assistant_turn",
			FunctionModule: "assistant_agent_loop",
		},
		Context: rtfailures.Context{Attributes: []rtfailures.ContextAttribute{
			{Key: "stage", Value: stage},
			{Key: "reason", Value: err.Error()},
		}},
	}.Normalized()
}

func buildSearchPlansForStep(turn assistant.AssistantTurn, skill SkillSelection, step ReactStepResult) []map[string]any {
	query := turn.Input.Text
	if step.Tool.Requested.Input != nil {
		if value, ok := step.Tool.Requested.Input["query"].(string); ok && value != "" {
			query = value
		}
		if plans := searchPlansFromToolInput(step.Tool.Requested.Input, step.Tool.Requested.ToolName); len(plans) > 0 {
			return plans
		}
	}
	return []map[string]any{{
		"query":          query,
		"label":          "综合检索",
		"purpose":        "",
		"sourceType":     step.Tool.Requested.ToolName,
		"freshnessHours": 24,
	}}
}

func searchPlansFromToolInput(input map[string]any, toolName string) []map[string]any {
	for _, key := range []string{"searchQueries", "queries"} {
		if plans := searchPlansFromRaw(input[key], toolName); len(plans) > 0 {
			return plans
		}
	}
	return nil
}

func searchPlansFromRaw(raw any, toolName string) []map[string]any {
	switch items := raw.(type) {
	case []any:
		plans := []map[string]any{}
		for _, item := range items {
			if plan := searchPlanFromAny(item, toolName); len(plan) > 0 {
				plans = append(plans, plan)
			}
		}
		return plans
	case []map[string]any:
		plans := []map[string]any{}
		for _, item := range items {
			if plan := searchPlanFromAny(item, toolName); len(plan) > 0 {
				plans = append(plans, plan)
			}
		}
		return plans
	case []string:
		plans := []map[string]any{}
		for _, item := range items {
			if plan := searchPlanFromAny(item, toolName); len(plan) > 0 {
				plans = append(plans, plan)
			}
		}
		return plans
	default:
		return nil
	}
}

func searchPlanFromAny(raw any, toolName string) map[string]any {
	switch item := raw.(type) {
	case string:
		query := strings.TrimSpace(item)
		if query == "" {
			return nil
		}
		return map[string]any{
			"query":          query,
			"label":          "检索",
			"purpose":        "",
			"sourceType":     toolName,
			"freshnessHours": 24,
		}
	case map[string]any:
		query := strings.TrimSpace(stringValue(item["query"]))
		if query == "" {
			return nil
		}
		label := strings.TrimSpace(stringValue(item["dimension"]))
		if label == "" {
			label = strings.TrimSpace(stringValue(item["label"]))
		}
		if label == "" {
			label = "检索"
		}
		return map[string]any{
			"query":          query,
			"label":          label,
			"purpose":        strings.TrimSpace(stringValue(item["purpose"])),
			"sourceType":     toolName,
			"freshnessHours": 24,
		}
	default:
		return nil
	}
}

func buildAcceptedSearchPlansForStep(turn assistant.AssistantTurn, skill SkillSelection, step ReactStepResult) []map[string]any {
	plans := buildSearchPlansForStep(turn, skill, step)
	for i := range plans {
		plans[i]["acceptReason"] = ""
	}
	return plans
}

func deltaNestedString(delta map[string]any, parentKey, childKey string) string {
	if delta == nil {
		return ""
	}
	raw, ok := delta[parentKey]
	if !ok {
		return ""
	}
	nested, ok := raw.(map[string]any)
	if !ok {
		return ""
	}
	return strings.TrimSpace(fmt.Sprint(nested[childKey]))
}

func stringSliceFromAny(raw any) []string {
	switch items := raw.(type) {
	case []any:
		out := []string{}
		for _, item := range items {
			text := strings.TrimSpace(fmt.Sprint(item))
			if text != "" {
				out = append(out, text)
			}
		}
		return out
	case []string:
		out := []string{}
		for _, item := range items {
			text := strings.TrimSpace(item)
			if text != "" {
				out = append(out, text)
			}
		}
		return out
	default:
		return []string{}
	}
}

func referencesFromEvidence(raw any) []map[string]any {
	switch items := raw.(type) {
	case []any:
		out := []map[string]any{}
		for _, item := range items {
			entry, ok := item.(map[string]any)
			if !ok {
				continue
			}
			out = append(out, entry)
		}
		return out
	case []map[string]any:
		return items
	default:
		return nil
	}
}

func buildUnderstandingSnapshotForStep(turn assistant.AssistantTurn, step ReactStepResult) map[string]any {
	delta := step.StructuredDelta
	stageNarrative := strings.TrimSpace(fmt.Sprint(delta["stageNarrative"]))
	if stageNarrative == "<nil>" {
		stageNarrative = ""
	}
	summary := stageNarrative
	if summary == "" {
		summary = deltaNestedString(delta, "understandingSnapshot", "userFacingSummary")
	}
	retrieval := ""
	if stageNarrative == "" {
		retrieval = deltaNestedString(delta, "understandingSnapshot", "retrievalDesignNarrative")
	}
	return map[string]any{
		"intentSummary":            turn.Input.Text,
		"userFacingSummary":        summary,
		"retrievalDesignNarrative": retrieval,
		"concernPoints":            []string{},
		"emotionSignal":            "",
		"resolutionItems":          []map[string]any{},
		"assumptions":              []string{},
		"mismatchSignal":           "",
		"carryForwardFacts":        []string{},
		"discardedAssumptions":     []string{},
	}
}

func buildRetrievalProcessingForStep(step ReactStepResult) map[string]any {
	delta := step.EvidenceStructuredDelta
	summary := ""
	keyPoints := []string{}
	modelRefs := []map[string]any(nil)
	if delta != nil {
		if rp, ok := delta["retrievalProcessing"].(map[string]any); ok {
			summary = strings.TrimSpace(fmt.Sprint(rp["processingSummary"]))
			keyPoints = stringSliceFromAny(rp["selectedKeyPoints"])
			modelRefs = referencesFromEvidence(rp["acceptedReferences"])
		}
	}
	reliable := toolResultReliable(step)
	toolRefs := []map[string]any{}
	if reliable {
		toolRefs = acceptedReferencesForStep(step)
	}
	searchedCount := len(toolRefs)
	if reliable {
		referencesCountFallback := searchedCount == 0 && !step.Observation.Empty
		if referencesCountFallback {
			searchedCount = 1
		}
	}
	acceptedRefs := []map[string]any{}
	if reliable {
		acceptedRefs = MergeReferences(modelRefs, toolRefs)
	}
	return map[string]any{
		"searchedDocumentCount":  searchedCount,
		"processedDocumentCount": searchedCount,
		"acceptedDocumentCount":  len(acceptedRefs),
		"processingSummary":      summary,
		"selectedKeyPoints":      keyPoints,
		"expansionReason":        "",
		"acceptedReferences":     acceptedRefs,
	}
}

func MergeReferences(primary []map[string]any, fallback []map[string]any) []map[string]any {
	merged := []map[string]any{}
	seen := map[string]bool{}
	authoritative := map[string]map[string]any{}
	for _, reference := range fallback {
		key, ok := referenceDestinationKey(reference)
		if !ok {
			continue
		}
		authoritative[key] = reference
	}
	appendOne := func(reference map[string]any) {
		if len(merged) >= 5 {
			return
		}
		key, ok := referenceDestinationKey(reference)
		if !ok || seen[key] {
			return
		}
		authoritativeReference, exists := authoritative[key]
		if !exists {
			return
		}
		seen[key] = true
		merged = append(merged, authoritativeReference)
	}
	for _, reference := range primary {
		canonical, ok := canonicalModelReference(reference)
		if ok {
			appendOne(canonical)
		}
	}
	for _, reference := range fallback {
		appendOne(reference)
	}
	return merged
}

// collectEmergedTags 汇总本轮 ReAct 各步 app_search 命中内容的类目（categoryId / subCategory），
// 去重后归到 Topic 维度生成路径制 tagRef，作为对话浮现的兴趣标签随 turn.completed 下发，
// 供端侧合成 assistant_interest 行为回流推荐特征（rm_recommend_feature）。
func collectEmergedTags(result ReactResult) []string {
	seen := map[string]struct{}{}
	tags := []string{}
	add := func(value string) {
		value = strings.TrimSpace(value)
		if value == "" {
			return
		}
		tagRef := "Topic/" + value
		if _, ok := seen[tagRef]; ok {
			return
		}
		seen[tagRef] = struct{}{}
		tags = append(tags, tagRef)
	}
	consume := func(m map[string]any) {
		add(stringValue(m["categoryId"]))
		add(stringValue(m["subCategory"]))
	}
	for _, step := range result.Steps {
		raw, ok := step.Tool.Completed.Result["results"]
		if !ok {
			continue
		}
		switch items := raw.(type) {
		case []any:
			for _, item := range items {
				if m, ok := item.(map[string]any); ok {
					consume(m)
				}
			}
		case []map[string]any:
			for _, m := range items {
				consume(m)
			}
		}
	}
	return tags
}

func toolResultReliable(step ReactStepResult) bool {
	result := step.Tool.Completed.Result
	if result == nil {
		return false
	}
	reliable, ok := result["reliable"].(bool)
	if !ok {
		return true
	}
	return reliable
}

func acceptedReferencesForStep(step ReactStepResult) []map[string]any {
	result := step.Tool.Completed.Result
	raw, ok := result["references"]
	if !ok {
		raw, ok = result["citations"]
		if !ok {
			return []map[string]any{}
		}
	}
	references := []map[string]any{}
	appendEntry := func(entry map[string]any) {
		reference, valid := CanonicalToolReference(entry)
		if !valid {
			return
		}
		references = append(references, reference)
	}
	switch items := raw.(type) {
	case []any:
		for _, item := range items {
			entry, ok := item.(map[string]any)
			if !ok {
				continue
			}
			appendEntry(entry)
			if len(references) >= 5 {
				break
			}
		}
	case []map[string]any:
		for _, entry := range items {
			appendEntry(entry)
			if len(references) >= 5 {
				break
			}
		}
	}
	return references
}

func referenceDestinationKey(reference map[string]any) (string, bool) {
	rawDestination, ok := reference["destination"].(map[string]any)
	if !ok {
		return "", false
	}
	destination, ok := citationDestinationFromMap(rawDestination)
	if !ok {
		return "", false
	}
	switch destination.Kind {
	case string(assistantgenerated.CitationDestinationKindInternal):
		return destination.Kind + ":" + destination.ObjectTypeRef + ":" + destination.ObjectID, true
	case string(assistantgenerated.CitationDestinationKindExternal):
		return destination.Kind + ":" + destination.URL, true
	default:
		return "", false
	}
}

func stringValue(value any) string {
	if value == nil {
		return ""
	}
	text := fmt.Sprint(value)
	if text == "<nil>" {
		return ""
	}
	return text
}
