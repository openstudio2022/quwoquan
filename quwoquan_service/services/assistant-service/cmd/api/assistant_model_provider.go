package main

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"sort"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/application"
)

type openAICompatibleModelProvider struct {
	baseURL string
	model   string
	apiKey  string
	client  *http.Client
}

func assistantClientModelTrace(
	req application.ModelRequest,
	userPrompt string,
	responseText string,
	finishReason string,
) map[string]any {
	return map[string]any{
		"stage":                   req.Stage,
		"skillId":                 req.SkillID,
		"turnId":                  req.TurnID,
		"traceId":                 req.TraceID,
		"contextTurnCount":        len(req.ContextTurns),
		"requestCharacterCount":   len([]rune(userPrompt)),
		"responseCharacterCount":  len([]rune(responseText)),
		"finishReason":            finishReason,
		"contentRedactionApplied": true,
	}
}

func (p openAICompatibleModelProvider) Complete(ctx context.Context, req application.ModelRequest) (application.ModelResponse, error) {
	startedAt := time.Now()
	prompt, body := buildOpenAICompatibleRequest(req, p.model, false)
	payload, _ := json.Marshal(body)
	log.Printf("assistant model request provider=openai_compatible stage=%s skillId=%s turnId=%s promptLen=%d", req.Stage, req.SkillID, req.TurnID, len([]rune(prompt)))
	emitAssistantModelRequestLog(req, p.model, body)
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, p.baseURL+"/chat/completions", bytes.NewReader(payload))
	if err != nil {
		return application.ModelResponse{}, err
	}
	httpReq.Header.Set("Authorization", "Bearer "+p.apiKey)
	httpReq.Header.Set("Content-Type", "application/json")
	resp, err := p.client.Do(httpReq)
	if err != nil {
		log.Printf("assistant model failed provider=openai_compatible stage=%s turnId=%s durationMs=%d err=%v", req.Stage, req.TurnID, time.Since(startedAt).Milliseconds(), err)
		return application.ModelResponse{}, err
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(io.LimitReader(resp.Body, 1024*1024))
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		emitAssistantModelErrorLog(req, p.model, resp.StatusCode, string(respBody))
		log.Printf("assistant model completed provider=openai_compatible stage=%s turnId=%s status=%d durationMs=%d", req.Stage, req.TurnID, resp.StatusCode, time.Since(startedAt).Milliseconds())
		return application.ModelResponse{}, fmt.Errorf(
			"model provider status=%d bodyLen=%d bodyDigest=%s",
			resp.StatusCode,
			len(respBody),
			assistantModelContentDigest(string(respBody)),
		)
	}
	modelDurationMs := time.Since(startedAt).Milliseconds()
	log.Printf("assistant model response provider=openai_compatible stage=%s turnId=%s status=%d bodyLen=%d durationMs=%d", req.Stage, req.TurnID, resp.StatusCode, len(respBody), modelDurationMs)
	var decoded struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
			FinishReason string `json:"finish_reason"`
		} `json:"choices"`
		Usage map[string]any `json:"usage"`
	}
	if err := json.Unmarshal(respBody, &decoded); err != nil {
		return application.ModelResponse{}, err
	}
	if len(decoded.Choices) == 0 {
		return application.ModelResponse{}, fmt.Errorf("model provider returned no choices")
	}
	rawText := strings.TrimSpace(decoded.Choices[0].Message.Content)
	outText := rawText
	delta := map[string]any(nil)
	switch req.Stage {
	case "skill_selection", "reasoning", "evidence_processing":
		delta = map[string]any{}
		var parsed map[string]any
		if err := json.Unmarshal([]byte(rawText), &parsed); err == nil {
			delta = parsed
		}
		if req.Stage == "reasoning" {
			delta["toolName"] = normalizeModelToolName(fmt.Sprint(delta["toolName"]))
		}
	case "final":
		outText = rawText
		delta = map[string]any{"userMarkdown": outText}
		acceptedRefs := acceptedReferencesFromObservation(req.Observation)
		if len(acceptedRefs) == 0 {
			outText = stripKnowledgeSourcesSection(outText)
			delta["userMarkdown"] = outText
		} else {
			outText = ensureKnowledgeSourcesSection(outText, acceptedRefs)
			delta["userMarkdown"] = outText
		}
	}
	if decoded.Usage == nil {
		decoded.Usage = map[string]any{}
	}
	decoded.Usage["provider"] = "openai_compatible"
	decoded.Usage["model"] = p.model
	decoded.Usage["latencyMs"] = modelDurationMs
	emitAssistantModelResponseLog(req, p.model, resp.StatusCode, rawText, decoded.Choices[0].FinishReason, decoded.Usage, delta)
	trace := assistantClientModelTrace(
		req,
		prompt,
		outText,
		decoded.Choices[0].FinishReason,
	)
	return application.ModelResponse{
		Text:                   outText,
		StructuredDelta:        delta,
		Usage:                  decoded.Usage,
		FinishReason:           decoded.Choices[0].FinishReason,
		ClientModelInteraction: trace,
	}, nil
}

