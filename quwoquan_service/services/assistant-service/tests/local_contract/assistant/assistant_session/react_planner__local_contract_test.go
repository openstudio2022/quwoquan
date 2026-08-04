package local_contract

import (
	"testing"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/reasoning"
)

func TestReactPlannerUsesStructuredToolDelta(t *testing.T) {
	decision := ReactPlanner{}.Decide(PlanInput{
		StructuredDelta: map[string]any{
			"nextAction": "tool_call",
			"toolName":   "app_search",
			"toolInput":  map[string]any{"query": "站内 AI 内容"},
		},
		ToolPolicy: []string{"web_search"},
		Budget:     DefaultBudget(),
	})
	if !decision.CallsTool() || decision.ToolName != "app_search" {
		t.Fatalf("decision=%#v", decision)
	}
	if decision.ToolInput["query"] != "站内 AI 内容" {
		t.Fatalf("toolInput=%#v", decision.ToolInput)
	}
	if decision.ActionCode != assistantgenerated.PlannerActionCodeExecuteSearch {
		t.Fatalf("actionCode=%q want execute_search", decision.ActionCode)
	}
}

func TestReactPlannerRejectsMissingToolNameWithoutChoosingPolicyFallback(t *testing.T) {
	decision := ReactPlanner{}.Decide(PlanInput{
		StructuredDelta: map[string]any{"nextAction": "tool_call"},
		ToolPolicy:      []string{"web_search"},
		Budget:          DefaultBudget(),
	})
	if decision.CallsTool() || !decision.Rejected() {
		t.Fatalf("decision=%#v want a non-executable rejection", decision)
	}
	if decision.ToolName != "" || decision.ReasonCode != "tool_name_required" {
		t.Fatalf("decision=%#v", decision)
	}
	if !decision.Rejection.Retryable ||
		len(decision.Rejection.AllowedTools) != 1 ||
		decision.Rejection.AllowedTools[0] != "web_search" {
		t.Fatalf("rejection=%#v", decision.Rejection)
	}
}

func TestReactPlannerAnswersWithoutStructuredToolDecision(t *testing.T) {
	decision := ReactPlanner{}.Decide(PlanInput{
		ReasoningText: "模型已直接给出无需检索的回答",
		ToolPolicy:    []string{"web_search"},
		Budget:        DefaultBudget(),
	})
	if decision.Rejected() || decision.CallsTool() ||
		decision.NextAction != assistantgenerated.AssistantNextActionAnswer {
		t.Fatalf("decision=%#v want direct answer", decision)
	}
	if decision.ReasonCode != "no_structured_tool_decision" {
		t.Fatalf("reasonCode=%q", decision.ReasonCode)
	}
}

func TestReactPlannerAnswersWhenToolBudgetIsExhausted(t *testing.T) {
	decision := ReactPlanner{}.Decide(PlanInput{
		StructuredDelta: map[string]any{"nextAction": "tool_call", "toolName": "web_search"},
		ToolPolicy:      []string{"web_search"},
		Budget:          Budget{MaxIterations: 1, MaxToolCalls: 0},
	})
	if decision.NextAction != assistantgenerated.AssistantNextActionAnswer {
		t.Fatalf("nextAction=%q want answer", decision.NextAction)
	}
	if decision.ReasonCode != "tool_budget_exhausted" {
		t.Fatalf("reasonCode=%q want tool_budget_exhausted", decision.ReasonCode)
	}
}

func TestReactPlannerRequestsClarificationWithPrompt(t *testing.T) {
	decision := ReactPlanner{}.Decide(PlanInput{
		StructuredDelta: map[string]any{
			"nextAction": "ask_user",
			"askUser": map[string]any{
				"slotId":      "destination",
				"prompt":      "你想去哪座城市？",
				"required":    true,
				"suggestions": []any{"杭州", "苏州"},
			},
		},
		ToolPolicy: []string{"web_search"},
		Budget:     DefaultBudget(),
	})
	if !decision.AsksUser() {
		t.Fatalf("decision=%#v want ask_user", decision)
	}
	if decision.AskUser.SlotID != "destination" || !decision.AskUser.Required {
		t.Fatalf("askUser=%#v", decision.AskUser)
	}
	if len(decision.AskUser.Suggestions) != 2 {
		t.Fatalf("suggestions=%#v want two options", decision.AskUser.Suggestions)
	}
	if decision.ActionCode != assistantgenerated.PlannerActionCodeAskClarification {
		t.Fatalf("actionCode=%q want ask_clarification", decision.ActionCode)
	}
}

func TestReactPlannerRejectsClarificationWithoutPrompt(t *testing.T) {
	decision := ReactPlanner{}.Decide(PlanInput{
		StructuredDelta: map[string]any{
			"nextAction": "ask_user",
			"askUser":    map[string]any{"slotId": "destination"},
		},
		ToolPolicy: []string{"web_search"},
		Budget:     DefaultBudget(),
	})
	if decision.AsksUser() {
		t.Fatalf("empty clarification must not reach the user: %#v", decision)
	}
	if decision.ReasonCode != "ask_user_without_prompt" {
		t.Fatalf("reasonCode=%q want ask_user_without_prompt", decision.ReasonCode)
	}
}

func TestReactPlannerMapsReplanAndRetryToActionCodes(t *testing.T) {
	replan := ReactPlanner{}.Decide(PlanInput{
		StructuredDelta: map[string]any{
			"nextAction": "replan", "toolName": "web_search",
		},
		ToolPolicy: []string{"web_search"},
		Budget:     DefaultBudget(),
	})
	if replan.ActionCode != assistantgenerated.PlannerActionCodeExpandSearch {
		t.Fatalf("replan actionCode=%q want expand_search", replan.ActionCode)
	}
	retry := ReactPlanner{}.Decide(PlanInput{
		StructuredDelta: map[string]any{
			"nextAction": "retry", "toolName": "web_search",
		},
		ToolPolicy: []string{"web_search"},
		Budget:     DefaultBudget(),
	})
	if retry.ActionCode != assistantgenerated.PlannerActionCodeRecoverRetrieval {
		t.Fatalf("retry actionCode=%q want recover_retrieval", retry.ActionCode)
	}
}

func TestReactPlannerTreatsUnparsableActionAsToolCall(t *testing.T) {
	decision := ReactPlanner{}.Decide(PlanInput{
		StructuredDelta: map[string]any{
			"nextAction": "final_answer", "toolName": "web_search",
		},
		ToolPolicy: []string{"web_search"},
		Budget:     DefaultBudget(),
	})
	if !decision.CallsTool() {
		t.Fatalf("decision=%#v want the deterministic tool path", decision)
	}
	if decision.ReasonCode != "unparsable_next_action" {
		t.Fatalf("reasonCode=%q want unparsable_next_action", decision.ReasonCode)
	}
}

func TestReactPlannerAbortsWithFallbackActionCode(t *testing.T) {
	decision := ReactPlanner{}.Decide(PlanInput{
		StructuredDelta: map[string]any{"nextAction": "abort", "reasonCode": "unsafe_request"},
		ToolPolicy:      []string{"web_search"},
		Budget:          DefaultBudget(),
	})
	if !decision.Aborts() {
		t.Fatalf("decision=%#v want abort", decision)
	}
	if decision.ActionCode != assistantgenerated.PlannerActionCodeFallbackWithExistingEvidence {
		t.Fatalf("actionCode=%q want fallback_with_existing_evidence", decision.ActionCode)
	}
	if decision.ReasonCode != "unsafe_request" {
		t.Fatalf("reasonCode=%q want unsafe_request", decision.ReasonCode)
	}
}
