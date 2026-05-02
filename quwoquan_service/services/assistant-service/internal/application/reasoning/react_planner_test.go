package reasoning

import "testing"

func TestReactPlannerUsesStructuredToolDelta(t *testing.T) {
	steps := ReactPlanner{}.Plan(PlanInput{
		StructuredDelta: map[string]any{
			"nextAction": "call_tool",
			"toolName":   "app_search",
			"toolInput":  map[string]any{"query": "站内 AI 内容"},
		},
		ToolPolicy: []string{"web_search"},
		Budget:     DefaultBudget(),
	})
	if len(steps) < 2 {
		t.Fatalf("steps=%#v", steps)
	}
	if steps[0].Action != "tool" || steps[0].ToolName != "app_search" {
		t.Fatalf("first step=%#v", steps[0])
	}
	if steps[0].Input["query"] != "站内 AI 内容" {
		t.Fatalf("input=%#v", steps[0].Input)
	}
}

func TestReactPlannerFallsBackToToolPolicy(t *testing.T) {
	steps := ReactPlanner{}.Plan(PlanInput{
		ToolPolicy: []string{"web_search"},
		Budget:     DefaultBudget(),
	})
	if steps[0].ToolName != "web_search" {
		t.Fatalf("toolName=%q", steps[0].ToolName)
	}
}
