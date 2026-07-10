package simulator

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

func TestRunner_RunReplayCases(t *testing.T) {
	fixtures := []string{
		"replay_direct_answer_min.json",
		"replay_tool_search_min.json",
		"replay_tool_failure_min.json",
		"replay_device_action_proposal_min.json",
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
