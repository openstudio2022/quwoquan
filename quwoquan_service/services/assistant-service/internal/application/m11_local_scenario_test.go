package application

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

func TestM11CloudAlphaUserInitiatedScenariosProduceTypedStream(t *testing.T) {
	t.Setenv("APP_ENV", "alpha")
	if got := os.Getenv("APP_ENV"); got != "alpha" {
		t.Fatalf("APP_ENV=%q, want alpha", got)
	}

	now := time.Date(2026, 4, 29, 9, 30, 0, 0, time.UTC)
	pack, err := LoadAssistantScenarioPack()
	if err != nil {
		t.Fatalf("LoadAssistantScenarioPack() error = %v", err)
	}
	cases := pack.AssistantTurnScenariosFor("alpha")
	if len(cases) == 0 {
		t.Fatal("assistant scenarios should not be empty")
	}

	for _, tc := range cases {
		t.Run(tc.ID, func(t *testing.T) {
			loop := NewAgentLoop(
				staticSkillRuntime{selection: SkillSelection{
					SkillID:    tc.SkillID,
					DomainID:   tc.DomainID,
					ToolPolicy: scenarioToolPolicy(t, tc.SkillID),
				}},
				ReactRuntime{
					Model: DeterministicModelProvider{},
					Tools: DefaultToolCoordinator{
						Now: func() time.Time { return now },
					},
				},
				func() time.Time { return now },
			)

			events, failure, err := loop.RunTurn(context.Background(), assistant.AssistantTurn{
				TurnID:         "atn_m11_" + strings.ReplaceAll(tc.ID, "-", "_"),
				ConversationID: "acv_m11_local",
				UserID:         "user_m11_local",
				TurnType:       "user",
				Status:         "running",
				SkillID:        tc.SkillID,
				DomainID:       tc.DomainID,
				Input:          assistant.AssistantTurnInput{Text: tc.Question},
				Trigger:        assistant.AssistantTurnTrigger{Type: "user_message"},
				TraceID:        "trace_m11_local",
				CreatedAt:      now,
			})
			if err != nil {
				t.Fatalf("RunTurn() error = %v", err)
			}
			if failure != nil {
				t.Fatalf("unexpected runtime failure: %#v", failure)
			}

			assertM11TypedStream(t, events)
			finalAnswer := finalAnswerText(t, events)
			for _, want := range tc.RemoteAnswerFragments() {
				if !strings.Contains(finalAnswer, want) {
					t.Fatalf("final answer %q missing %q", finalAnswer, want)
				}
			}
		})
	}
}

func TestM11ReactiveP0SkillInferenceForBetaQuestions(t *testing.T) {
	pack, err := LoadAssistantScenarioPack()
	if err != nil {
		t.Fatalf("LoadAssistantScenarioPack() error = %v", err)
	}
	cases := pack.AssistantTurnScenariosFor("beta")

	for _, tc := range cases {
		t.Run(tc.ID, func(t *testing.T) {
			if !containsHan(tc.Question) {
				t.Skip("非中文自由输入依赖模型语义改写，不由 deterministic fallback 断言")
			}
			selection, err := DefaultSkillRuntime{}.SelectSkill(context.Background(), assistant.AssistantTurn{
				Input: assistant.AssistantTurnInput{Text: tc.Question},
			})
			if err != nil {
				t.Fatalf("SelectSkill() error = %v", err)
			}
			if !skillMatchesScenario(selection.SkillID, tc.SkillID) {
				t.Fatalf("skillID=%q, want compatible with %q", selection.SkillID, tc.SkillID)
			}
			if len(selection.ToolPolicy) == 0 {
				t.Fatalf("tool policy should not be empty: %#v", selection)
			}
		})
	}
}

func containsHan(text string) bool {
	for _, r := range text {
		if r >= '\u4e00' && r <= '\u9fff' {
			return true
		}
	}
	return false
}

func scenarioToolPolicy(t *testing.T, skillID string) []string {
	t.Helper()
	if IsP0ProactiveSkill(skillID) {
		return p0SkillToolPolicy(skillID)
	}
	for _, manifest := range AssistantDomainSkillCatalog() {
		if manifest.SkillID != skillID {
			continue
		}
		if len(manifest.ToolPolicy.PreferredTools) > 0 {
			return append([]string{}, manifest.ToolPolicy.PreferredTools...)
		}
		return append([]string{}, manifest.ToolPolicy.AllowedTools...)
	}
	t.Fatalf("missing skill manifest for %s", skillID)
	return nil
}

func assertM11TypedStream(t *testing.T, events []streaming.Envelope) {
	t.Helper()
	wantOrder := []string{
		"turn_started",
		"plan_updated",
		"search_query_generated",
		"tool_use_requested",
		"tool_result_received",
		"observation_assessed",
		"final_answer",
	}
	cursor := 0
	for _, want := range wantOrder {
		found := false
		for cursor < len(events) {
			if events[cursor].EventType == want {
				found = true
				cursor++
				break
			}
			cursor++
		}
		if !found {
			t.Fatalf("missing eventType %q in %#v", want, events)
		}
	}
	for i, event := range events {
		if event.Seq != uint64(i+1) {
			t.Fatalf("event %d seq=%d, want %d", i, event.Seq, i+1)
		}
		if event.TraceID != "trace_m11_local" {
			t.Fatalf("event %d traceId=%q", i, event.TraceID)
		}
	}
}

func skillMatchesScenario(actual, expected string) bool {
	if actual == expected {
		return true
	}
	compatible := map[string][]string{
		SkillStockSentinel:        {"finance_consumer"},
		SkillTravelJourneyManager: {"weather", "travel_planning", "travel_transport"},
	}
	for _, item := range compatible[expected] {
		if actual == item {
			return true
		}
	}
	return false
}

func finalAnswerText(t *testing.T, events []streaming.Envelope) string {
	t.Helper()
	for _, event := range events {
		if event.EventType != "final_answer" {
			continue
		}
		text, _ := event.Payload["text"].(string)
		if strings.TrimSpace(text) == "" {
			t.Fatalf("final_answer missing payload.text: %#v", event.Payload)
		}
		return text
	}
	t.Fatalf("missing final_answer event")
	return ""
}
