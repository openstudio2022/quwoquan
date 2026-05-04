package application

import (
	"context"
	"fmt"
	"log"
	"strings"
	"time"

	rtfailures "quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type AgentLoop struct {
	Skills       SkillRuntime
	React        ReactRuntime
	Orchestrator orchestration.PhaseOrchestrator
	Now          func() time.Time
}

func NewAgentLoop(skills SkillRuntime, react ReactRuntime, now func() time.Time) *AgentLoop {
	if skills == nil {
		skills = DefaultSkillRuntime{}
	}
	if react.Model == nil {
		react.Model = DeterministicModelProvider{}
	}
	if react.Tools == nil {
		react.Tools = DefaultToolCoordinator{Now: now}
	}
	return &AgentLoop{Skills: skills, React: react, Orchestrator: orchestration.NewPhaseOrchestrator(now), Now: now}
}

func (l *AgentLoop) RunTurn(ctx context.Context, turn assistant.AssistantTurn) ([]streaming.Envelope, *rtfailures.Failure, error) {
	return l.RunTurnWithSink(ctx, turn, nil)
}

func (l *AgentLoop) RunTurnWithSink(ctx context.Context, turn assistant.AssistantTurn, emit func(streaming.Envelope) error) ([]streaming.Envelope, *rtfailures.Failure, error) {
	if l == nil {
		l = NewAgentLoop(nil, ReactRuntime{}, nil)
	}
	log.Printf("assistant agent turn_started conversationId=%s turnId=%s traceId=%s", turn.ConversationID, turn.TurnID, turn.TraceID)
	projector := NewStreamProjector(turn, l.Now)
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
	if err := appendEvent(projector.Event("assistant.turn.started", map[string]any{
		"status": "running",
		"input":  turn.Input,
	})); err != nil {
		return nil, nil, err
	}
	runState, err := l.orchestrator().Run(ctx, turn)
	if err != nil {
		log.Printf("assistant agent orchestrator_failed turnId=%s err=%v", turn.TurnID, err)
		failure := modelFailure("phase_orchestrator", err)
		events = appendFailureEvents(projector, events, failure)
		return events, &failure, nil
	}
	log.Printf("assistant agent orchestrator_done turnId=%s traceEvents=%d processFrames=%d journeyEntries=%d", turn.TurnID, len(runState.TraceEvents), len(runState.ProcessTimeline), len(runState.Journey.Entries))
	for _, traceEvent := range runState.TraceEvents {
		if err := appendEvent(projector.Event("assistant.trace", map[string]any{
			"traceEvent": traceEvent,
		})); err != nil {
			return nil, nil, err
		}
	}
	if err := appendEvent(projector.Event("assistant.journey.updated", map[string]any{
		"journey": runState.Journey,
	})); err != nil {
		return nil, nil, err
	}
	if err := appendEvent(projector.Event("assistant.process_timeline.updated", map[string]any{
		"processTimeline": runState.ProcessTimeline,
	})); err != nil {
		return nil, nil, err
	}
	skill, err := l.skills().SelectSkill(ctx, turn)
	if err != nil {
		log.Printf("assistant agent skill_select_failed turnId=%s err=%v", turn.TurnID, err)
		failure := modelFailure("skill_runtime", err)
		events = appendFailureEvents(projector, events, failure)
		return events, &failure, nil
	}
	log.Printf("assistant agent skill_selected turnId=%s skillId=%s domainId=%s displayName=%s", turn.TurnID, skill.SkillID, skill.DomainID, skill.DisplayName)
	if err := appendEvent(projector.Event("assistant.skill.selected", map[string]any{
		"skillId":      skill.SkillID,
		"domainId":     skill.DomainID,
		"displayName":  skill.DisplayName,
		"promptPolicy": skill.PromptPolicy,
		"toolPolicy":   skill.ToolPolicy,
	})); err != nil {
		return nil, nil, err
	}
	if err := appendEvent(projector.Event("assistant.reasoning.started", map[string]any{
		"skillId": skill.SkillID,
	})); err != nil {
		return nil, nil, err
	}
	var streamedFailure *rtfailures.Failure
	result, err := l.React.RunWithSinks(ctx, turn, skill, func(step ReactStepResult) error {
		return emitReactReasoning(ctx, projector, appendEvent, turn, skill, step, emit != nil)
	}, func(step ReactStepResult) error {
		failure, err := emitReactObservation(ctx, projector, appendEvent, turn, skill, step, emit != nil)
		if failure != nil {
			streamedFailure = failure
		}
		return err
	})
	if err != nil {
		log.Printf("assistant agent react_failed turnId=%s skillId=%s err=%v", turn.TurnID, skill.SkillID, err)
		failure := modelFailure("react_runtime", err)
		events = appendFailureEvents(projector, events, failure)
		return events, &failure, nil
	}
	log.Printf("assistant agent react_done turnId=%s skillId=%s steps=%d finalLen=%d stopReason=%s", turn.TurnID, skill.SkillID, len(result.Steps), len([]rune(result.FinalText)), result.StopReason)
	if streamedFailure != nil {
		return events, streamedFailure, nil
	}
	if len(result.Steps) == 0 {
		if err := appendEvent(projector.Event("assistant.model.delta", map[string]any{
			"text":      result.ModelDelta,
			"stage":     "reasoning",
			"skillId":   skill.SkillID,
			"reasoning": result.ReasoningText,
		})); err != nil {
			return nil, nil, err
		}
	}
	if len(result.FinalClientTrace) > 0 {
		if err := appendEvent(projector.Event("assistant.model.interaction", result.FinalClientTrace)); err != nil {
			return nil, nil, err
		}
	}
	answerDeltas := splitAnswerDeltas(result.FinalText)
	if err := appendEvent(projector.Event("assistant.answer.delta", map[string]any{
		"text": answerDeltas[0],
	})); err != nil {
		return nil, nil, err
	}
	pauseForVisibleStream(ctx, emit)
	for _, delta := range answerDeltas[1:] {
		if err := appendEvent(projector.Event("assistant.answer.delta", map[string]any{
			"text": delta,
		})); err != nil {
			return nil, nil, err
		}
		pauseForVisibleStream(ctx, emit)
	}
	if err := appendEvent(projector.Event("assistant.answer.final", map[string]any{
		"text":       result.FinalText,
		"stopReason": result.StopReason,
	})); err != nil {
		return nil, nil, err
	}
	if err := appendEvent(projector.Event("assistant.turn.completed", map[string]any{
		"status": "completed",
	})); err != nil {
		return nil, nil, err
	}
	log.Printf("assistant agent turn_completed conversationId=%s turnId=%s events=%d answerLen=%d", turn.ConversationID, turn.TurnID, len(events), len([]rune(result.FinalText)))
	return events, nil, nil
}

