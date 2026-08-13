// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-stream-protocol/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-stream-protocol/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-stream-protocol/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-stream-protocol/spec.md#gwt-001.t3
// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-stream-protocol/spec.md#gwt-001.t4
package local_contract

import (
	"context"
	"path/filepath"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/replay"
	"testing"
	"time"

	"quwoquan_service/runtime/streaming"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/streaming"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/tests/support/promptassets"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

func TestRunner_RunReplayCases(t *testing.T) {
	catalog, err := skillfixture.Load()
	if err != nil {
		t.Fatalf("load production skill catalog: %v", err)
	}
	promptResolver := promptassets.MustResolver(t)
	fixtures := []string{
		"replay_direct_answer_min.json",
		"replay_tool_search_min.json",
		"replay_tool_failure_min.json",
	}
	for _, fixture := range fixtures {
		t.Run(fixture, func(t *testing.T) {
			replay, err := LoadCase(filepath.Join("../../../support/contract_fixtures", fixture))
			if err != nil {
				t.Fatalf("load replay case: %v", err)
			}
			transcript, err := (Runner{
				Catalog:      catalog,
				PromptAssets: promptResolver,
				Now: func() time.Time {
					return time.Date(2026, 4, 29, 0, 0, 0, 0, time.UTC)
				},
			}).Run(context.Background(), replay)
			if err != nil {
				t.Fatalf("run replay case: %v", err)
			}
			if transcript.CaseID != replay.ReplayCaseID {
				t.Fatalf("case id mismatch: got %q want %q", transcript.CaseID, replay.ReplayCaseID)
			}
			if len(transcript.Events) == 0 {
				t.Fatalf("expected non-empty stream transcript")
			}
			assistantSessionRunnerAssertReplayGoldenEvents(t, replay, transcript.Events)
			if replay.ExpectedRunResponse.Status == "failed" && transcript.Failure == nil {
				t.Fatalf("expected runtime failure for failed replay")
			}
		})
	}
}

func assistantSessionRunnerAssertReplayGoldenEvents(t *testing.T, replay assistant.ReplayCase, events []streaming.Envelope) {
	t.Helper()
	if events[0].EventType != string(assistantstreaming.AssistantStreamEventRunStarted) {
		t.Fatalf(
			"replay %s first event=%q, want %q",
			replay.ReplayCaseID,
			events[0].EventType,
			assistantstreaming.AssistantStreamEventRunStarted,
		)
	}
	validTypes := map[string]bool{
		string(assistantstreaming.AssistantStreamEventRunStarted):     true,
		string(assistantstreaming.AssistantStreamEventProcessReplace): true,
		string(assistantstreaming.AssistantStreamEventProcessAppend):  true,
		string(assistantstreaming.AssistantStreamEventProcessCommit):  true,
		string(assistantstreaming.AssistantStreamEventAnswerDelta):    true,
		string(assistantstreaming.AssistantStreamEventCompleted):      true,
		string(assistantstreaming.AssistantStreamEventFailed):         true,
		string(assistantstreaming.AssistantStreamEventCancelled):      true,
	}
	seenReplace := false
	terminalCount := 0
	wantTerminal := string(assistantstreaming.AssistantStreamEventCompleted)
	if replay.ExpectedRunResponse.Status == "failed" {
		wantTerminal = string(assistantstreaming.AssistantStreamEventFailed)
	}
	var previousSeq uint64
	for _, event := range events {
		if event.Seq != previousSeq+1 {
			t.Fatalf(
				"replay %s event sequence=%d after %d, want one contiguous ordered log",
				replay.ReplayCaseID,
				event.Seq,
				previousSeq,
			)
		}
		previousSeq = event.Seq
		if !validTypes[event.EventType] {
			t.Fatalf(
				"replay %s emitted non-canonical event type %q",
				replay.ReplayCaseID,
				event.EventType,
			)
		}
		if event.EventType == string(assistantstreaming.AssistantStreamEventProcessReplace) {
			seenReplace = true
		}
		if event.EventType == string(assistantstreaming.AssistantStreamEventCompleted) ||
			event.EventType == string(assistantstreaming.AssistantStreamEventFailed) ||
			event.EventType == string(assistantstreaming.AssistantStreamEventCancelled) {
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
