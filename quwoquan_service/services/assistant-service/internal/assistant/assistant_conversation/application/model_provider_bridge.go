package application

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_conversation"
	runerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_run"
)

// ProviderBackedModelProvider 把既有 AgentLoop 模型接口收敛到强类型外部端口。
// 动态 structured delta 只在 application 的模型协议投影中存在，不会越过 adapter。
type ProviderBackedModelProvider struct {
	Backend ModelCompletionProvider
}

func (p ProviderBackedModelProvider) Complete(
	ctx context.Context,
	req ModelRequest,
) (ModelResponse, error) {
	if p.Backend == nil {
		return ModelResponse{}, ProviderFailure{
			Capability: "model",
			Reason:     ProviderFailureUnavailable,
		}
	}
	wire, err := modelCompletionRequestFrom(req, false)
	if err != nil {
		return ModelResponse{}, err
	}
	result, err := p.Backend.Complete(ctx, wire)
	if err != nil {
		return ModelResponse{}, modelProviderRuntimeError(err)
	}
	return modelResponseFromCompletion(req, result)
}

func (p ProviderBackedModelProvider) Stream(
	ctx context.Context,
	req ModelRequest,
	emit func(ModelTextDelta) error,
) (ModelResponse, error) {
	if p.Backend == nil {
		return ModelResponse{}, ProviderFailure{
			Capability: "model",
			Reason:     ProviderFailureUnavailable,
		}
	}
	wire, err := modelCompletionRequestFrom(req, true)
	if err != nil {
		return ModelResponse{}, err
	}
	result, err := p.Backend.Stream(ctx, wire, emit)
	if err != nil {
		return ModelResponse{}, modelProviderRuntimeError(err)
	}
	return modelResponseFromCompletion(req, result)
}