func pauseForVisibleStream(ctx context.Context, emit func(streaming.Envelope) error) {
	if emit == nil {
		return
	}
	timer := time.NewTimer(220 * time.Millisecond)
	defer timer.Stop()
	select {
	case <-ctx.Done():
	case <-timer.C:
	}
}

func pauseForVisibleProjection(ctx context.Context, enabled bool) {
	if !enabled {
		return
	}
	timer := time.NewTimer(350 * time.Millisecond)
	defer timer.Stop()
	select {
	case <-ctx.Done():
	case <-timer.C:
	}
}

func progressiveSnapshotFrames(snapshot map[string]any, field string) []map[string]any {
	text := strings.TrimSpace(stringValue(snapshot[field]))
	if text == "" {
		return []map[string]any{snapshot}
	}
	runes := []rune(text)
	if len(runes) <= 90 {
		return []map[string]any{snapshot}
	}
	breakpoints := []int{len(runes) / 3, len(runes) * 2 / 3, len(runes)}
	frames := []map[string]any{}
	seen := map[int]bool{}
	for _, end := range breakpoints {
		if end <= 0 || seen[end] {
			continue
		}
		seen[end] = true
		frame := copyStringAnyMap(snapshot)
		frame[field] = string(runes[:end])
		frames = append(frames, frame)
	}
	if len(frames) == 0 {
		return []map[string]any{snapshot}
	}
	return frames
}

func copyStringAnyMap(input map[string]any) map[string]any {
	out := make(map[string]any, len(input))
	for key, value := range input {
		out[key] = value
	}
	return out
}