func (p openAICompatibleModelProvider) Stream(
	ctx context.Context,
	req application.ModelRequest,
	emit func(application.ModelTextDelta) error,
) (application.ModelResponse, error) {
	if req.Stage != "final" {
		return p.Complete(ctx, req)
	}
	startedAt := time.Now()
	prompt, body := buildOpenAICompatibleRequest(req, p.model, true)
	payload, err := json.Marshal(body)
	if err != nil {
		return application.ModelResponse{}, err
	}
	log.Printf("assistant model stream request provider=openai_compatible stage=%s skillId=%s turnId=%s promptLen=%d", req.Stage, req.SkillID, req.TurnID, len([]rune(prompt)))
	emitAssistantModelRequestLog(req, p.model, body)
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, p.baseURL+"/chat/completions", bytes.NewReader(payload))
	if err != nil {
		return application.ModelResponse{}, err
	}
	httpReq.Header.Set("Authorization", "Bearer "+p.apiKey)
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "text/event-stream")
	resp, err := p.client.Do(httpReq)
	if err != nil {
		return application.ModelResponse{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		responseBody, _ := io.ReadAll(io.LimitReader(resp.Body, 1024*1024))
		emitAssistantModelErrorLog(req, p.model, resp.StatusCode, string(responseBody))
		return application.ModelResponse{}, fmt.Errorf("model provider status=%d", resp.StatusCode)
	}

	var answer strings.Builder
	usage := map[string]any{}
	finishReason := ""
	scanner := bufio.NewScanner(resp.Body)
	scanner.Buffer(make([]byte, 64*1024), 2*1024*1024)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if !strings.HasPrefix(line, "data:") {
			continue
		}
		data := strings.TrimSpace(strings.TrimPrefix(line, "data:"))
		if data == "" || data == "[DONE]" {
			continue
		}
		var chunk struct {
			Choices []struct {
				Delta struct {
					Content string `json:"content"`
				} `json:"delta"`
				FinishReason string `json:"finish_reason"`
			} `json:"choices"`
			Usage map[string]any `json:"usage"`
		}
		if err := json.Unmarshal([]byte(data), &chunk); err != nil {
			return application.ModelResponse{}, fmt.Errorf("decode model stream chunk: %w", err)
		}
		if chunk.Usage != nil {
			usage = chunk.Usage
		}
		for _, choice := range chunk.Choices {
			if choice.FinishReason != "" {
				finishReason = choice.FinishReason
			}
			if choice.Delta.Content == "" {
				continue
			}
			answer.WriteString(choice.Delta.Content)
			if emit != nil {
				if err := emit(application.ModelTextDelta{Text: choice.Delta.Content}); err != nil {
					return application.ModelResponse{}, err
				}
			}
		}
	}
	if err := scanner.Err(); err != nil {
		return application.ModelResponse{}, fmt.Errorf("read model stream: %w", err)
	}
	outText := strings.TrimSpace(answer.String())
	if outText == "" {
		return application.ModelResponse{}, fmt.Errorf("model provider returned empty stream")
	}
	acceptedRefs := acceptedReferencesFromObservation(req.Observation)
	if len(acceptedRefs) == 0 {
		outText = stripKnowledgeSourcesSection(outText)
	} else {
		outText = ensureKnowledgeSourcesSection(outText, acceptedRefs)
	}
	modelDurationMs := time.Since(startedAt).Milliseconds()
	usage["provider"] = "openai_compatible"
	usage["model"] = p.model
	usage["latencyMs"] = modelDurationMs
	delta := map[string]any{"userMarkdown": outText}
	emitAssistantModelResponseLog(req, p.model, resp.StatusCode, outText, finishReason, usage, delta)
	trace := assistantClientModelTrace(req, prompt, outText, finishReason)
	return application.ModelResponse{
		Text:                   outText,
		StructuredDelta:        delta,
		Usage:                  usage,
		FinishReason:           finishReason,
		ClientModelInteraction: trace,
	}, nil
}

