// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-stream-protocol/spec.md#gwt-001
package local_contract

import (
	"context"
	"fmt"
	"testing"
	"time"

	"quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/persistence"
)

func TestAssistantRunEventStoreAcceptsOnlyOneContiguousEventLog(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	store := persistence.NewMemoryConversationRunStore()
	const runID = "run-sequence-contract"
	first := assistantRunSequenceEvent(runID, 1, "first")

	if err := store.AppendRunEvent(ctx, runID, first); err != nil {
		t.Fatalf("append first event: %v", err)
	}
	if err := store.AppendRunEvent(ctx, runID, first); err != nil {
		t.Fatalf("replay of identical event must be idempotent: %v", err)
	}

	divergentReplay := assistantRunSequenceEvent(runID, 1, "different")
	if err := store.AppendRunEvent(ctx, runID, divergentReplay); err == nil {
		t.Fatal("divergent replay must be rejected")
	}
	if err := store.AppendRunEvent(
		ctx,
		runID,
		assistantRunSequenceEvent(runID, 3, "skipped"),
	); err == nil {
		t.Fatal("sequence gap must be rejected")
	}
	if err := store.AppendRunEvent(
		ctx,
		runID,
		assistantRunSequenceEvent(runID, 0, "zero"),
	); err == nil {
		t.Fatal("zero sequence must be rejected")
	}
	second := assistantRunSequenceEvent(runID, 2, "second")
	if err := store.AppendRunEvent(ctx, runID, second); err != nil {
		t.Fatalf("append contiguous second event: %v", err)
	}

	events, err := store.ListRunEvents(ctx, runID, 0, 10)
	if err != nil {
		t.Fatalf("list contiguous events: %v", err)
	}
	if len(events) != 2 || events[0].Seq != 1 || events[1].Seq != 2 {
		t.Fatalf("stored sequence = %#v, want seq [1, 2]", events)
	}
}

func assistantRunSequenceEvent(
	runID string,
	seq uint64,
	text string,
) streaming.Envelope {
	eventType := "process_append"
	return streaming.Envelope{
		EventID:   fmt.Sprintf("%s:%d", runID, seq),
		StreamID:  runID,
		Event:     eventType,
		EventType: eventType,
		Seq:       seq,
		Payload: map[string]any{
			"text": text,
		},
		CreatedAt: time.Date(2026, 7, 24, 0, 0, int(seq), 0, time.UTC),
	}
}
