// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/long-term-memory-compaction/spec.md#gwt-002
// readiness_case: compact-assistant-session-local
package local_contract

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	runmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	sessioncompaction "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/compaction"
	sessionmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/persistence"
)

type terminalRunReader struct {
	run runruntime.Run
}

func (reader terminalRunReader) Load(
	_ context.Context,
	runID string,
) (runruntime.Run, error) {
	if runID != reader.run.RunID {
		return runruntime.Run{}, errors.New("terminal Run not found")
	}
	return reader.run, nil
}

type recordingNarrativeGenerator struct {
	calls  int
	inputs []sessioncompaction.NarrativeInput
}

func TestAssistantRunTerminalCoordinatorCompactsTheOwnedSession(t *testing.T) {
	store := persistence.NewMemorySessionStore()
	now := time.Date(2026, 8, 4, 9, 0, 0, 0, time.UTC)
	_, _, err := store.InsertSession(t.Context(), sessionmodel.AssistantSession{
		SessionID: "session-terminal-coordinator",
		UserID:    "user-terminal-coordinator",
		State:     "active",
		CreatedAt: now.Add(-time.Hour),
		UpdatedAt: now.Add(-time.Hour),
	})
	if err != nil {
		t.Fatalf("insert AssistantSession: %v", err)
	}
	hooks, err := runruntime.NewHookRegistry()
	if err != nil {
		t.Fatalf("create hook registry: %v", err)
	}
	coordinator := sessioncompaction.NewAssistantRunTerminalCoordinator(
		terminalRunReader{run: runruntime.Run{
			RunID:     "run-terminal-coordinator",
			UserID:    "user-terminal-coordinator",
			SessionID: "session-terminal-coordinator",
			InputText: "规划杭州行程并确认酒店",
			State:     assistantgenerated.AssistantRunStateCompleted,
			TaskGraph: runruntime.TaskGraph{Tasks: []runruntime.TaskNode{{
				TaskID: "task-confirm-hotel",
				Goal:   "确认酒店",
				Status: assistantgenerated.AssistantTaskStatusPending,
			}}},
			TerminalSnapshot: &runmodel.AssistantRunTerminalSnapshot{
				AnswerText: "已给出第一版路线",
			},
		}},
		sessioncompaction.NewService(store, &recordingNarrativeGenerator{}),
		hooks,
	)
	event := runruntime.TerminalEvent{
		EventID:    "run-terminal-coordinator:terminal",
		RunID:      "run-terminal-coordinator",
		UserID:     "user-terminal-coordinator",
		SessionID:  "session-terminal-coordinator",
		Outcome:    "completed",
		OccurredAt: now,
	}
	if err := coordinator.CompactSession(t.Context(), event); err != nil {
		t.Fatalf("compact terminal AssistantRun: %v", err)
	}
	if err := coordinator.HandleTerminalEvent(t.Context(), event); err != nil {
		t.Fatalf("replay terminal AssistantRun: %v", err)
	}
	persisted, found, err := store.GetSession(t.Context(), event.SessionID)
	if err != nil || !found || persisted.ContextSummary == nil {
		t.Fatalf("persisted terminal summary=%+v found=%t err=%v", persisted, found, err)
	}
	if persisted.ContextSummary.ToTurnID != event.RunID ||
		persisted.SummaryVersion != 1 || persisted.CompletionSequence != 1 ||
		!strings.Contains(persisted.ContextSummary.Text, "待处理：确认酒店") {
		t.Fatalf("terminal coordinator did not own compaction: %+v", persisted)
	}
}

func (generator *recordingNarrativeGenerator) GenerateRollingNarrative(
	_ context.Context,
	input sessioncompaction.NarrativeInput,
) (string, error) {
	generator.calls++
	generator.inputs = append(generator.inputs, input)
	return "你已确定杭州行程，下一步需要确认酒店。", nil
}

