// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"sort"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	runmessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/messaging"
)

type terminalOutboxPublicationFixture struct {
	event         runruntime.TerminalEvent
	marked        int
	released      int
	scheduled     int
	nextAttemptAt time.Time
	failureCode   string
}

func (fixture *terminalOutboxPublicationFixture) ClaimPendingTerminalEvents(
	_ context.Context, _ string, now time.Time, _ time.Duration, _ int,
) ([]runruntime.TerminalEvent, error) {
	if fixture.marked > 0 || (!fixture.nextAttemptAt.IsZero() && now.Before(fixture.nextAttemptAt)) {
		return nil, nil
	}
	return []runruntime.TerminalEvent{fixture.event}, nil
}

func (fixture *terminalOutboxPublicationFixture) AcknowledgeTerminalEvent(
	context.Context, string, string, time.Time,
) error {
	fixture.marked++
	return nil
}

func (fixture *terminalOutboxPublicationFixture) ScheduleTerminalEventRetry(
	_ context.Context, _ string, _ string, _ time.Time,
	nextAttemptAt time.Time, failureCode string,
) error {
	fixture.scheduled++
	fixture.nextAttemptAt = nextAttemptAt
	fixture.failureCode = failureCode
	return nil
}

func (fixture *terminalOutboxPublicationFixture) ReleaseTerminalEventClaim(
	context.Context, string, string,
) error {
	fixture.released++
	return nil
}

type terminalTransportFixture struct {
	fail      bool
	message   runtimemessaging.DurableMessage
	retention time.Duration
}

func (fixture *terminalTransportFixture) AppendDurable(
	_ context.Context, message runtimemessaging.DurableMessage,
) (string, error) {
	if fixture.fail {
		return "", errors.New("transport unavailable")
	}
	fixture.message = message
	return "1-0", nil
}

func (fixture *terminalTransportFixture) SetDurableRetention(
	_ context.Context, _ string, retention time.Duration,
) error {
	fixture.retention = retention
	return nil
}

func TestTerminalRelayPublishesCompletedRunBeforeHandlersAndCheckpoint(t *testing.T) {
	now := time.Date(2026, 8, 5, 13, 0, 0, 0, time.UTC)
	clock := now
	tools := []string{"web.search", "map.lookup"}
	modelID := "model-prod-2026-08"
	tokens := int64(123)
	latency := int64(456)
	store := &terminalOutboxPublicationFixture{event: runruntime.TerminalEvent{
		EventID: "run-1:terminal", RunID: "run-1", UserID: "user-1",
		PersonaID: "persona-1", SessionID: "session-1", DomainID: "travel",
		Outcome: "completed", ToolsCalled: &tools, LLMModel: &modelID,
		LLMTokensUsed: &tokens, LatencyMS: &latency, OccurredAt: now,
		AttemptCount: 1,
	}}
	transport := &terminalTransportFixture{fail: true}
	publisher, err := runmessaging.NewTerminalEventPublisher(transport)
	if err != nil {
		t.Fatal(err)
	}
	handled := 0
	relay := runruntime.NewTerminalRunRelay(
		store,
		publisher,
		[]runruntime.TerminalEventHandler{runruntime.TerminalEventHandlerFunc(func(
			context.Context,
			runruntime.TerminalEvent,
		) error {
			handled++
			return nil
		})},
		"terminal-publication-worker",
		time.Second,
		1,
		runruntime.WithTerminalRelayClock(func() time.Time { return clock }),
	)
	if count, err := relay.FlushOnce(t.Context()); err == nil || count != 0 {
		t.Fatalf("failed FlushOnce() = (%d, %v), want (0, error)", count, err)
	}
	if store.marked != 0 || store.scheduled != 1 || store.released != 0 ||
		store.nextAttemptAt != now.Add(time.Second) ||
		store.failureCode != "publish_failed" || handled != 0 {
		t.Fatalf("failed delivery state = %+v handled=%d, want persisted retry", store, handled)
	}
	if count, err := relay.FlushOnce(t.Context()); err != nil || count != 0 {
		t.Fatalf("retry before nextAttemptAt = (%d, %v), want (0, nil)", count, err)
	}
	transport.fail = false
	clock = now.Add(time.Second)
	if count, err := relay.FlushOnce(t.Context()); err != nil || count != 1 {
		t.Fatalf("recovered FlushOnce() = (%d, %v), want (1, nil)", count, err)
	}
	fields := runtimemessaging.DurableFieldMap(transport.message.Fields)
	if store.marked != 1 || handled != 1 || transport.message.Stream != runmessaging.AssistantRunEventStream ||
		fields["eventName"] != "AssistantRunCompleted" || transport.retention <= 0 {
		t.Fatalf("terminal delivery mismatch: marked=%d handled=%d stream=%q fields=%v retention=%s",
			store.marked, handled, transport.message.Stream, fields, transport.retention)
	}
	var payload map[string]any
	if err := json.Unmarshal([]byte(fields["payload"]), &payload); err != nil {
		t.Fatalf("decode completed payload: %v", err)
	}
	gotKeys := make([]string, 0, len(payload))
	for key := range payload {
		gotKeys = append(gotKeys, key)
	}
	sort.Strings(gotKeys)
	wantKeys := []string{
		"_id", "latencyMs", "llmModel", "llmTokensUsed", "personaContextVersion",
		"personaId", "satisfactionScore", "status", "toolsCalled", "userId",
	}
	if !reflect.DeepEqual(gotKeys, wantKeys) || payload["_id"] != "run-1" ||
		payload["userId"] != "user-1" || payload["personaId"] != "persona-1" ||
		payload["status"] != "completed" || payload["llmModel"] != modelID ||
		payload["llmTokensUsed"] != float64(tokens) || payload["latencyMs"] != float64(latency) ||
		payload["personaContextVersion"] != nil || payload["satisfactionScore"] != nil {
		t.Fatalf("strict terminal payload mismatch: keys=%v payload=%v", gotKeys, payload)
	}
	wantTools := []any{"web.search", "map.lookup"}
	if !reflect.DeepEqual(payload["toolsCalled"], wantTools) {
		t.Fatalf("toolsCalled=%v, want %v", payload["toolsCalled"], wantTools)
	}
}

func TestTerminalRelayRetryBackoffIsCapped(t *testing.T) {
	now := time.Date(2026, 8, 5, 14, 0, 0, 0, time.UTC)
	store := &terminalOutboxPublicationFixture{event: runruntime.TerminalEvent{
		EventID: "run-99:terminal", RunID: "run-99", UserID: "user-99",
		PersonaID: "persona-99", Outcome: "completed", OccurredAt: now,
		AttemptCount: 99,
	}}
	transport := &terminalTransportFixture{fail: true}
	publisher, err := runmessaging.NewTerminalEventPublisher(transport)
	if err != nil {
		t.Fatal(err)
	}
	relay := runruntime.NewTerminalRunRelay(
		store, publisher,
		[]runruntime.TerminalEventHandler{runruntime.TerminalEventHandlerFunc(func(
			context.Context, runruntime.TerminalEvent,
		) error {
			return nil
		})},
		"terminal-capped-worker", time.Second, 1,
		runruntime.WithTerminalRelayClock(func() time.Time { return now }),
	)
	if _, err := relay.FlushOnce(t.Context()); err == nil {
		t.Fatal("FlushOnce() error = nil, want transport failure")
	}
	if store.nextAttemptAt != now.Add(32*time.Second) {
		t.Fatalf("capped retry=%s, want %s", store.nextAttemptAt, now.Add(32*time.Second))
	}
}
