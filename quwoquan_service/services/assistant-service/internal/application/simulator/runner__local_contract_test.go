package simulator

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"quwoquan_service/runtime/streaming"
	app "quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

func TestRunner_RunReplayCases(t *testing.T) {
	fixtures := []string{
		"replay_direct_answer_min.json",
		"replay_tool_search_min.json",
		"replay_tool_failure_min.json",
	}
	for _, fixture := range fixtures {
		t.Run(fixture, func(t *testing.T) {
			replay, err := LoadCase(filepath.Join("../../../../../contracts/metadata/assistant/test_fixtures", fixture))
			if err != nil {
				t.Fatalf("load replay case: %v", err)
			}
			transcript, err := (Runner{Now: func() time.Time {
				return time.Date(2026, 4, 29, 0, 0, 0, 0, time.UTC)
			}}).Run(context.Background(), replay)
			if err != nil {
				t.Fatalf("run replay case: %v", err)
			}
			if transcript.CaseID != replay.ReplayCaseID {
				t.Fatalf("case id mismatch: got %q want %q", transcript.CaseID, replay.ReplayCaseID)
			}
			if len(transcript.Events) == 0 {
				t.Fatalf("expected non-empty stream transcript")
			}
			assertReplayGoldenEvents(t, replay, transcript.Events)
			if replay.ExpectedRunResponse.Status == "failed" && transcript.Failure == nil {
				t.Fatalf("expected runtime failure for failed replay")
			}
		})
	}
}

func assertReplayGoldenEvents(t *testing.T, replay assistant.ReplayCase, events []streaming.Envelope) {
	t.Helper()
	if events[0].EventType != string(app.AssistantStreamEventRunStarted) {
		t.Fatalf(
			"replay %s first event=%q, want %q",
			replay.ReplayCaseID,
			events[0].EventType,
			app.AssistantStreamEventRunStarted,
		)
	}
	validTypes := map[string]bool{
		string(app.AssistantStreamEventRunStarted):     true,
		string(app.AssistantStreamEventProcessReplace): true,
		string(app.AssistantStreamEventProcessAppend):  true,
		string(app.AssistantStreamEventProcessCommit):  true,
		string(app.AssistantStreamEventAnswerDelta):    true,
		string(app.AssistantStreamEventCompleted):      true,
		string(app.AssistantStreamEventFailed):         true,
		string(app.AssistantStreamEventCancelled):      true,
	}
	seenReplace := false
	terminalCount := 0
	wantTerminal := string(app.AssistantStreamEventCompleted)
	if replay.ExpectedRunResponse.Status == "failed" {
		wantTerminal = string(app.AssistantStreamEventFailed)
	}
	for _, event := range events {
		if !validTypes[event.EventType] {
			t.Fatalf(
				"replay %s emitted non-canonical event type %q",
				replay.ReplayCaseID,
				event.EventType,
			)
		}
		if event.EventType == string(app.AssistantStreamEventProcessReplace) {
			seenReplace = true
		}
		if event.EventType == string(app.AssistantStreamEventCompleted) ||
			event.EventType == string(app.AssistantStreamEventFailed) ||
			event.EventType == string(app.AssistantStreamEventCancelled) {
			terminalCount++
			if event.EventType != wantTerminal {
				t.Fatalf(
					"replay %s terminal=%q, want %q",
					replay.ReplayCaseID,
					event.EventType,
					wantTerminal,
				)
			}
		}
	}
	if !seenReplace {
		t.Fatalf("replay %s missing process_replace", replay.ReplayCaseID)
	}
	if terminalCount != 1 {
		t.Fatalf("replay %s terminal events=%d, want 1", replay.ReplayCaseID, terminalCount)
	}
	if len(replay.ExpectedStreamEvents) == 0 {
		return
	}
	cursor := 0
	for _, expected := range replay.ExpectedStreamEvents {
		want, _ := expected["eventType"].(string)
		if want == "" {
			continue
		}
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
			t.Fatalf("replay %s missing expected eventType %q in actual stream", replay.ReplayCaseID, want)
		}
	}
}
