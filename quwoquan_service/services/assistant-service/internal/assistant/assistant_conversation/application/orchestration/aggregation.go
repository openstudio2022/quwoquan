package orchestration

import (
	"fmt"
	"strings"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_conversation"
	react "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/reasoning"
)

// SkillRunOutcome 是一次 skill 执行的可聚合投影，形状对齐契约 _shared/skill_run。
// 单技能与多技能共用同一条通道：单技能只是长度为 1 的 skillRuns。
type SkillRunOutcome struct {
	RunID          string
	SkillID        string
	DomainID       string
	Goal           string
	ProblemClass   string
	Role           string
	AnswerReady    bool
	StopReason     string
	ResultSummary  string
	ToolNames      []string
	ReferenceCount int
	AskUser        *react.AskUser
}

// AggregationOutcome 是聚合裁决结果，形状对齐契约 _shared/aggregation_state。
type AggregationOutcome struct {
	AllSkillsReady       bool
	BlockingSkills       []string
	CanGivePartialAnswer bool
	FinalAnswerReady     bool
	FinalAnswerMode      assistantgenerated.FinalAnswerMode
	ClarificationNeeded  bool
	AnswerOwner          string
	ClarificationSource  string
}

// 能被视为「该技能已经拿到完整回答」的收尾原因。其余收尾原因都只允许有界回答。
var completeStopReasons = map[string]bool{
	"observation_sufficient":       true,
	"model_answered_without_tools": true,
}

func skillRunOutcomeFrom(runID string, skill SkillSelection, result ReactResult) SkillRunOutcome {
	outcome := SkillRunOutcome{
		RunID:         runID,
		SkillID:       skill.SkillID,
		DomainID:      skill.DomainID,
		ProblemClass:  skill.ProblemClass,
		StopReason:    result.StopReason,
		ResultSummary: firstLine(result.FinalText),
		AskUser:       result.AskUser,
	}
	for _, step := range result.Steps {
		toolName := strings.TrimSpace(step.Tool.Requested.ToolName)
		if toolName != "" {
			outcome.ToolNames = append(outcome.ToolNames, toolName)
		}
		processing := buildRetrievalProcessingForStep(step)
		outcome.ReferenceCount += intValue(processing["acceptedDocumentCount"])
	}
	outcome.AnswerReady = result.AskUser == nil &&
		strings.TrimSpace(result.FinalText) != "" &&
		completeStopReasons[result.StopReason]
	return outcome
}

// ResolveAggregation 裁决 finalAnswerMode：反问优先，其次是全部就绪、部分证据、完全阻塞。
func ResolveAggregation(runs []SkillRunOutcome) AggregationOutcome {
	outcome := AggregationOutcome{
		FinalAnswerMode: assistantgenerated.FinalAnswerModeBlocked,
	}
	if len(runs) == 0 {
		return outcome
	}
	readyCount := 0
	answeredCount := 0
	for _, run := range runs {
		if run.AskUser != nil {
			outcome.ClarificationNeeded = true
			if outcome.ClarificationSource == "" {
				outcome.ClarificationSource = run.SkillID
			}
			outcome.BlockingSkills = append(outcome.BlockingSkills, run.SkillID)
			continue
		}
		if run.AnswerReady {
			readyCount++
			answeredCount++
			if outcome.AnswerOwner == "" {
				outcome.AnswerOwner = run.SkillID
			}
			continue
		}
		outcome.BlockingSkills = append(outcome.BlockingSkills, run.SkillID)
		if strings.TrimSpace(run.ResultSummary) != "" {
			answeredCount++
			if outcome.AnswerOwner == "" {
				outcome.AnswerOwner = run.SkillID
			}
		}
	}
	switch {
	case outcome.ClarificationNeeded:
		outcome.FinalAnswerMode = assistantgenerated.FinalAnswerModeClarify
	case readyCount == len(runs):
		outcome.AllSkillsReady = true
		outcome.FinalAnswerReady = true
		outcome.FinalAnswerMode = assistantgenerated.FinalAnswerModeFull
	case answeredCount > 0:
		outcome.CanGivePartialAnswer = true
		outcome.FinalAnswerReady = true
		outcome.FinalAnswerMode = assistantgenerated.FinalAnswerModeBoundedAnswer
	}
	return outcome
}

// MessageKind 说明该次运行给用户的消息类型：反问、错误还是回答。
func (outcome AggregationOutcome) MessageKind() assistantgenerated.AssistantMessageKind {
	switch {
	case outcome.ClarificationNeeded:
		return assistantgenerated.AssistantMessageKindAskUser
	case outcome.FinalAnswerMode == assistantgenerated.FinalAnswerModeBlocked:
		return assistantgenerated.AssistantMessageKindFallback
	default:
		return assistantgenerated.AssistantMessageKindAnswer
	}
}

func (outcome AggregationOutcome) payload() map[string]any {
	blocking := outcome.BlockingSkills
	if blocking == nil {
		blocking = []string{}
	}
	return map[string]any{
		"allSkillsReady":       outcome.AllSkillsReady,
		"blockingSkills":       blocking,
		"canGivePartialAnswer": outcome.CanGivePartialAnswer,
		"finalAnswerReady":     outcome.FinalAnswerReady,
		"finalAnswerMode":      outcome.FinalAnswerMode.WireName(),
		"clarificationNeeded":  outcome.ClarificationNeeded,
		"answerOwner":          outcome.AnswerOwner,
		"clarificationSource":  outcome.ClarificationSource,
	}
}

func skillRunPayloads(runs []SkillRunOutcome) []map[string]any {
	payloads := make([]map[string]any, 0, len(runs))
	for _, run := range runs {
		toolNames := run.ToolNames
		if toolNames == nil {
			toolNames = []string{}
		}
		payloads = append(payloads, map[string]any{
			"runId":          run.RunID,
			"skillId":        run.SkillID,
			"domainId":       run.DomainID,
			"goal":           run.Goal,
			"problemClass":   run.ProblemClass,
			"role":           run.Role,
			"answerReady":    run.AnswerReady,
			"stopReason":     run.StopReason,
			"resultSummary":  run.ResultSummary,
			"toolNames":      toolNames,
			"referenceCount": run.ReferenceCount,
		})
	}
	return payloads
}

func askUserPayload(ask *react.AskUser) map[string]any {
	if ask == nil {
		return nil
	}
	suggestions := ask.Suggestions
	if suggestions == nil {
		suggestions = []string{}
	}
	return map[string]any{
		"slotId":      ask.SlotID,
		"prompt":      ask.Prompt,
		"required":    ask.Required,
		"suggestions": suggestions,
	}
}

func skillRunID(index int, skillID string) string {
	return fmt.Sprintf("run:%d:%s", index+1, skillID)
}

func firstLine(text string) string {
	trimmed := strings.TrimSpace(text)
	if trimmed == "" {
		return ""
	}
	if newline := strings.IndexRune(trimmed, '\n'); newline > 0 {
		trimmed = strings.TrimSpace(trimmed[:newline])
	}
	if runes := []rune(trimmed); len(runes) > 160 {
		return string(runes[:160]) + "…"
	}
	return trimmed
}
