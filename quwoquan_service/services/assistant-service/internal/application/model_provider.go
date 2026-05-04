package application

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	skillpkg "quwoquan_service/services/assistant-service/internal/application/skill"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type ModelRequest struct {
	TurnID       string
	TraceID      string
	SkillID      string
	Prompt       string
	Stage        string
	Observation  map[string]any
	UserQuestion string
	ContextTurns []assistant.AssistantConversationContextTurn
	SkillCatalog []skillpkg.Manifest
}

type ModelResponse struct {
	Text                   string
	StructuredDelta        map[string]any
	Usage                  map[string]any
	FinishReason           string
	ClientModelInteraction map[string]any
}

type ModelProvider interface {
	Complete(ctx context.Context, req ModelRequest) (ModelResponse, error)
}

type DeterministicModelProvider struct{}

func deterministicClientTrace(req ModelRequest, responseText string, delta map[string]any) map[string]any {
	prompt := fmt.Sprintf("%s%s\n用户问题：%s", req.Prompt, FormatModelContextForPrompt(req.ContextTurns), req.UserQuestion)
	return map[string]any{
		"stage":             req.Stage,
		"skillId":           req.SkillID,
		"turnId":            req.TurnID,
		"traceId":           req.TraceID,
		"requestUserPrompt": prompt,
		"responseText":      responseText,
		"structuredDelta":   delta,
		"usage":             map[string]any{"deterministic": true},
		"finishReason":      "stop",
	}
}

func observationToolSummary(obs map[string]any) string {
	if obs == nil {
		return ""
	}
	if res, ok := obs["result"].(map[string]any); ok {
		s := strings.TrimSpace(fmt.Sprint(res["summary"]))
		if s != "" && s != "<nil>" {
			return s
		}
	}
	s := strings.TrimSpace(fmt.Sprint(obs["summary"]))
	if s == "<nil>" {
		return ""
	}
	return s
}

func FormatModelContextForPrompt(turns []assistant.AssistantConversationContextTurn) string {
	if len(turns) == 0 {
		return ""
	}
	lines := []string{"\n同一会话前文（按时间从旧到新，仅用于理解省略表达、延续地点/约束和复用事实；不要复制前文回答的开头、模板口吻或内部过程表述）："}
	for _, turn := range turns {
		role := strings.TrimSpace(turn.Role)
		if role == "" {
			role = "user"
		}
		text := strings.TrimSpace(turn.Text)
		if text == "" {
			continue
		}
		lines = append(lines, fmt.Sprintf("- %s: %s", role, truncateDeterministicRunes(text, 240)))
	}
	if len(lines) == 1 {
		return ""
	}
	return strings.Join(lines, "\n")
}

func truncateDeterministicRunes(s string, maxRunes int) string {
	r := []rune(s)
	if len(r) <= maxRunes {
		return s
	}
	return string(r[:maxRunes]) + "…"
}