func emitReactReasoning(ctx context.Context, projector *StreamProjector, appendEvent func(streaming.Envelope, error) error, turn assistant.AssistantTurn, skill SkillSelection, step ReactStepResult, visibleStream bool) error {
	log.Printf("assistant agent react_reasoning turnId=%s skillId=%s iteration=%d tool=%s", turn.TurnID, skill.SkillID, step.Iteration, step.Tool.Requested.ToolName)
	for _, interaction := range step.ModelInteractions {
		if len(interaction) == 0 {
			continue
		}
		if err := appendEvent(projector.Event("assistant.model.interaction", interaction)); err != nil {
			return err
		}
	}
	snapshot := buildUnderstandingSnapshotForStep(turn, step)
	for _, frame := range progressiveSnapshotFrames(snapshot, "userFacingSummary") {
		if err := appendEvent(projector.Event("assistant.plan.updated", map[string]any{
			"iteration":             step.Iteration,
			"skillId":               skill.SkillID,
			"plan":                  step.Plan,
			"understandingSnapshot": frame,
			"debugTrace":            map[string]any{"reasoning": step.ReasoningText},
		})); err != nil {
			return err
		}
		pauseForVisibleProjection(ctx, visibleStream)
	}
	if err := appendEvent(projector.Event("assistant.model.delta", map[string]any{
		"text":      step.ModelDelta,
		"stage":     "reasoning",
		"skillId":   skill.SkillID,
		"iteration": step.Iteration,
		"reasoning": step.ReasoningText,
	})); err != nil {
		return err
	}
	if err := appendEvent(projector.Event("assistant.search_query.generated", map[string]any{
		"iteration":   step.Iteration,
		"skillId":     skill.SkillID,
		"searchPlans": buildSearchPlansForStep(turn, skill, step),
		"debugTrace":  map[string]any{"structuredDelta": step.StructuredDelta},
	})); err != nil {
		return err
	}
	if err := appendEvent(projector.Event("assistant.search_query.accepted", map[string]any{
		"iteration":           step.Iteration,
		"skillId":             skill.SkillID,
		"acceptedSearchPlans": buildAcceptedSearchPlansForStep(turn, skill, step),
	})); err != nil {
		return err
	}
	return nil
}

func emitReactObservation(ctx context.Context, projector *StreamProjector, appendEvent func(streaming.Envelope, error) error, turn assistant.AssistantTurn, skill SkillSelection, step ReactStepResult, visibleStream bool) (*rtfailures.Failure, error) {
	log.Printf("assistant agent react_step turnId=%s skillId=%s iteration=%d tool=%s observationLen=%d replan=%t", turn.TurnID, skill.SkillID, step.Iteration, step.Tool.Requested.ToolName, len([]rune(step.Observation.Summary)), step.Replan)
	evidenceInteractions := []map[string]any{}
	if len(step.ModelInteractions) > 1 {
		evidenceInteractions = step.ModelInteractions[1:]
	}
	for _, interaction := range evidenceInteractions {
		if len(interaction) == 0 {
			continue
		}
		if err := appendEvent(projector.Event("assistant.model.interaction", interaction)); err != nil {
			return nil, err
		}
	}
	if err := appendEvent(projector.Event("assistant.tool.requested", map[string]any{
		"toolUse": step.Tool.Requested,
	})); err != nil {
		return nil, err
	}
	if step.Tool.Failure != nil {
		log.Printf("assistant agent tool_failed turnId=%s skillId=%s iteration=%d tool=%s code=%s", turn.TurnID, skill.SkillID, step.Iteration, step.Tool.Requested.ToolName, step.Tool.Failure.Code)
		if err := appendEvent(projector.Failure("assistant.failure", map[string]any{
			"toolUse": step.Tool.Completed,
			"stage":   "tool",
		}, *step.Tool.Failure)); err != nil {
			return nil, err
		}
		if err := appendEvent(projector.Failure("assistant.turn.failed", map[string]any{
			"status": "failed",
		}, *step.Tool.Failure)); err != nil {
			return nil, err
		}
		return step.Tool.Failure, nil
	}
	if step.Tool.Completed.Status == "waiting_confirmation" {
		if err := appendEvent(projector.Event("assistant.user_confirmation.requested", map[string]any{
			"toolUse": step.Tool.Completed,
		})); err != nil {
			return nil, err
		}
	}
	if err := appendEvent(projector.Event("assistant.tool.completed", map[string]any{
		"toolUse": step.Tool.Completed,
	})); err != nil {
		return nil, err
	}
	log.Printf("assistant agent tool_completed turnId=%s skillId=%s iteration=%d tool=%s status=%s", turn.TurnID, skill.SkillID, step.Iteration, step.Tool.Completed.ToolName, step.Tool.Completed.Status)
	retrievalProcessing := buildRetrievalProcessingForStep(step)
	for _, frame := range progressiveSnapshotFrames(retrievalProcessing, "processingSummary") {
		if err := appendEvent(projector.Event("assistant.observation.assessed", map[string]any{
			"iteration":           step.Iteration,
			"skillId":             skill.SkillID,
			"observation":         step.Observation,
			"replan":              step.Replan,
			"replanReason":        step.ReplanReason,
			"retrievalProcessing": frame,
			"readiness": map[string]any{
				"finalAnswerReady": !step.Replan,
				"needReplan":       step.Replan,
			},
		})); err != nil {
			return nil, err
		}
		pauseForVisibleProjection(ctx, visibleStream)
	}
	if step.Replan {
		log.Printf("assistant agent replan_requested turnId=%s skillId=%s iteration=%d reason=%s", turn.TurnID, skill.SkillID, step.Iteration, step.ReplanReason)
		if err := appendEvent(projector.Event("assistant.replan.requested", map[string]any{
			"iteration":    step.Iteration,
			"skillId":      skill.SkillID,
			"replanReason": step.ReplanReason,
		})); err != nil {
			return nil, err
		}
	}
	return nil, nil
}