func modelCompletionRequestFrom(
	req ModelRequest,
	stream bool,
) (ModelCompletionRequest, error) {
	stage := ModelStage(strings.TrimSpace(req.Stage))
	if stage == "" {
		return ModelCompletionRequest{}, fmt.Errorf("model stage is required")
	}
	prompt := req.Prompt
	contextPrompt := FormatModelContextForPrompt(req.ContextTurns)
	pageContextPrompt := FormatPageContextForPrompt(req.PageContext)
	intersectionEvidencePrompt := FormatAuthorizedIntersectionEvidenceForPrompt(
		req.IntersectionEvidence,
	)
	preferencePrompt := FormatModelPreferencesForPrompt(
		req.SessionPreferenceFacts,
		req.LongTermPreferenceFacts,
	)
	feedbackPrompt := FormatFeedbackContextForPrompt(req.FeedbackContext)
	if stage == ModelStageFinal || stage == ModelStageEvidenceProcessing {
		raw, err := json.Marshal(req.Observation)
		if err != nil {
			return ModelCompletionRequest{}, fmt.Errorf("encode model observation: %w", err)
		}
		label := "工具观察"
		if stage == ModelStageEvidenceProcessing {
			label = "工具观察JSON"
		}
		prompt = fmt.Sprintf(
			"%s%s%s%s%s%s\n用户问题：%s\n%s：%s",
			req.Prompt,
			contextPrompt,
			pageContextPrompt,
			intersectionEvidencePrompt,
			preferencePrompt,
			feedbackPrompt,
			req.UserQuestion,
			label,
			string(raw),
		)
	} else {
		prompt = fmt.Sprintf(
			"%s%s%s%s%s%s\n用户问题：%s",
			req.Prompt,
			contextPrompt,
			pageContextPrompt,
			intersectionEvidencePrompt,
			preferencePrompt,
			feedbackPrompt,
			req.UserQuestion,
		)
	}

	system := "你是趣我圈小趣私人助理云侧引擎。严格遵守输出格式约定。"
	structured := false
	switch stage {
	case ModelStageSkillSelection:
		system = "你是趣我圈小趣私人助理的技能选择器。只能从用户提供的 manifest 中选择一个 skillId，输出 JSON：{\"skillId\":\"...\",\"reason\":\"...\"}。reason 仅供调试追溯，不要使用固定模板套话。"
		structured = true
	case ModelStageReasoning:
		system = "输出唯一 JSON：nextAction（call_tool）、toolName（web_search 或 app_search）、toolInput（含 query；可含 searchQueries:[{dimension,query}]、location、locationSearchName、symbol 或 symbols）、stageNarrative（唯一面向用户叙事字段，180-320字）。stageNarrative 必须使用第二人称“你/你的”，禁止写“用户/该用户/客户/提问者”；先用 2-4 句深入说明你真正要解决的问题，覆盖地点、时间、人数/对象、出行或决策约束、已知上下文和缺失信息；检索设计只占最后 1 句，简要说明会核验哪些事实，不要让检索词占据主体。toolInput.query 是主检索短词；如有天气、交通、景点、人流、股票、新闻等多个维度，在 toolInput.searchQueries 中每个维度一行列出结构化检索词。如问题涉及天气、出行地点或本地实时信息，toolInput.location 填你识别出的地点，toolInput.locationSearchName 填适合地理检索的英文/拉丁写法（例如杭州用 Hangzhou、深圳用 Shenzhen）；如问题涉及证券/股票，toolInput.symbol 或 symbols 填你能识别的交易代码。拼音/缩写须自行理解为可用检索词。禁止输出 JSON 外文字。 检索时优先规划权威来源、官方文档、产品页、标准组织或一手机构资料；若用户问题本身包含‘对比’、‘怎么选’、‘差异’、‘竞品’等意图，应主动把 searchQueries 拆成多家官方来源或多个权威机构的对比查询，而不是只盯单一站点。"
		structured = true
	case ModelStageEvidenceProcessing:
		system = "输出唯一 JSON：{\"retrievalProcessing\":{\"processingSummary\":\"...\",\"selectedKeyPoints\":[\"...\"],\"acceptedReferences\":[{\"title\":\"\",\"url\":\"\",\"source\":\"\",\"snippet\":\"\"}]},\"evidenceSufficient\":true}。processingSummary 为面向用户的证据处理叙事，必须使用第二人称“你/你的”，禁止写“用户/该用户/客户/提问者”；先说明证据覆盖了你问题里的哪些维度，再说明未覆盖或需要自行复核的部分。acceptedReferences 只能从输入 references 中挑选；若输入有 2-4 条相关高置信引用，应保留 2-4 条不同来源或不同用途的引用，不要无故压缩成 1 条；若工具结果 reliable=false 或 references 为空，不得声称已接纳可靠资料，acceptedReferences 必须为空。面向用户文字不要出现 reliable=true/false、JSON 字段名、工具调用、工具结果、工具观察等协议或调试表述。"
		structured = true
	case ModelStageFinal:
		system = "直接输出面向用户的完整 Markdown 回答，不要包裹 JSON 或代码块。回答必须非空，必须使用第二人称“你/你的”，禁止写“用户/该用户/客户/提问者”。开头直接给结论或建议，不要用内部证据来源作为开场，不要出现“工具、观察、检索、证据标记、协议、JSON、reliable”等内部过程或调试表述；也不要复述同一会话前文里的生硬模板口吻。若输入证据可靠，请把事实自然融入回答并给可执行建议；若输入证据不足，才说明不确定性与下一步核验办法。Markdown 结构必须清晰：优先使用 2-4 个短小段落、项目符号或小标题；每个要点单独成行，避免把天气、原因、行动建议挤成一个长段。遵守法律法规；勿编造实时事实；不确定处提示用户自行核实；仅当用户问题确实涉及金融、股票、证券、基金、买卖或投资决策时才加注非投资建议声明；天气、出行、行程规划等非金融问题禁止出现投资建议声明。若 observation.retrievalProcessing.acceptedReferences 非空，在正文结尾追加“## 知识来源”小节，列出 1-4 条来源；只能使用输入里的 title/url/source，不得编造链接或来源。若用户问题涉及选型、价格、计费、购买或跨平台对比，请优先引用 acceptedReferences 中的权威/官方来源来支撑关键结论；当 acceptedReferences 为空时，不得编造来源或把未经证据支撑的细节写成确定事实。"
	default:
		return ModelCompletionRequest{}, fmt.Errorf("unsupported model stage %q", stage)
	}
	if stream && stage != ModelStageFinal {
		stream = false
	}
	return ModelCompletionRequest{
		Stage:            stage,
		StructuredOutput: structured,
		Stream:           stream,
		Messages: []ModelMessage{
			{Role: "system", Content: system},
			{Role: "user", Content: prompt},
		},
	}, nil
}

