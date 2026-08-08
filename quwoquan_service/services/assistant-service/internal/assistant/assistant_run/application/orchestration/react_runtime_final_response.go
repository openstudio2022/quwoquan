package orchestration

import (
	"context"
	"fmt"
	"strings"

	react "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/reasoning"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

// SynthesizeSubagentAnswer 把并行子代理的结论合成一个最终回答。聚合层只通过这一条通道
// 生成最终文本，避免多技能时出现第二套回答生成路径。
func (r ReactRuntime) SynthesizeSubagentAnswer(
	ctx context.Context,
	turn assistant.AssistantTurn,
	primary SkillSelection,
	observation map[string]any,
	finalTextSink func(ports.ModelTextDelta) error,
) (ModelResponse, bool, error) {
	model := r.Model
	if model == nil {
		return ModelResponse{}, false, fmt.Errorf("assistant model provider is not configured")
	}
	if r.PrePlanAccess != nil {
		if err := r.PrePlanAccess(ctx, turn, primary); err != nil {
			return ModelResponse{}, false, err
		}
	}
	request := frozenPolicyModelRequest(turn, primary, ModelRequest{
		TurnID:               turn.TurnID,
		TraceID:              turn.TraceID,
		SkillID:              primary.SkillID,
		Stage:                string(ports.ModelStageFinal),
		Prompt:               "多个子任务已分别完成。请合成一个连贯回答：按子任务归类要点，明确哪一部分没有拿到结果，不要重复同一条结论。",
		Observation:          observation,
		UserQuestion:         turn.Input.Text,
		ContextTurns:         turn.ContextTurns,
		ContextSummary:       turn.ContextSummary,
		PageContext:          turn.PageContext,
		IntersectionEvidence: turn.IntersectionEvidence,
		ContextAssembly:      primary.ContextAssembly,
		SessionPreferences:   turn.SessionPreferences,
		LongTermPreferences:  turn.LongTermPreferences,
	})
	response, streamed, err := completeFinalModelResponse(ctx, model, request, finalTextSink)
	if err != nil {
		return ModelResponse{}, false, err
	}
	if !finalAnswerUsable(response) && !streamed {
		return ModelResponse{}, false, fmt.Errorf("merged final answer is not displayable")
	}
	return response, streamed, nil
}

// askUserPromptText 把反问渲染成用户可读文本：问题本身加上可选项，不再另起一次模型调用。
func askUserPromptText(ask react.AskUser) string {
	prompt := strings.TrimSpace(ask.Prompt)
	if len(ask.Suggestions) == 0 {
		return prompt
	}
	var b strings.Builder
	b.WriteString(prompt)
	b.WriteString("\n")
	for _, suggestion := range ask.Suggestions {
		b.WriteString("\n- ")
		b.WriteString(suggestion)
	}
	return b.String()
}

func frozenPolicyModelRequest(
	turn assistant.AssistantTurn,
	skill SkillSelection,
	request ModelRequest,
) ModelRequest {
	frozen := turn.FrozenPolicySelection
	request.PolicyID = frozen.PolicyID
	request.PolicyReleaseDigest = frozen.ReleaseDigest
	request.PolicyCohort = frozen.Cohort
	request.PolicyRolloutRevision = frozen.RolloutRevision
	request.PolicyRuleID = frozen.RuleID
	request.PolicyTemplateID = frozen.Template.TemplateID
	request.SearchIntensity = skill.SearchIntensity
	request.ProblemClass = skill.ProblemClass
	request.FeedbackContext = turn.FeedbackContextSnapshot
	policyPrompt := strings.TrimSpace(skill.PromptPolicy)
	stagePrompt := strings.TrimSpace(request.Prompt)
	switch {
	case policyPrompt == "":
		request.Prompt = stagePrompt
	case stagePrompt == "":
		request.Prompt = policyPrompt
	default:
		request.Prompt = policyPrompt + "\n\nStage instruction:\n" + stagePrompt
	}
	return request
}

func completeFinalModelResponse(
	ctx context.Context,
	model ModelProvider,
	request ModelRequest,
	finalTextSink func(ports.ModelTextDelta) error,
) (ModelResponse, bool, error) {
	maxRunes := 0
	if request.ContextAssembly != nil {
		maxRunes = request.ContextAssembly.MaxAnswerRunes
	}
	streamingModel, ok := model.(StreamingModelProvider)
	if !ok {
		response, err := model.Complete(ctx, request)
		if usageErr := consumeExecutionModelResponse(ctx, response); usageErr != nil {
			return ModelResponse{}, false, usageErr
		}
		response = boundModelResponseText(response, maxRunes)
		return response, false, err
	}
	streamed := false
	streamedRunes := 0
	response, err := streamingModel.Stream(
		ctx,
		request,
		func(delta ports.ModelTextDelta) error {
			if delta.Text == "" {
				return nil
			}
			if maxRunes > 0 {
				remaining := maxRunes - streamedRunes
				if remaining <= 0 {
					return nil
				}
				runes := []rune(delta.Text)
				if len(runes) > remaining {
					runes = runes[:remaining]
				}
				delta.Text = string(runes)
				streamedRunes += len(runes)
			}
			streamed = true
			if finalTextSink == nil {
				return nil
			}
			return finalTextSink(delta)
		},
	)
	if usageErr := consumeExecutionModelResponse(ctx, response); usageErr != nil {
		return ModelResponse{}, false, usageErr
	}
	// Stream owns the only pre-emission retry boundary. Switching protocols here
	// would restart the tier chain and create a second final-answer path.
	response = boundModelResponseText(response, maxRunes)
	return response, streamed, err
}

func boundModelResponseText(response ModelResponse, maxRunes int) ModelResponse {
	if maxRunes <= 0 {
		return response
	}
	runes := []rune(response.Text)
	if len(runes) <= maxRunes {
		return response
	}
	response.Text = string(runes[:maxRunes])
	if response.StructuredDelta != nil {
		if _, ok := response.StructuredDelta["userMarkdown"]; ok {
			response.StructuredDelta["userMarkdown"] = response.Text
		}
	}
	return response
}

func finalAnswerUsable(resp ModelResponse) bool {
	text := strings.TrimSpace(resp.Text)
	if text == "" || text == "{}" || strings.EqualFold(text, "null") {
		return false
	}
	if containsInternalAnswerWording(text) {
		return false
	}
	if strings.HasPrefix(text, "{") && strings.HasSuffix(text, "}") {
		if md := strings.TrimSpace(fmtAny(resp.StructuredDelta["userMarkdown"])); md == "" {
			return false
		}
	}
	return true
}

func containsInternalAnswerWording(text string) bool {
	normalized := strings.ToLower(strings.TrimSpace(text))
	if normalized == "" {
		return false
	}
	internalMarkers := []string{
		"工具观察",
		"工具结果",
		"工具调用",
		"根据工具",
		"可靠标记",
		"协议字段",
		"reliable",
	}
	for _, marker := range internalMarkers {
		if strings.Contains(normalized, strings.ToLower(marker)) {
			return true
		}
	}
	return false
}

func collectModelInteraction(resp ModelResponse) []map[string]any {
	if resp.ClientModelInteraction == nil {
		return nil
	}
	return []map[string]any{resp.ClientModelInteraction}
}

func buildFinalObservationPayload(
	finalObservation map[string]any,
	steps []ReactStepResult,
) map[string]any {
	payload := map[string]any{}
	for key, value := range finalObservation {
		payload[key] = value
	}
	if len(steps) == 0 {
		return payload
	}
	lastStep := steps[len(steps)-1]
	if lastStep.DecisionRejection != nil {
		payload["decisionRejection"] = toolDecisionRejectionObservation(
			lastStep.DecisionRejection,
		)
		return payload
	}
	payload["retrievalProcessing"] = buildRetrievalProcessingForStep(lastStep)
	return payload
}