func emitReactStep(projector *StreamProjector, appendEvent func(streaming.Envelope, error) error, turn assistant.AssistantTurn, skill SkillSelection, step ReactStepResult) (*rtfailures.Failure, error) {
	log.Printf("assistant agent react_step turnId=%s skillId=%s iteration=%d tool=%s observationLen=%d replan=%t", turn.TurnID, skill.SkillID, step.Iteration, step.Tool.Requested.ToolName, len([]rune(step.Observation.Summary)), step.Replan)
	for _, interaction := range step.ModelInteractions {
		if len(interaction) == 0 {
			continue
		}
		if err := appendEvent(projector.Event("assistant.model.interaction", interaction)); err != nil {
			return nil, err
		}
	}
	if err := appendEvent(projector.Event("assistant.plan.updated", map[string]any{
		"iteration":             step.Iteration,
		"skillId":               skill.SkillID,
		"plan":                  step.Plan,
		"understandingSnapshot": buildUnderstandingSnapshotForStep(turn, step),
		"debugTrace":            map[string]any{"reasoning": step.ReasoningText},
	})); err != nil {
		return nil, err
	}
	if err := appendEvent(projector.Event("assistant.model.delta", map[string]any{
		"text":      step.ModelDelta,
		"stage":     "reasoning",
		"skillId":   skill.SkillID,
		"iteration": step.Iteration,
		"reasoning": step.ReasoningText,
	})); err != nil {
		return nil, err
	}
	if err := appendEvent(projector.Event("assistant.search_query.generated", map[string]any{
		"iteration":   step.Iteration,
		"skillId":     skill.SkillID,
		"searchPlans": buildSearchPlansForStep(turn, skill, step),
		"debugTrace":  map[string]any{"structuredDelta": step.StructuredDelta},
	})); err != nil {
		return nil, err
	}
	if err := appendEvent(projector.Event("assistant.search_query.accepted", map[string]any{
		"iteration":           step.Iteration,
		"skillId":             skill.SkillID,
		"acceptedSearchPlans": buildAcceptedSearchPlansForStep(turn, skill, step),
	})); err != nil {
		return nil, err
	}
	if err := appendEvent(projector.Event("assistant.tool.requested", map[string]any{
		"toolUse": step.Tool.Requested,
	})); err != nil {
		return nil, err
	}
	if step.Tool.Failure != nil {
		log.Printf("assistant agent tool_failed turnId=%s skillId=%s iteration=%d tool=%s code=%s", turn.TurnID, skill.SkillID, step.Iteration, step.Tool.Requested.ToolName, step.Tool.Failure.Code)
		if err := appendEvent(projector.Failure("assistant.failure", map[string]any{
			"toolUse": step.Tool.Completed,
			"stage":   "tool",
		}, *step.Tool.Failure)); err != nil {
			return nil, err
		}
		if err := appendEvent(projector.Failure("assistant.turn.failed", map[string]any{
			"status": "failed",
		}, *step.Tool.Failure)); err != nil {
			return nil, err
		}
		return step.Tool.Failure, nil
	}
	if step.Tool.Completed.Status == "waiting_confirmation" {
		if err := appendEvent(projector.Event("assistant.user_confirmation.requested", map[string]any{
			"toolUse": step.Tool.Completed,
		})); err != nil {
			return nil, err
		}
	}
	if err := appendEvent(projector.Event("assistant.tool.completed", map[string]any{
		"toolUse": step.Tool.Completed,
	})); err != nil {
		return nil, err
	}
	log.Printf("assistant agent tool_completed turnId=%s skillId=%s iteration=%d tool=%s status=%s", turn.TurnID, skill.SkillID, step.Iteration, step.Tool.Completed.ToolName, step.Tool.Completed.Status)
	if err := appendEvent(projector.Event("assistant.observation.assessed", map[string]any{
		"iteration":           step.Iteration,
		"skillId":             skill.SkillID,
		"observation":         step.Observation,
		"replan":              step.Replan,
		"replanReason":        step.ReplanReason,
		"retrievalProcessing": buildRetrievalProcessingForStep(step),
		"readiness": map[string]any{
			"finalAnswerReady": !step.Replan,
			"needReplan":       step.Replan,
		},
	})); err != nil {
		return nil, err
	}
	if step.Replan {
		log.Printf("assistant agent replan_requested turnId=%s skillId=%s iteration=%d reason=%s", turn.TurnID, skill.SkillID, step.Iteration, step.ReplanReason)
		if err := appendEvent(projector.Event("assistant.replan.requested", map[string]any{
			"iteration":    step.Iteration,
			"skillId":      skill.SkillID,
			"replanReason": step.ReplanReason,
		})); err != nil {
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

func (l *AgentLoop) orchestrator() orchestration.PhaseOrchestrator {
	if l != nil && len(l.Orchestrator.Phases()) > 0 {
		return l.Orchestrator
	}
	now := func() time.Time { return time.Now().UTC() }
	if l != nil && l.Now != nil {
		now = l.Now
	}
	return orchestration.NewPhaseOrchestrator(now)
}

func appendFailureEvents(projector *StreamProjector, events []streaming.Envelope, failure rtfailures.Failure) []streaming.Envelope {
	if envelope, err := projector.Failure("assistant.failure", map[string]any{"stage": "agent_loop"}, failure); err == nil {
		events = append(events, envelope)
	}
	if envelope, err := projector.Failure("assistant.turn.failed", map[string]any{"status": "failed"}, failure); err == nil {
		events = append(events, envelope)
	}
	return events
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
	if reliable && len(modelRefs) > 0 {
		acceptedRefs = mergeReferences(modelRefs, nil)
	}
	if reliable && len(acceptedRefs) == 0 && searchedCount > 0 && len(toolRefs) > 0 {
		acceptedRefs = []map[string]any{toolRefs[0]}
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

func mergeReferences(primary []map[string]any, fallback []map[string]any) []map[string]any {
	merged := []map[string]any{}
	seen := map[string]bool{}
	appendOne := func(reference map[string]any) {
		if len(merged) >= 5 {
			return
		}
		title := stringValue(reference["title"])
		url := stringValue(reference["url"])
		source := stringValue(reference["source"])
		if title == "" && url == "" && source == "" {
			return
		}
		key := url
		if key == "" {
			key = title + "|" + source
		}
		if seen[key] {
			return
		}
		seen[key] = true
		merged = append(merged, reference)
	}
	for _, reference := range primary {
		appendOne(reference)
	}
	for _, reference := range fallback {
		appendOne(reference)
	}
	return merged
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
		return []map[string]any{}
	}
	references := []map[string]any{}
	appendEntry := func(entry map[string]any) {
		reference := map[string]any{
			"title":   stringValue(entry["title"]),
			"url":     stringValue(entry["url"]),
			"source":  stringValue(entry["source"]),
			"snippet": stringValue(entry["snippet"]),
		}
		if reference["title"] == "" && reference["url"] == "" && reference["source"] == "" {
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

func splitAnswerDeltas(text string) []string {
	if text == "" {
		return []string{""}
	}
	runes := []rune(text)
	chunks := []string{}
	const targetChunkSize = 36
	const maxChunkSize = 52
	for start := 0; start < len(runes); {
		end := start + targetChunkSize
		if end >= len(runes) {
			chunks = append(chunks, string(runes[start:]))
			break
		}
		limit := start + maxChunkSize
		if limit > len(runes) {
			limit = len(runes)
		}
		if boundary := answerChunkBoundary(runes, start, end, limit); boundary > start {
			end = boundary
		}
		chunks = append(chunks, string(runes[start:end]))
		start = end
	}
	return chunks
}

func answerChunkBoundary(runes []rune, start, preferred, limit int) int {
	for i := preferred; i < limit; i++ {
		if isAnswerChunkBoundaryRune(runes[i]) {
			return i + 1
		}
	}
	for i := preferred; i > start; i-- {
		if isAnswerChunkBoundaryRune(runes[i-1]) {
			return i
		}
	}
	return preferred
}

func isAnswerChunkBoundaryRune(r rune) bool {
	switch r {
	case '\n', '。', '！', '？', '；', ';', '.', '!', '?':
		return true
	default:
		return false
	}
}
