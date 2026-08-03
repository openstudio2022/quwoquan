// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-progressive-disclosure-routing/spec.md#gwt-002
package local_contract

import (
	"context"
	"strings"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/tests/support/promptassets"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

// promptRecordingModel 记录每个 stage 收到的提示词，用来断言模型真正读到的是话术正文。
type promptRecordingModel struct {
	prompts []string
}

func (m *promptRecordingModel) Complete(
	_ context.Context,
	req orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	m.prompts = append(m.prompts, req.Prompt)
	if strings.TrimSpace(req.Stage) == "final" {
		return orchestration.ModelResponse{
			Text:            "已完成回答。",
			StructuredDelta: map[string]any{"userMarkdown": "已完成回答。"},
			FinishReason:    "stop",
		}, nil
	}
	return orchestration.ModelResponse{
		Text:            `{"nextAction":"final_answer"}`,
		StructuredDelta: map[string]any{"nextAction": "final_answer"},
		FinishReason:    "stop",
	}, nil
}

func (m *promptRecordingModel) joined() string {
	return strings.Join(m.prompts, "\n")
}

// 被选中技能的领域话术必须以正文进入提示词；资产 ID 不得出现在提示词里。
func TestSelectedSkillPromptAssetsResolveToProse(t *testing.T) {
	model := &promptRecordingModel{}
	loop := orchestration.NewAgentLoop(nil, orchestration.ReactRuntime{Model: model}, nil)
	loop.Catalog = skillfixture.Loader{}
	loop.PromptAssets = promptassets.MustResolver(t)

	turn := promptAssetTurn(
		"travel_companion",
		"travel",
		"目的地是杭州，明天出发，帮我安排三天行程",
	)
	if _, failure, err := loop.RunTurn(t.Context(), turn); err != nil || failure != nil {
		t.Fatalf("run turn: failure=%+v err=%v", failure, err)
	}

	prompt := model.joined()
	if !strings.Contains(prompt, "test frozen policy prompt") {
		t.Fatal("frozen policy prompt must stay in the composed prompt")
	}
	if !strings.Contains(prompt, "贴身旅行管家") {
		t.Fatalf("selected skill guidance must reach the model, got %q", prompt)
	}
	if !strings.Contains(prompt, "证据纪律") {
		t.Fatal("shared evidence discipline asset must reach the model")
	}
	for _, assetID := range []string{"travel_companion.system", "assistant.evidence_discipline"} {
		if strings.Contains(prompt, assetID) {
			t.Fatalf("asset id %q leaked into the prompt as prose", assetID)
		}
	}
}

// 渐进披露：未被选中的技能话术不得进入提示词。
func TestUnselectedSkillPromptAssetsStayOutOfPrompt(t *testing.T) {
	model := &promptRecordingModel{}
	loop := orchestration.NewAgentLoop(nil, orchestration.ReactRuntime{Model: model}, nil)
	loop.Catalog = skillfixture.Loader{}
	loop.PromptAssets = promptassets.MustResolver(t)

	turn := promptAssetTurn("weather", "weather", "杭州明天天气怎么样")
	if _, failure, err := loop.RunTurn(t.Context(), turn); err != nil || failure != nil {
		t.Fatalf("run turn: failure=%+v err=%v", failure, err)
	}

	prompt := model.joined()
	if !strings.Contains(prompt, "天气助手") {
		t.Fatalf("weather guidance must reach the model, got %q", prompt)
	}
	for _, foreign := range []string{"贴身旅行管家", "本地生活助手", "通用搜索兜底"} {
		if strings.Contains(prompt, foreign) {
			t.Fatalf("unselected skill guidance %q leaked into the prompt", foreign)
		}
	}
}

// 主动订阅和响应式运行共享同一条 Skill -> Context -> AgentLoop 管线，
// 因此主动技能也必须在选中后才把清单声明的正文装入模型请求。
func TestProactiveSkillPromptAssetsResolveToProse(t *testing.T) {
	model := &promptRecordingModel{}
	loop := orchestration.NewAgentLoop(nil, orchestration.ReactRuntime{Model: model}, nil)
	loop.Catalog = skillfixture.Loader{}
	loop.PromptAssets = promptassets.MustResolver(t)

	turn := promptAssetTurn(
		"news_briefing",
		"content",
		"请生成本期人工智能行业新闻简报",
	)
	// Scheduler starts the canonical Run with the subscribed Skill identity.
	// Keep that identity explicit here so the test exercises proactive lookup
	// instead of reactive natural-language routing.
	turn.SkillID = "news_briefing"
	if _, failure, err := loop.RunTurn(t.Context(), turn); err != nil || failure != nil {
		t.Fatalf("run proactive turn: failure=%+v err=%v", failure, err)
	}

	prompt := model.joined()
	if !strings.Contains(prompt, "新闻简报主动服务") {
		t.Fatalf("proactive skill guidance must reach the model, got %q", prompt)
	}
	if !strings.Contains(prompt, "证据纪律") {
		t.Fatal("proactive web skill must retain shared evidence discipline")
	}
	for _, assetID := range []string{
		"news_briefing.proactive",
		"assistant.evidence_discipline",
	} {
		if strings.Contains(prompt, assetID) {
			t.Fatalf("proactive asset id %q leaked into the prompt", assetID)
		}
	}
}

// 资产无法解析时必须让该轮失败，而不是把 ID 或空话术送进模型。
func TestMissingPromptAssetResolverFailsTurn(t *testing.T) {
	model := &promptRecordingModel{}
	loop := orchestration.NewAgentLoop(nil, orchestration.ReactRuntime{Model: model}, nil)
	loop.Catalog = skillfixture.Loader{}

	turn := promptAssetTurn("travel_companion", "travel", "帮我安排杭州三天行程")
	_, failure, err := loop.RunTurn(t.Context(), turn)
	if err == nil && failure == nil {
		t.Fatal("missing prompt asset resolver must fail the turn")
	}
	if len(model.prompts) != 0 {
		t.Fatalf("model must not be called without resolved guidance, got %v", model.prompts)
	}
}

// 每个清单声明的资产都必须能解析出正文，否则该技能一旦被选中就会整轮失败。
func TestEveryDeclaredPromptAssetResolves(t *testing.T) {
	catalog, err := skillfixture.Load()
	if err != nil {
		t.Fatalf("load assistant domain skill catalog: %v", err)
	}
	resolver := promptassets.MustResolver(t)
	declared := 0
	for _, manifest := range catalog {
		if len(manifest.PromptAssets) == 0 {
			continue
		}
		declared++
		guidance, err := resolver.ResolvePromptAssets(t.Context(), manifest.PromptAssets)
		if err != nil {
			t.Fatalf("skill %q prompt assets must resolve: %v", manifest.SkillID, err)
		}
		if strings.TrimSpace(guidance) == "" {
			t.Fatalf("skill %q prompt assets resolved to empty guidance", manifest.SkillID)
		}
	}
	if declared == 0 {
		t.Fatal("no skill declares prompt assets; progressive disclosure would be vacuous")
	}
}

func TestEveryProactiveSkillDeclaresPromptAssets(t *testing.T) {
	catalog, err := skillfixture.Load()
	if err != nil {
		t.Fatalf("load assistant domain skill catalog: %v", err)
	}
	proactiveCount := 0
	for _, manifest := range catalog {
		if !manifest.IsProactive() {
			continue
		}
		proactiveCount++
		if len(manifest.PromptAssets) == 0 {
			t.Fatalf("proactive skill %q has no prompt assets", manifest.SkillID)
		}
	}
	if proactiveCount == 0 {
		t.Fatal("active catalog fixture has no proactive skills")
	}
}

func promptAssetTurn(skillID string, domainID string, text string) assistant.AssistantTurn {
	return assistant.AssistantTurn{
		SessionID:             "session-prompt-assets",
		TurnID:                "turn-prompt-assets",
		TraceID:               "trace-prompt-assets",
		Input:                 assistant.AssistantTurnInput{Text: text},
		FrozenPolicySelection: testFrozenPolicySelection("assistant-default", skillID, domainID),
	}
}