func (DeterministicModelProvider) Complete(_ context.Context, req ModelRequest) (ModelResponse, error) {
	question := strings.TrimSpace(req.UserQuestion)
	if question == "" {
		question = "你的问题"
	}
	switch strings.TrimSpace(req.Stage) {
	case "skill_selection":
		manifest := skillpkg.NewRouter(req.SkillCatalog).Route(assistant.AssistantTurn{
			Input: assistant.AssistantTurnInput{Text: question},
		})
		delta := map[string]any{
			"skillId": manifest.SkillID,
			"reason":  "manifest_semantic_fallback",
		}
		text := fmt.Sprintf(`{"skillId":%q,"reason":"manifest_semantic_fallback"}`, manifest.SkillID)
		return ModelResponse{
			Text:                   text,
			StructuredDelta:        delta,
			Usage:                  map[string]any{"inputTokens": 40, "outputTokens": 12},
			FinishReason:           "stop",
			ClientModelInteraction: deterministicClientTrace(req, text, delta),
		}, nil
	case "reasoning":
		toolName := "web_search"
		switch req.SkillID {
		case SkillDailyAssistant:
			toolName = "app_search"
		case SkillNewsBriefing, SkillStockSentinel, SkillTravelJourneyManager:
			toolName = "web_search"
		case "calendar_task":
			toolName = "app_search"
		case "travel_transport":
			toolName = "app_search"
		case "work_productivity", "local_life":
			toolName = "app_search"
		case "emotion_companion", "social_companion_chat", "relationship_matchmaking":
			toolName = "web_search"
		}
		delta := map[string]any{
			"nextAction": "call_tool",
			"toolName":   toolName,
			"toolInput": map[string]any{
				"query": question,
			},
			"understandingSnapshot": map[string]any{
				"userFacingSummary":        fmt.Sprintf("我理解你想了解「%s」，会先对齐关键信息再走检索。", question),
				"retrievalDesignNarrative": fmt.Sprintf("检索上将围绕「%s」查找可公开核验的线索。", question),
			},
		}
		raw, _ := json.Marshal(delta)
		text := string(raw)
		return ModelResponse{
			Text:                   text,
			StructuredDelta:        delta,
			Usage:                  map[string]any{"inputTokens": 32, "outputTokens": 24},
			FinishReason:           "tool_use",
			ClientModelInteraction: deterministicClientTrace(req, text, delta),
		}, nil
	case "evidence_processing":
		summary := observationToolSummary(req.Observation)
		if summary == "" {
			summary = "工具返回了结构化摘要。"
		}
		delta := map[string]any{
			"retrievalProcessing": map[string]any{
				"processingSummary":  fmt.Sprintf("已从工具结果梳理：%s", truncateDeterministicRunes(summary, 160)),
				"selectedKeyPoints":  []string{"要点已对齐工具摘要"},
				"acceptedReferences": []any{},
			},
			"evidenceSufficient": true,
		}
		raw, _ := json.Marshal(delta)
		text := string(raw)
		return ModelResponse{
			Text:                   text,
			StructuredDelta:        delta,
			Usage:                  map[string]any{"inputTokens": 36, "outputTokens": 28},
			FinishReason:           "stop",
			ClientModelInteraction: deterministicClientTrace(req, text, delta),
		}, nil
	case "final":
		summary := observationToolSummary(req.Observation)
		if summary == "" {
			summary = strings.TrimSpace(fmt.Sprint(req.Observation["summary"]))
		}
		if summary == "" || summary == "<nil>" {
			summary = "云端工具已返回可用上下文"
		}
		var markdown string
		if IsP0ProactiveSkill(req.SkillID) {
			markdown = p0FinalAnswer(req.SkillID, question, summary)
		} else if text := domainSkillFinalAnswer(req.SkillID, question, summary); text != "" {
			markdown = text
		} else {
			markdown = fmt.Sprintf("已基于云端 ReAct 流程完成回答：%s。针对“%s”，建议先按优先级整理事项，再继续补充细节。", summary, question)
		}
		delta := map[string]any{"userMarkdown": markdown}
		return ModelResponse{
			Text:                   markdown,
			StructuredDelta:        delta,
			Usage:                  map[string]any{"inputTokens": 48, "outputTokens": 44},
			FinishReason:           "stop",
			ClientModelInteraction: deterministicClientTrace(req, markdown, delta),
		}, nil
	default:
		text := fmt.Sprintf("云端模型已处理：%s", question)
		delta := map[string]any{"note": text}
		return ModelResponse{
			Text:                   text,
			StructuredDelta:        delta,
			FinishReason:           "stop",
			ClientModelInteraction: deterministicClientTrace(req, text, delta),
		}, nil
	}
}

