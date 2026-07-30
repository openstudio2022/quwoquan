package orchestration

import (
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/streaming"
	"strings"

	"quwoquan_service/runtime/streaming"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_conversation"
	contextassembly "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/contextassembly"
	react "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/reasoning"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

func streamContextClarification(
	turn assistant.AssistantTurn,
	skill SkillSelection,
	assembly contextassembly.AssemblyResult,
	projector *assistantstreaming.StreamProjector,
	appendEvent func(streaming.Envelope, error) error,
) error {
	task := assembly.FillTasks[0]
	ask := &react.AskUser{
		SlotID:      task.SlotID,
		Prompt:      strings.TrimSpace(task.Prompt),
		Required:    task.Required,
		Suggestions: append([]string(nil), task.Suggestions...),
	}
	if ask.Prompt == "" {
		ask.Prompt = "请补充完成这件事所需的关键信息。"
	}
	process := assistant.AssistantRunVisibleProcess{
		ProcessID:  userProcessID(assistantUserProcessPhaseClarifying, 0),
		Scope:      assistantUserProcessScopeAggregation,
		Stage:      assistantUserProcessPhaseClarifying.WireName(),
		ActionCode: assistantgenerated.PlannerActionCodeAskClarification.WireName(),
		Status:     assistantUserProcessStatusActive,
		Order:      999,
		SkillID:    skill.SkillID,
		DomainID:   skill.DomainID,
	}
	if err := appendEvent(projector.Event(
		assistantstreaming.AssistantStreamEventProcessAppend,
		userProcessPayload(process),
	)); err != nil {
		return err
	}
	if err := appendEvent(projector.Event(
		assistantstreaming.AssistantStreamEventAnswerDelta,
		map[string]any{"text": ask.Prompt},
	)); err != nil {
		return err
	}
	process.Status = assistantUserProcessStatusCompleted
	if err := appendEvent(projector.Event(
		assistantstreaming.AssistantStreamEventProcessCommit,
		userProcessPayload(process),
	)); err != nil {
		return err
	}
	result := ReactResult{
		FinalText:  ask.Prompt,
		AskUser:    ask,
		StopReason: "context_fill_required",
	}
	skillRuns := []SkillRunOutcome{
		skillRunOutcomeFrom(skillRunID(0, skill.SkillID), skill, result),
	}
	aggregation := ResolveAggregation(skillRuns)
	payload := map[string]any{
		"status":            "completed",
		"finalAnswer":       result.FinalText,
		"emergedTags":       []string{},
		"policyAttribution": boundedPolicyAttribution(turn),
		"messageKind":       aggregation.MessageKind().WireName(),
		"finalAnswerMode":   aggregation.FinalAnswerMode.WireName(),
		"aggregationState":  aggregation.payload(),
		"skillRuns":         skillRunPayloads(skillRuns),
		"askUser":           askUserPayload(ask),
	}
	return appendEvent(projector.Event(assistantstreaming.AssistantStreamEventCompleted, payload))
}
