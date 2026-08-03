// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-progressive-disclosure-routing/spec.md#req-003
package local_contract

import (
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/skill"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

// 主动订阅技能与反应式技能必须来自同一份技能清单：清单是判定主动性、展示名与工具策略的
// 唯一来源。
func TestProactiveSkillsComeFromManifestCatalog(t *testing.T) {
	catalog, err := skillfixture.Load()
	if err != nil {
		t.Fatalf("load assistant domain skill catalog: %v", err)
	}
	proactive := map[string]skillpkg.Manifest{}
	for _, manifest := range catalog {
		if manifest.IsProactive() {
			proactive[manifest.SkillID] = manifest
		}
	}
	if len(proactive) == 0 {
		t.Fatal("manifest catalog must declare at least one proactive skill")
	}
	for skillID, manifest := range proactive {
		selection, err := (orchestration.DefaultSkillRuntime{Loader: skillfixture.Loader{}}).SelectSkill(
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
		wantTools := manifest.ToolPolicy.AllowedTools
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

// 纯主动订阅 Skill 不得被用户提问选中；hybrid 的旅行 Skill 则必须同时可被用户调用。
func TestProactiveSkillsAreNotSelectableByUserQuestions(t *testing.T) {
	runtime := orchestration.ManifestSkillRuntime{Loader: publishedSkillLoader{}}
	catalog, err := publishedSkillLoader{}.Load(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	pureProactive := map[string]bool{}
	for _, manifest := range catalog {
		if manifest.Activation == skillpkg.ActivationProactive {
			pureProactive[manifest.SkillID] = true
		}
	}
	questions := []string{
		"帮我看下今天的待办和会议安排",
		"最近的新闻简报有什么",
		"我关注的股票有什么消息",
	}
	for _, question := range questions {
		selection, err := runtime.SelectSkill(
			t.Context(),
			assistant.AssistantTurn{Input: assistant.AssistantTurnInput{Text: question}},
		)
		if err != nil {
			t.Fatalf("select skill for %q: %v", question, err)
		}
		if pureProactive[selection.SkillID] {
			t.Fatalf("question %q selected proactive skill %q", question, selection.SkillID)
		}
	}
	selection, err := runtime.SelectSkill(
		t.Context(),
		assistant.AssistantTurn{Input: assistant.AssistantTurnInput{Text: "我的行程有风险吗"}},
	)
	if err != nil || selection.SkillID != "travel_companion" {
		t.Fatalf("hybrid travel skill selection=%#v err=%v", selection, err)
	}
}