func buildOpenAICompatibleRequest(
	req application.ModelRequest,
	model string,
	stream bool,
) (string, map[string]any) {
	prompt := req.Prompt
	contextPrompt := application.FormatModelContextForPrompt(req.ContextTurns)
	preferencePrompt := application.FormatModelPreferencesForPrompt(
		req.SessionPreferenceFacts,
		req.LongTermPreferenceFacts,
	)
	switch req.Stage {
	case "final":
		raw, _ := json.Marshal(req.Observation)
		prompt = fmt.Sprintf("%s%s%s\n用户问题：%s\n工具观察：%s", req.Prompt, contextPrompt, preferencePrompt, req.UserQuestion, string(raw))
	case "evidence_processing":
		raw, _ := json.Marshal(req.Observation)
		prompt = fmt.Sprintf("%s%s%s\n用户问题：%s\n工具观察JSON：%s", req.Prompt, contextPrompt, preferencePrompt, req.UserQuestion, string(raw))
	default:
		prompt = fmt.Sprintf("%s%s%s\n用户问题：%s", req.Prompt, contextPrompt, preferencePrompt, req.UserQuestion)
	}
	body := map[string]any{
		"model": model,
		"messages": []map[string]string{
			{"role": "system", "content": "你是趣我圈小趣私人助理云侧引擎。严格遵守输出格式约定。"},
			{"role": "user", "content": prompt},
		},
		"temperature": 0.2,
	}
	switch req.Stage {
	case "skill_selection":
		body["response_format"] = map[string]string{"type": "json_object"}
		body["messages"] = []map[string]string{
			{"role": "system", "content": "你是趣我圈小趣私人助理的技能选择器。只能从用户提供的 manifest 中选择一个 skillId，输出 JSON：{\"skillId\":\"...\",\"reason\":\"...\"}。reason 仅供调试追溯，不要使用固定模板套话。"},
			{"role": "user", "content": prompt},
		}
	case "reasoning":
		reasoningSystemPrompt := "输出唯一 JSON：nextAction（call_tool）、toolName（web_search 或 app_search）、toolInput（含 query；可含 searchQueries:[{dimension,query}]、location、locationSearchName、symbol 或 symbols）、stageNarrative（唯一面向用户叙事字段，180-320字）。stageNarrative 必须使用第二人称“你/你的”，禁止写“用户/该用户/客户/提问者”；先用 2-4 句深入说明你真正要解决的问题，覆盖地点、时间、人数/对象、出行或决策约束、已知上下文和缺失信息；检索设计只占最后 1 句，简要说明会核验哪些事实，不要让检索词占据主体。toolInput.query 是主检索短词；如有天气、交通、景点、人流、股票、新闻等多个维度，在 toolInput.searchQueries 中每个维度一行列出结构化检索词。如问题涉及天气、出行地点或本地实时信息，toolInput.location 填你识别出的地点，toolInput.locationSearchName 填适合地理检索的英文/拉丁写法（例如杭州用 Hangzhou、深圳用 Shenzhen）；如问题涉及证券/股票，toolInput.symbol 或 symbols 填你能识别的交易代码。拼音/缩写须自行理解为可用检索词。禁止输出 JSON 外文字。"
		reasoningSystemPrompt += " 检索时优先规划权威来源、官方文档、产品页、标准组织或一手机构资料；若用户问题本身包含‘对比’、‘怎么选’、‘差异’、‘竞品’等意图，应主动把 searchQueries 拆成多家官方来源或多个权威机构的对比查询，而不是只盯单一站点。"
		body["response_format"] = map[string]string{"type": "json_object"}
		body["messages"] = []map[string]string{
			{"role": "system", "content": reasoningSystemPrompt},
			{"role": "user", "content": prompt},
		}
	case "evidence_processing":
		body["response_format"] = map[string]string{"type": "json_object"}
		body["messages"] = []map[string]string{
			{"role": "system", "content": "输出唯一 JSON：{\"retrievalProcessing\":{\"processingSummary\":\"...\",\"selectedKeyPoints\":[\"...\"],\"acceptedReferences\":[{\"title\":\"\",\"url\":\"\",\"source\":\"\",\"snippet\":\"\"}]},\"evidenceSufficient\":true}。processingSummary 为面向用户的证据处理叙事，必须使用第二人称“你/你的”，禁止写“用户/该用户/客户/提问者”；先说明证据覆盖了你问题里的哪些维度，再说明未覆盖或需要自行复核的部分。acceptedReferences 只能从输入 references 中挑选；若输入有 2-4 条相关高置信引用，应保留 2-4 条不同来源或不同用途的引用，不要无故压缩成 1 条；若工具结果 reliable=false 或 references 为空，不得声称已接纳可靠资料，acceptedReferences 必须为空。面向用户文字不要出现 reliable=true/false、JSON 字段名、工具调用、工具结果、工具观察等协议或调试表述。"},
			{"role": "user", "content": prompt},
		}
	case "final":
		finalSystemPrompt := "直接输出面向用户的完整 Markdown 回答，不要包裹 JSON 或代码块。回答必须非空，必须使用第二人称“你/你的”，禁止写“用户/该用户/客户/提问者”。开头直接给结论或建议，不要用内部证据来源作为开场，不要出现“工具、观察、检索、证据标记、协议、JSON、reliable”等内部过程或调试表述；也不要复述同一会话前文里的生硬模板口吻。若输入证据可靠，请把事实自然融入回答并给可执行建议；若输入证据不足，才说明不确定性与下一步核验办法。Markdown 结构必须清晰：优先使用 2-4 个短小段落、项目符号或小标题；每个要点单独成行，避免把天气、原因、行动建议挤成一个长段。遵守法律法规；勿编造实时事实；不确定处提示用户自行核实；仅当用户问题确实涉及金融、股票、证券、基金、买卖或投资决策时才加注非投资建议声明；天气、出行、行程规划等非金融问题禁止出现投资建议声明。若 observation.retrievalProcessing.acceptedReferences 非空，在正文结尾追加“## 知识来源”小节，列出 1-4 条来源；只能使用输入里的 title/url/source，不得编造链接或来源。若用户问题涉及选型、价格、计费、购买或跨平台对比，请优先引用 acceptedReferences 中的权威/官方来源来支撑关键结论；当 acceptedReferences 为空时，不得编造来源或把未经证据支撑的细节写成确定事实。"
		body["messages"] = []map[string]string{
			{"role": "system", "content": finalSystemPrompt},
			{"role": "user", "content": prompt},
		}
	}
	if stream {
		body["stream"] = true
		body["stream_options"] = map[string]bool{"include_usage": true}
	}
	return prompt, body
}

