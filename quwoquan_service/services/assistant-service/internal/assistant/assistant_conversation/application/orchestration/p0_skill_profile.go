package orchestration

import (
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/ports"
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
	// Personalization attribution (set when an interest profile is applied).
	Personalized    bool
	InterestTags    []string
	MatchedSegments []string
	LifecycleStage  string
}

// BuildP0ProactiveSkillResult renders a P0 proactive skill payload. When
// profile is non-nil and carries signal, the result is personalized with the
// user's interest tags / segments / lifecycle stage (interest tags are also
// woven into Prompt so the downstream model generates more relevant content).
// A nil profile yields the baseline (non-personalized) output unchanged.
func BuildP0ProactiveSkillResult(
	subscription assistant.SkillSubscription,
	profile *ports.ProactiveInterestProfile,
	now time.Time,
) P0ProactiveSkillResult {
	return personalizeProactive(buildP0ProactiveBase(subscription, now), profile)
}

func buildP0ProactiveBase(subscription assistant.SkillSubscription, now time.Time) P0ProactiveSkillResult {
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
			Summary:  why + " 今日可优先安排会议准备、学习计划与作息提醒，建议先处理高优先级事项。",
			Prompt:   "每日助手主动简报：" + rawText,
			Why:      why,
			Evidence: proactiveEvidence(queries, now),
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
			Summary:  why + " 已按你的订阅关键词" + evidenceText + "整理关注方向，可继续追问具体话题与公开来源。",
			Prompt:   "新闻简报主动摘要：" + rawText,
			Why:      why,
			Evidence: proactiveEvidence(queries, now),
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
			Summary:  why + " 已按你订阅的标的整理消息面关注要点；本提醒仅作信息摘要，非投资建议。",
			Prompt:   "股票哨兵主动摘要：" + rawText + "。必须包含非投资建议边界。",
			Why:      why,
			Evidence: proactiveEvidence(queries, now),
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
			Summary:  why + " 出行前建议关注天气、路况与热门景点排队，预留弹性时间。",
			Prompt:   "出行旅程主动提醒：" + rawText,
			Why:      why,
			Evidence: proactiveEvidence(queries, now),
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
			Evidence:    proactiveEvidence(queries, now),
			NextActions: []string{"打开找私助查看详情"},
		}
	}
}

// personalizeProactive layers a user's derived interest profile onto a baseline
// proactive result. It is additive (never removes baseline copy) so non-profile
// callers and existing assertions are unaffected: interest tags / segments /
// lifecycle drive a lifecycle-aware lead-in, a "why" suffix, and explicit
// profile context appended to Prompt for the downstream model.
func personalizeProactive(
	base P0ProactiveSkillResult,
	profile *ports.ProactiveInterestProfile,
) P0ProactiveSkillResult {
	if profile == nil {
		return base
	}
	tags := topInterestTags(profile, 3)
	segments := compactStrings(profile.Segments)
	lifecycle := strings.TrimSpace(profile.LifecycleStage)
	if len(tags) == 0 && len(segments) == 0 && lifecycle == "" {
		return base
	}
	base.Personalized = true
	base.InterestTags = tags
	base.MatchedSegments = segments
	base.LifecycleStage = lifecycle
	if len(tags) > 0 {
		base.Evidence = append(base.Evidence, "兴趣画像匹配："+strings.Join(tags, "、"))
	}
	if len(segments) > 0 {
		base.Evidence = append(base.Evidence, "命中人群："+strings.Join(segments, "、"))
	}

	switch lifecycle {
	case "dormant":
		base.Summary = "好久不见，根据你的兴趣画像为你精选了相关更新。" + base.Summary
	case "new":
		base.Summary = "为刚开始的你，结合可观察到的偏好做了轻度个性化。" + base.Summary
	}

	promptCtx := make([]string, 0, 3)
	if len(tags) > 0 {
		joined := strings.Join(tags, "、")
		base.Why = base.Why + "（已结合你的兴趣画像：" + joined + "）"
		promptCtx = append(promptCtx, "兴趣标签："+joined)
	}
	if len(segments) > 0 {
		promptCtx = append(promptCtx, "人群："+strings.Join(segments, "、"))
	}
	if lifecycle != "" {
		promptCtx = append(promptCtx, "生命周期："+lifecycle)
	}
	if len(promptCtx) > 0 {
		base.Prompt = base.Prompt + " [用户兴趣画像] " + strings.Join(promptCtx, "；")
	}
	return base
}

// IsP0ProactiveSkill 以技能清单的 activation 为准判断是否为主动订阅技能。
func IsP0ProactiveSkill(skillID string) bool {
	_, found := proactiveSkillManifest(strings.TrimSpace(skillID))
	return found
}

func displaySkillName(skillID string) string {
	skillID = strings.TrimSpace(skillID)
	if skillID == "" {
		return "主动 Skill"
	}
	if manifest, found, err := assistantDomainSkillManifest(skillID); err == nil && found {
		if name := strings.TrimSpace(manifest.DisplayName); name != "" {
			return name
		}
	}
	return skillID
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

// proactiveEvidence renders the real, auditable basis for a proactive reminder:
// the user's subscription query plan plus the cron trigger time. It deliberately
// carries no fabricated external-data rows (no fake_news / fake_market /
// fake_weather): the assistant does not yet ingest those live sources, so the
// only honest baseline evidence is the subscription itself; personalizeProactive
// later appends the user's interest-profile match when a profile is available.
func proactiveEvidence(queries []string, now time.Time) []string {
	evidence := make([]string, 0, 2)
	if joined := strings.Join(compactStrings(queries), "、"); joined != "" {
		evidence = append(evidence, "订阅关注："+joined)
	}
	evidence = append(evidence, "触发时间："+now.UTC().Format("15:04")+"（cron 命中）")
	return evidence
}