func TestCompletedRunCompactsRollingSessionWithIdempotentReceipt(t *testing.T) {
	store := persistence.NewMemorySessionStore()
	now := time.Date(2026, 8, 4, 10, 0, 0, 0, time.UTC)
	_, _, err := store.InsertSession(t.Context(), sessionmodel.AssistantSession{
		SessionID: "session-rolling-summary",
		UserID:    "user-rolling-summary",
		State:     "active",
		CreatedAt: now.Add(-time.Hour),
		UpdatedAt: now.Add(-time.Hour),
	})
	if err != nil {
		t.Fatalf("insert AssistantSession: %v", err)
	}
	generator := &recordingNarrativeGenerator{}
	service := sessioncompaction.NewService(store, generator)
	source := sessioncompaction.CompletedRunSource{
		CompletionEventID: "run-rolling-summary:terminal",
		RunID:             "run-rolling-summary",
		SessionID:         "session-rolling-summary",
		UserID:            "user-rolling-summary",
		CurrentGoal:       "完成杭州三日行程",
		UserInput:         "去杭州三天，预算五千元",
		AnswerText:        "已给出第一版路线",
		ConfirmedFacts:    []string{"同行人数为 2 人"},
		PendingItems:      []string{"确认酒店"},
		ConfirmedSlots:    map[string]string{"destination": "杭州"},
		CompletedAt:       now,
	}

	first, err := service.CompactCompletedRun(t.Context(), source)
	if err != nil {
		t.Fatalf("compact completed Run: %v", err)
	}
	if !strings.HasPrefix(first.SummaryID, "sha256:") ||
		len(first.SummaryID) != len("sha256:")+64 {
		t.Fatalf("summary identity is not canonical SHA-256: %q", first.SummaryID)
	}
	for _, want := range []string{
		"当前目标：完成杭州三日行程",
		"已确认槽位：destination=杭州",
		"已确认事实：同行人数为 2 人",
		"待处理：确认酒店",
		"连续摘要：你已确定杭州行程",
	} {
		if !strings.Contains(first.Text, want) {
			t.Fatalf("rolling summary missing %q: %s", want, first.Text)
		}
	}
	if first.FromTurnID != source.RunID || first.ToTurnID != source.RunID ||
		first.TurnCount != 1 || generator.calls != 1 {
		t.Fatalf("summary=%+v generator calls=%d", first, generator.calls)
	}

	// Simulate commit succeeded but terminal outbox acknowledgement was lost.
	replayed, err := service.CompactCompletedRun(t.Context(), source)
	if err != nil {
		t.Fatalf("replay completed Run: %v", err)
	}
	if replayed.SummaryID != first.SummaryID || generator.calls != 1 {
		t.Fatalf(
			"terminal replay changed summary or called provider: first=%+v replay=%+v calls=%d",
			first,
			replayed,
			generator.calls,
		)
	}
	persisted, found, err := store.GetSession(t.Context(), source.SessionID)
	if err != nil || !found || persisted.ContextSummary == nil ||
		persisted.SummaryVersion != 1 || persisted.SummarySourceSequence != 1 ||
		persisted.CompletionSequence != 1 {
		t.Fatalf("persisted rolling summary=%+v found=%t err=%v", persisted, found, err)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/long-term-memory-compaction/spec.md#gwt-002
func TestCompactorMergesCurrentRunSlotsWithPreviousSummary(t *testing.T) {
	store := persistence.NewMemorySessionStore()
	now := time.Date(2026, 8, 4, 12, 0, 0, 0, time.UTC)
	_, _, err := store.InsertSession(t.Context(), sessionmodel.AssistantSession{
		SessionID: "session-workshop-carry-over",
		UserID:    "user-workshop-carry-over",
		State:     "active",
		ContextSummary: &sessionmodel.AssistantSessionContextSummary{
			SummaryID:   "sha256:" + strings.Repeat("a", 64),
			Text:        "当前目标：准备工作坊\n已确认槽位：meeting_place=杭州；workshop_topic=旧议题\n连续摘要：此前已确定会场。",
			FromTurnID:  "run-workshop-before",
			ToTurnID:    "run-workshop-before",
			TurnCount:   1,
			CurrentGoal: "准备工作坊",
			ConfirmedSlots: map[string]string{
				"meeting_place":  "杭州",
				"workshop_topic": "旧议题",
			},
		},
		SummaryVersion:        1,
		SummarySourceSequence: 1,
		CompletionSequence:    1,
		CreatedAt:             now.Add(-time.Hour),
		UpdatedAt:             now.Add(-time.Hour),
	})
	if err != nil {
		t.Fatalf("insert AssistantSession: %v", err)
	}
	generator := &recordingNarrativeGenerator{}
	summary, err := sessioncompaction.NewService(store, generator).CompactCompletedRun(
		t.Context(),
		sessioncompaction.CompletedRunSource{
			CompletionEventID: "run-workshop-current:terminal",
			RunID:             "run-workshop-current",
			SessionID:         "session-workshop-carry-over",
			UserID:            "user-workshop-carry-over",
			CurrentGoal:       "完成工作坊方案",
			UserInput:         "议题是依赖反转",
			AnswerText:        "已整理下一步",
			ConfirmedSlots: map[string]string{
				"workshop_topic": "依赖反转",
			},
			CompletedAt: now,
		},
	)
	if err != nil {
		t.Fatalf("compact current Run slots: %v", err)
	}
	if summary.ConfirmedSlots["meeting_place"] != "杭州" ||
		summary.ConfirmedSlots["workshop_topic"] != "依赖反转" ||
		len(summary.ConfirmedSlots) != 2 {
		t.Fatalf("merged confirmed slots=%#v", summary.ConfirmedSlots)
	}
	if generator.calls != 1 || len(generator.inputs) != 1 ||
		generator.inputs[0].ConfirmedSlots["workshop_topic"] != "依赖反转" {
		t.Fatalf("narrative input did not receive protected merge: %#v", generator.inputs)
	}
}