// assistantModelDebugLogEnabled 显式开启后才允许 dump 模型请求/响应全文。
// 默认关闭：metadata 对 run 请求/响应声明 log_policy: metadata_only（SENSITIVE），
// 生产日志只保留长度/哈希/耗时等元信息（R-ASSIST-003）。
// composition root 强制只允许 alpha；beta/gamma/prod 即使误配也 fail-fast。
var assistantModelDebugLogEnabled bool

func validateAssistantModelDebugLogPolicy(appEnv string, enabled bool) error {
	if enabled && appEnv != "alpha" {
		return fmt.Errorf(
			"ASSISTANT_MODEL_DEBUG_LOG is forbidden when APP_ENV=%s",
			appEnv,
		)
	}
	return nil
}

func assistantModelContentDigest(text string) string {
	sum := sha256.Sum256([]byte(text))
	return hex.EncodeToString(sum[:4])
}

func emitAssistantModelRequestLog(req application.ModelRequest, model string, body map[string]any) {
	if !assistantModelDebugLogEnabled {
		payload, _ := json.Marshal(body)
		log.Printf(
			"[AssistantModel][cloud] REQUEST stage=%s skillId=%s turnId=%s model=%s bodyBytes=%d bodyDigest=%s",
			req.Stage, req.SkillID, req.TurnID, model, len(payload),
			assistantModelContentDigest(string(payload)),
		)
		return
	}
	header := fmt.Sprintf("[AssistantModel][cloud] REQUEST stage=%s skillId=%s turnId=%s model=%s", req.Stage, req.SkillID, req.TurnID, model)
	log.Print(header)
	emitAssistantModelSection("request", body)
}

