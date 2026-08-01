package orchestration

import "strings"

// Stable Skill identities remain public to replay fixtures and policy assets;
// activation, tools, context and presentation come only from Skill Package
// profile refs.
const (
	SkillDailyAssistant       = "daily_assistant"
	SkillNewsBriefing         = "news_briefing"
	SkillStockSentinel        = "stock_sentinel"
	SkillTravelJourneyManager = "travel_journey_manager"
)

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
