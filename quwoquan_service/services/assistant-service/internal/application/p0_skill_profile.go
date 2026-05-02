package application

import (
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

const (
	SkillDailyAssistant       = "daily_assistant"
	SkillNewsBriefing         = "news_briefing"
	SkillStockSentinel        = "stock_sentinel"
	SkillTravelJourneyManager = "travel_journey_manager"
)

type P0ProactiveSkillResult struct {
	SkillID     string
	Title       string
	Summary     string
	Prompt      string
	Why         string
	Evidence    []string
	NextActions []string
}

func BuildP0ProactiveSkillResult(subscription assistant.SkillSubscription, now time.Time) P0ProactiveSkillResult {
	skillID := strings.TrimSpace(subscription.SkillID)
	queries := compactStrings(subscription.SearchQueryPlan.Queries)
	rawText := strings.TrimSpace(subscription.SearchQueryPlan.RawText)
	if rawText == "" && len(queries) > 0 {
		rawText = strings.Join(queries, "，")
	}
	if rawText == "" {
		rawText = "执行主动订阅 " + skillID
	}
	why := fmt.Sprintf("为什么提醒你：你订阅了 %s，当前 cron 在 %s 命中。", displaySkillName(skillID), now.UTC().Format("15:04"))
	evidenceText := queryEvidence(queries)
	switch skillID {
	case SkillDailyAssistant:
		return P0ProactiveSkillResult{
			SkillID:  skillID,
			Title:    dailyAssistantTitle(rawText),
			Summary:  why + " 今日重点：会议准备、学习计划、作息提醒。建议先处理高优先级事项。",
			Prompt:   "每日助手主动简报：" + rawText,
			Why:      why,
			Evidence: []string{"fake_todo: 2 个高优先级事项", "fake_calendar: 1 场会议", "fake_study: 30 分钟学习计划"},
			NextActions: []string{
				"先处理高优先级工作事项",
				"为会议预留准备时间",
				"晚上回顾学习计划完成情况",
			},
		}
	case SkillNewsBriefing:
		return P0ProactiveSkillResult{
			SkillID:  skillID,
			Title:    "新闻简报：" + firstQueryOrDefault(queries, "关注话题"),
			Summary:  why + " 公开来源显示" + evidenceText + "有新摘要，可继续追问来源详情。",
			Prompt:   "新闻简报主动摘要：" + rawText,
			Why:      why,
			Evidence: []string{"fake_news: 人工智能芯片进展", "fake_news: 模型更新", "fake_news: 产业政策摘要"},
			NextActions: []string{
				"查看来源摘要",
				"追问某个话题的详细影响",
				"调整订阅关键词",
			},
		}
	case SkillStockSentinel:
		return P0ProactiveSkillResult{
			SkillID:  skillID,
			Title:    "股票哨兵：重大消息摘要",
			Summary:  why + " 模拟消息显示关注公司出现重大信息变化；本提醒仅作信息摘要，非投资建议。",
			Prompt:   "股票哨兵主动摘要：" + rawText + "。必须包含非投资建议边界。",
			Why:      why,
			Evidence: []string{"fake_market: 盘前波动扩大", "fake_news: 公司公告摘要", "fake_sector: 行业政策变化"},
			NextActions: []string{
				"核对公开公告原文",
				"查看自选股消息面",
				"仅作信息参考，不构成买卖建议",
			},
		}
	case SkillTravelJourneyManager:
		return P0ProactiveSkillResult{
			SkillID:  skillID,
			Title:    "出行管家：今日行程提醒",
			Summary:  why + " 模拟天气、路况和景点拥堵显示出发前需要调整时间。",
			Prompt:   "出行旅程主动提醒：" + rawText,
			Why:      why,
			Evidence: []string{"fake_weather: 午后有阵雨", "fake_traffic: 高峰路段拥堵", "fake_poi: 热门景点排队升高"},
			NextActions: []string{
				"提前 30 分钟出发",
				"准备雨具",
				"优先预约或错峰参观",
			},
		}
	default:
		return P0ProactiveSkillResult{
			SkillID:     skillID,
			Title:       "小趣主动提醒",
			Summary:     fmt.Sprintf("你订阅的 %s 已在 %s 生成提醒。", skillID, now.UTC().Format("15:04")),
			Prompt:      rawText,
			Why:         why,
			Evidence:    []string{"fake_subscription: cron 命中"},
			NextActions: []string{"打开找私助查看详情"},
		}
	}
}

func IsP0ProactiveSkill(skillID string) bool {
	switch strings.TrimSpace(skillID) {
	case SkillDailyAssistant, SkillNewsBriefing, SkillStockSentinel, SkillTravelJourneyManager:
		return true
	default:
		return false
	}
}

func displaySkillName(skillID string) string {
	switch strings.TrimSpace(skillID) {
	case SkillDailyAssistant:
		return "每日助手"
	case SkillNewsBriefing:
		return "新闻简报"
	case SkillStockSentinel:
		return "股票哨兵"
	case SkillTravelJourneyManager:
		return "出行旅程管家"
	default:
		if strings.TrimSpace(skillID) == "" {
			return "主动 Skill"
		}
		return skillID
	}
}

func dailyAssistantTitle(rawText string) string {
	if strings.Contains(rawText, "晚") || strings.Contains(rawText, "复盘") {
		return "每日助手：晚间复盘"
	}
	return "每日助手：早间计划"
}

func firstQueryOrDefault(queries []string, fallback string) string {
	for _, query := range queries {
		if trimmed := strings.TrimSpace(query); trimmed != "" {
			return trimmed
		}
	}
	return fallback
}

func queryEvidence(queries []string) string {
	if len(queries) == 0 {
		return "关注话题"
	}
	return strings.Join(queries, "、")
}
