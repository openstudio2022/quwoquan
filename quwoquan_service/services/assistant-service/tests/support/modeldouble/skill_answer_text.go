package modeldouble

import (
	"fmt"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
)

// domainSkillFinalAnswer 是测试树内的领域技能话术表，只用于让断言可以稳定匹配某个
// skillId 走到了 final stage。生产回答由模型生成，不得反向依赖本表。
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
		return fmt.Sprintf("云服务问答助手已整理云服务选型线索：%s。针对“%s”，建议按算力、编排、存储、计费和运维成本拆分评估，并结合权威来源做对比。", summary, question)
	case "fallback_general_search":
		return fmt.Sprintf("通用搜索助手已生成 AI 产品搜索摘要：%s。针对“%s”，建议按模型能力、应用场景和商业化进展分组跟踪。", summary, question)
	default:
		return ""
	}
}

func proactiveFinalAnswer(skillID, question, summary string) string {
	switch skillID {
	case orchestration.SkillDailyAssistant:
		return fmt.Sprintf("每日助手已生成计划：%s。为什么提醒你：你订阅了每日助手。建议先处理会议准备、学习计划和作息提醒。", summary)
	case orchestration.SkillNewsBriefing:
		return fmt.Sprintf("新闻简报已生成：%s。为什么提醒你：你订阅了相关话题。可以继续追问任一来源的影响。", summary)
	case orchestration.SkillStockSentinel:
		return fmt.Sprintf("股票哨兵已生成信息摘要：%s。为什么提醒你：你订阅了关注标的消息面。本内容仅作信息摘要，非投资建议。", summary)
	case orchestration.SkillTravelJourneyManager:
		return fmt.Sprintf("出行管家已生成行程提醒：%s。为什么提醒你：你订阅了行程天气、路况和拥堵变化。建议预留缓冲时间。", summary)
	default:
		return fmt.Sprintf("已完成主动 Skill 摘要：%s。针对“%s”，你可以继续追问细节。", summary, question)
	}
}
