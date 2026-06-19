package recpolicy

import "testing"

func TestPresetForScenario_BaselineMappings(t *testing.T) {
	p := Baseline()
	cases := []struct {
		scenario string
		want     string
	}{
		{"homepage", "premium"},        // 实体/人物主页记录流 → 精品
		{"similar", "premium"},         // 沉浸相似消费 → 精品
		{"circle", "engagement_heavy"}, // 圈子记录流
		{"topic", "engagement_heavy"},
		{"search", "engagement_heavy"}, // 搜索发现区
		{"discovery", p.DefaultPreset}, // 主发现流回落默认，行为不变
		{"", p.DefaultPreset},          // 空场景回落默认
		{"unknown_surface", p.DefaultPreset},
	}
	for _, c := range cases {
		if got := p.PresetForScenario(c.scenario); got != c.want {
			t.Fatalf("PresetForScenario(%q)=%q want %q", c.scenario, got, c.want)
		}
	}
}

func TestPremiumPresetEmphasizesFinishOverPopularity(t *testing.T) {
	p := Baseline()
	premium, ok := p.WeightPresets["premium"]
	if !ok {
		t.Fatal("premium preset missing from baseline")
	}
	control := p.WeightPresets[p.DefaultPreset]
	// 精品应弱化纯热度、强化完成/停留与相关性。
	if !(premium.DwellBonus > control.DwellBonus) {
		t.Fatalf("premium dwellBonus %.2f should exceed control %.2f", premium.DwellBonus, control.DwellBonus)
	}
	if !(premium.Popularity < control.Popularity) {
		t.Fatalf("premium popularity %.2f should be below control %.2f", premium.Popularity, control.Popularity)
	}
	if !(premium.TagRelevance >= control.TagRelevance) {
		t.Fatalf("premium tagRelevance %.2f should be >= control %.2f", premium.TagRelevance, control.TagRelevance)
	}
}

func TestPresetForScenario_FallsBackOnInvalidMapping(t *testing.T) {
	p := &RecPolicy{
		PolicyVersion: "test",
		DefaultPreset: "control",
		WeightPresets: map[string]WeightPreset{"control": {}},
		ScenarioRouting: map[string]string{
			"homepage": "nonexistent_preset",
		},
	}
	if got := p.PresetForScenario("homepage"); got != "control" {
		t.Fatalf("invalid mapped preset must fall back to default, got %q", got)
	}
}

func TestValidate_RejectsUnknownScenarioPreset(t *testing.T) {
	p := Baseline()
	p.ScenarioRouting = map[string]string{"homepage": "ghost_preset"}
	if err := p.Validate(); err == nil {
		t.Fatal("expected validation error for unknown scenarioRouting preset")
	}
}