func emitAssistantModelResponseLog(req application.ModelRequest, model string, statusCode int, text string, finishReason string, usage map[string]any, delta map[string]any) {
	if !assistantModelDebugLogEnabled {
		log.Printf(
			"[AssistantModel][cloud] RESPONSE stage=%s skillId=%s turnId=%s model=%s status=%d finishReason=%s contentLen=%d contentDigest=%s",
			req.Stage, req.SkillID, req.TurnID, model, statusCode, finishReason,
			len([]rune(text)), assistantModelContentDigest(text),
		)
		return
	}
	header := fmt.Sprintf("[AssistantModel][cloud] RESPONSE stage=%s skillId=%s turnId=%s model=%s status=%d finishReason=%s", req.Stage, req.SkillID, req.TurnID, model, statusCode, finishReason)
	log.Print(header)
	emitAssistantModelSection("response", map[string]any{
		"content":         text,
		"structuredDelta": delta,
		"usage":           usage,
	})
}

func emitAssistantModelErrorLog(req application.ModelRequest, model string, statusCode int, body string) {
	if !assistantModelDebugLogEnabled {
		log.Printf(
			"[AssistantModel][cloud] ERROR stage=%s skillId=%s turnId=%s model=%s status=%d bodyLen=%d bodyDigest=%s",
			req.Stage, req.SkillID, req.TurnID, model, statusCode,
			len(body), assistantModelContentDigest(body),
		)
		return
	}
	header := fmt.Sprintf("[AssistantModel][cloud] ERROR stage=%s skillId=%s turnId=%s model=%s status=%d", req.Stage, req.SkillID, req.TurnID, model, statusCode)
	log.Print(header)
	emitAssistantModelSection("error", body)
}

func emitAssistantModelSection(title string, value any) {
	log.Printf("[AssistantModel] %s:", title)
	switch typed := value.(type) {
	case map[string]any:
		emitAssistantModelMap("[AssistantModel]   ", typed)
	case string:
		emitAssistantModelMultiline("[AssistantModel]   ", typed)
	default:
		encoded, err := json.MarshalIndent(typed, "", "  ")
		if err != nil {
			log.Printf("[AssistantModel]   %v", typed)
			return
		}
		emitAssistantModelMultiline("[AssistantModel]   ", string(encoded))
	}
}

func emitAssistantModelMap(prefix string, values map[string]any) {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		value := values[key]
		switch typed := value.(type) {
		case string:
			log.Printf("%s%s:", prefix, key)
			emitAssistantModelMultiline(prefix+"  ", typed)
		case []map[string]string:
			log.Printf("%s%s:", prefix, key)
			for index, message := range typed {
				log.Printf("%s  [%d].role: %s", prefix, index, message["role"])
				log.Printf("%s  [%d].content:", prefix, index)
				emitAssistantModelMultiline(prefix+"    ", message["content"])
			}
		default:
			encoded, err := json.MarshalIndent(typed, "", "  ")
			if err != nil {
				log.Printf("%s%s: %v", prefix, key, typed)
				continue
			}
			log.Printf("%s%s:", prefix, key)
			emitAssistantModelMultiline(prefix+"  ", string(encoded))
		}
	}
}

func emitAssistantModelMultiline(prefix string, text string) {
	if strings.TrimSpace(text) == "" {
		log.Printf("%s<empty>", prefix)
		return
	}
	for _, line := range strings.Split(text, "\n") {
		log.Printf("%s%s", prefix, line)
	}
}

func normalizeModelToolName(raw string) string {
	toolName := strings.TrimSpace(raw)
	switch toolName {
	case "web_search", "app_search", "app_action", "scheduler", "deep_link", "intent_bridge":
		return toolName
	case "":
		return ""
	default:
		log.Printf("assistant model returned unsupported toolName=%s", toolName)
		return toolName
	}
}