func domainSkillFinalAnswer(skillID, question, summary string) string {
	switch skillID {
	case "finance_consumer":
		return fmt.Sprintf("理财与投资助手已生成重大消息摘要：%s。针对“%s”，请优先核对公告原文、行业政策与盘中波动，本内容仅作信息摘要，非投资建议。", summary, question)
	case "weather":
		return fmt.Sprintf("天气助手已生成天气建议：%s。针对“%s”，请关注地点、日期、降雨或温度变化，建议携带雨具并预留出行缓冲时间。", summary, question)
	case "travel_transport":
		return fmt.Sprintf("交通出行助手已生成路线与缓冲建议：%s。针对“%s”，建议先确认公共交通衔接，再为路况和换乘预留缓冲时间。", summary, question)
	case "travel_planning":
		return fmt.Sprintf("出行管家已生成行程提醒：%s。针对“%s”，建议同时关注景点、酒店区域、天气和拥堵，必要时调整游览顺序。", summary, question)
	case "local_life":
		return fmt.Sprintf("本地生活助手已生成附近餐厅与本地好去处建议：%s。针对“%s”，建议按距离、排队、口味和营业时间筛选。", summary, question)
	case "calendar_task":
		return fmt.Sprintf("日程待办助手已生成会议与提醒方案：%s。针对“%s”，建议确认时间、材料清单和提醒方式后再执行。", summary, question)
	case "knowledge_general":
		return fmt.Sprintf("通用知识助手已整理原理与局限：%s。针对“%s”，我会先解释核心概念，再说明适用场景和局限。", summary, question)
	case "health_wellness":
		return fmt.Sprintf("健康生活助手已生成睡眠、饮食和运动建议：%s。针对“%s”，建议循序渐进；如有持续不适，请咨询专业医生。", summary, question)
	case "education_learning":
		return fmt.Sprintf("学习助手已生成两周计划：%s。针对“%s”，建议拆分每日任务、复盘节点和阶段测验。", summary, question)
	case "work_productivity":
		return fmt.Sprintf("工作效率助手已生成任务与里程碑拆解：%s。针对“%s”，建议明确负责人、风险清单和验收节点。", summary, question)
	case "shopping_decision":
		return fmt.Sprintf("购物决策助手已生成对比与性价比建议：%s。针对“%s”，建议按参数、体验、预算和售后权重排序。", summary, question)
	case "policy_public_service":
		return fmt.Sprintf("政策办事助手已生成材料和流程清单：%s。针对“%s”，建议以当地政务最新要求为准，并提前核对办理条件。", summary, question)
	case "emotion_companion":
		return fmt.Sprintf("情感陪伴助手已接住你的压力和焦虑：%s。针对“%s”，我们先拆分触发点、可控事项和今天能做的小行动。", summary, question)
	case "social_companion_chat":
		return fmt.Sprintf("轻松闲聊助手已准备好聊天：%s。针对“%s”，我们可以从今天的小事、兴趣话题或一个轻松问题开始。", summary, question)
	case "relationship_matchmaking":
		return fmt.Sprintf("关系沟通助手已生成关系与沟通建议：%s。针对“%s”，建议用事实、感受、需要和请求四步表达，减少对抗。", summary, question)
	case "family_parenting":
		return fmt.Sprintf("家庭育儿助手已生成亲子和青春期沟通建议：%s。针对“%s”，建议先稳定情绪、明确边界，再共同约定下一步。", summary, question)
	case "fortune_astrology":
		return fmt.Sprintf("星座运势助手已生成事业与感情的娱乐解读：%s。针对“%s”，内容仅供轻松娱乐参考。", summary, question)
	case "divination_fortune":
		return fmt.Sprintf("今日运势助手已生成财运与事业的趣味建议：%s。针对“%s”，请把运势内容作为娱乐参考。", summary, question)
	case "astrology_constellation":
		return fmt.Sprintf("占星星盘助手已解释上升星座与太阳星座：%s。针对“%s”，可把太阳星座看作核心自我，上升星座看作外在呈现。", summary, question)
	case "huawei_cloud_qa":
		return fmt.Sprintf("华为云问答助手已生成昇腾、容器和对象存储选型建议：%s。针对“%s”，建议按算力、编排、存储和运维成本拆分评估。", summary, question)
	case "fallback_general_search":
		return fmt.Sprintf("通用搜索助手已生成 AI 产品搜索摘要：%s。针对“%s”，建议按模型能力、应用场景和商业化进展分组跟踪。", summary, question)
	default:
		return ""
	}
}

func p0FinalAnswer(skillID, question, summary string) string {
	switch skillID {
	case SkillDailyAssistant:
		return fmt.Sprintf("每日助手已生成计划：%s。为什么提醒你：你订阅了每日助手。建议先处理会议准备、学习计划和作息提醒。", summary)
	case SkillNewsBriefing:
		return fmt.Sprintf("新闻简报已生成：%s。为什么提醒你：你订阅了相关话题。可以继续追问任一来源的影响。", summary)
	case SkillStockSentinel:
		return fmt.Sprintf("股票哨兵已生成信息摘要：%s。为什么提醒你：你订阅了关注标的消息面。本内容仅作信息摘要，非投资建议。", summary)
	case SkillTravelJourneyManager:
		return fmt.Sprintf("出行管家已生成行程提醒：%s。为什么提醒你：你订阅了行程天气、路况和拥堵变化。建议预留缓冲时间。", summary)
	default:
		return fmt.Sprintf("已完成主动 Skill 摘要：%s。针对“%s”，你可以继续追问细节。", summary, question)
	}
}
