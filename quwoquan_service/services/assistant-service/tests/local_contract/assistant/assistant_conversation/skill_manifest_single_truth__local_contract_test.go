// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-progressive-disclosure-routing/spec.md#req-003
package local_contract

import (
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/orchestration"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/skill"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

// 主动订阅技能与反应式技能必须来自同一份技能清单：清单是判定主动性、展示名与工具策略的
// 唯一来源。
func TestProactiveSkillsComeFromManifestCatalog(t *testing.T) {
	catalog, err := orchestration.LoadAssistantDomainSkillCatalog()
	if err != nil {
		t.Fatalf("load assistant domain skill catalog: %v", err)
	}
	proactive := map[string]skillpkg.Manifest{}
	for _, manifest := range catalog {
		if manifest.IsProactive() {
			proactive[manifest.SkillID] = manifest
		}
	}
	expected := []string{
		orchestration.SkillDailyAssistant,
		orchestration.SkillNewsBriefing,
		orchestration.SkillStockSentinel,
		orchestration.SkillTravelJourneyManager,
	}
	for _, skillID := range expected {
		manifest, found := proactive[skillID]
		if !found {
			t.Fatalf("proactive skill %q must be declared by a manifest", skillID)
		}
		if !orchestration.IsP0ProactiveSkill(skillID) {
			t.Fatalf("skill %q manifest declares proactive activation but runtime disagrees", skillID)
		}
		selection, err := orchestration.DefaultSkillRuntime{}.SelectSkill(
			t.Context(),
			assistant.AssistantTurn{SkillID: skillID},
		)
		if err != nil {
			t.Fatalf("select proactive skill %q: %v", skillID, err)
		}
		if selection.DisplayName != manifest.DisplayName {
			t.Fatalf(
				"skill %q display name %q must come from the manifest %q",
				skillID,
				selection.DisplayName,
				manifest.DisplayName,
			)
		}
		wantTools := manifest.ToolPolicy.PreferredTools
		if len(wantTools) == 0 {
			wantTools = manifest.ToolPolicy.AllowedTools
		}
		if len(selection.ToolPolicy) != len(wantTools) {
			t.Fatalf(
				"skill %q tool policy %v must come from the manifest %v",
				skillID,
				selection.ToolPolicy,
				wantTools,
			)
		}
		for i, name := range wantTools {
			if selection.ToolPolicy[i] != name {
				t.Fatalf(
					"skill %q tool policy %v must come from the manifest %v",
					skillID,
					selection.ToolPolicy,
					wantTools,
				)
			}
		}
	}
}

// 主动订阅技能不得被用户提问选中，否则一次普通提问会跑成订阅推送话术。
func TestProactiveSkillsAreNotSelectableByUserQuestions(t *testing.T) {
	runtime := orchestration.ManifestSkillRuntime{Loader: publishedSkillLoader{}}
	questions := []string{
		"帮我看下今天的待办和会议安排",
		"最近的新闻简报有什么",
		"我关注的股票有什么消息",
		"我的行程有风险吗",
	}
	for _, question := range questions {
		selection, err := runtime.SelectSkill(
			t.Context(),
			assistant.AssistantTurn{Input: assistant.AssistantTurnInput{Text: question}},
		)
		if err != nil {
			t.Fatalf("select skill for %q: %v", question, err)
		}
		if orchestration.IsP0ProactiveSkill(selection.SkillID) {
			t.Fatalf("question %q selected proactive skill %q", question, selection.SkillID)
		}
	}
}