func modelResponseFromCompletion(
	req ModelRequest,
	result ModelCompletionResult,
) (ModelResponse, error) {
	text := strings.TrimSpace(result.Content)
	delta := map[string]any(nil)
	switch ModelStage(req.Stage) {
	case ModelStageSkillSelection, ModelStageReasoning, ModelStageEvidenceProcessing:
		delta = map[string]any{}
		if err := json.Unmarshal([]byte(text), &delta); err != nil {
			return ModelResponse{}, ProviderFailure{
				Capability: "model",
				Reason:     ProviderFailureInvalidResponse,
			}
		}
		if ModelStage(req.Stage) == ModelStageReasoning {
			delta["toolName"] = normalizeModelToolName(fmt.Sprint(delta["toolName"]))
		}
	case ModelStageFinal:
		if len(modelAcceptedReferences(req.Observation)) == 0 {
			text = stripUnbackedKnowledgeSources(text)
		} else {
			text = appendAcceptedKnowledgeSources(
				text,
				modelAcceptedReferences(req.Observation),
			)
		}
		delta = map[string]any{"userMarkdown": text}
	}
	return ModelResponse{
		Text:            text,
		StructuredDelta: delta,
		Usage: map[string]any{
			"latencyMs":        result.Usage.Latency.Milliseconds(),
			"promptTokens":     result.Usage.PromptTokens,
			"completionTokens": result.Usage.CompletionTokens,
			"totalTokens":      result.Usage.TotalTokens,
		},
		FinishReason: result.FinishReason,
		ClientModelInteraction: map[string]any{
			"stage":                   req.Stage,
			"skillId":                 req.SkillID,
			"turnId":                  req.TurnID,
			"traceId":                 req.TraceID,
			"contextTurnCount":        len(req.ContextTurns),
			"requestCharacterCount":   modelRequestCharacterCount(req),
			"responseCharacterCount":  len([]rune(text)),
			"finishReason":            result.FinishReason,
			"contentRedactionApplied": true,
		},
	}, nil
}

func modelRequestCharacterCount(req ModelRequest) int {
	request, err := modelCompletionRequestFrom(req, false)
	if err == nil && len(request.Messages) > 1 {
		return len([]rune(request.Messages[1].Content))
	}
	return len([]rune(req.Prompt + req.UserQuestion))
}

func modelAcceptedReferences(observation map[string]any) []ExternalReference {
	if observation == nil {
		return nil
	}
	processing, ok := observation["retrievalProcessing"].(map[string]any)
	if !ok {
		return nil
	}
	var entries []map[string]any
	switch raw := processing["acceptedReferences"].(type) {
	case []map[string]any:
		entries = raw
	case []any:
		entries = make([]map[string]any, 0, len(raw))
		for _, item := range raw {
			if entry, ok := item.(map[string]any); ok {
				entries = append(entries, entry)
			}
		}
	default:
		return nil
	}
	refs := make([]ExternalReference, 0, len(entries))
	for _, entry := range entries {
		rawDestination, ok := entry["destination"].(map[string]any)
		if !ok {
			continue
		}
		destination, ok := citationDestinationFromMap(rawDestination)
		if !ok ||
			destination.Kind != string(assistantgenerated.CitationDestinationKindExternal) {
			continue
		}
		ref := ExternalReference{
			Title:   strings.TrimSpace(fmt.Sprint(entry["title"])),
			URL:     destination.URL,
			Source:  strings.TrimSpace(fmt.Sprint(entry["source"])),
			Snippet: strings.TrimSpace(fmt.Sprint(entry["snippet"])),
		}
		if ref.Title != "" || ref.Source != "" {
			refs = append(refs, ref)
		}
	}
	return refs
}

func appendAcceptedKnowledgeSources(
	markdown string,
	refs []ExternalReference,
) string {
	trimmed := strings.TrimSpace(markdown)
	if trimmed == "" || len(refs) == 0 || strings.Contains(trimmed, "知识来源") {
		return trimmed
	}
	lines := []string{trimmed, "", "## 知识来源"}
	for _, ref := range refs {
		label := ref.Title
		if label == "" {
			label = ref.Source
		}
		if label == "" {
			continue
		}
		if ref.URL != "" && ref.URL != "<nil>" {
			lines = append(lines, fmt.Sprintf("- [%s](%s)", label, ref.URL))
			continue
		}
		lines = append(lines, "- "+label)
	}
	return strings.Join(lines, "\n")
}

func stripUnbackedKnowledgeSources(markdown string) string {
	trimmed := strings.TrimSpace(markdown)
	if index := strings.Index(trimmed, "\n## 知识来源"); index >= 0 {
		return strings.TrimSpace(trimmed[:index])
	}
	if strings.HasPrefix(trimmed, "## 知识来源") {
		return ""
	}
	return trimmed
}

func normalizeModelToolName(raw string) string {
	toolName := strings.TrimSpace(raw)
	switch toolName {
	case "web_search", "app_search", "":
		return toolName
	default:
		return toolName
	}
}

func modelProviderRuntimeError(err error) error {
	var providerFailure ProviderFailure
	if errors.As(err, &providerFailure) && providerFailure.Capability == "model" {
		return runerrors.AppErrorFromModelProviderUnavailable(
			"model provider " + string(providerFailure.Reason),
		)
	}
	return err
}
