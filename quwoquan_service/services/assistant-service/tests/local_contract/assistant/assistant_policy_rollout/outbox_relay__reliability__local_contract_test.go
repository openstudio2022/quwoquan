// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/policy-template-routing/spec.md#gwt-001
package assistant_policy_rollout_test

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"sort"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rolloutports "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/domain/ports"
	rolloutmessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/infrastructure/messaging"
)

type rolloutOutboxFixture struct {
	event         rolloutports.OutboxEvent
	marked        int
	scheduled     int
	nextAttemptAt time.Time
	failureCode   string
}

func (fixture *rolloutOutboxFixture) ClaimPendingOutbox(
	_ context.Context, _ string, now time.Time, _ time.Duration,
) (rolloutports.OutboxEvent, bool, error) {
	if fixture.marked > 0 || (!fixture.nextAttemptAt.IsZero() && now.Before(fixture.nextAttemptAt)) {
		return rolloutports.OutboxEvent{}, false, nil
	}
	return fixture.event, true, nil
}

func (fixture *rolloutOutboxFixture) MarkOutboxPublished(
	context.Context, string, string, string, time.Time,
) error {
	fixture.marked++
	return nil
}

func (fixture *rolloutOutboxFixture) ScheduleOutboxRetry(
	_ context.Context, _ string, _ string, _ time.Time,
	nextAttemptAt time.Time, failureCode string,
) error {
	fixture.scheduled++
	fixture.nextAttemptAt = nextAttemptAt
	fixture.failureCode = failureCode
	return nil
}

type rolloutTransportFixture struct {
	fail      bool
	message   runtimemessaging.DurableMessage
	retention time.Duration
}

func (fixture *rolloutTransportFixture) AppendDurable(
	_ context.Context,
	message runtimemessaging.DurableMessage,
) (string, error) {
	if fixture.fail {
		return "", errors.New("transport unavailable")
	}
	fixture.message = message
	return "stream-1", nil
}

func (fixture *rolloutTransportFixture) SetDurableRetention(
	_ context.Context,
	_ string,
	retention time.Duration,
) error {
	fixture.retention = retention
	return nil
}

func TestPolicyRolloutRelayOnlyAcknowledgesDurableHandoff(t *testing.T) {
	now := time.Date(2026, 8, 5, 13, 0, 0, 0, time.UTC)
	clock := now
	store := &rolloutOutboxFixture{event: rolloutports.OutboxEvent{
		EventID: "rollout-1:2", EventType: "AssistantPolicyRolloutActivated",
		AggregateID: "assistant-default", AggregateVersion: 2, AttemptCount: 1,
		Payload:    []byte(`{"policyId":"assistant-default","revision":2,"status":"active","assignments":[{"cohort":"all","releaseDigest":"sha256:dda18a0e21ae47c53b4309434cbc02ae8bf764fa83a6defbb719431242722aa7"}],"activatedAt":"2026-08-05T13:00:00Z"}`),
		OccurredAt: now,
	}}
	transport := &rolloutTransportFixture{fail: true}
	relay, err := rolloutmessaging.NewOutboxRelay(
		store, transport, time.Second, 1, nil,
		rolloutmessaging.WithRelayClock(func() time.Time { return clock }),
	)
	if err != nil {
		t.Fatalf("NewOutboxRelay() error = %v", err)
	}
	if count, err := relay.FlushOnce(t.Context()); err == nil || count != 0 {
		t.Fatalf("failed FlushOnce() = (%d, %v), want (0, error)", count, err)
	}
	if store.marked != 0 || store.scheduled != 1 ||
		store.nextAttemptAt != now.Add(time.Second) || store.failureCode != "publish_failed" {
		t.Fatalf("failed handoff state = %+v, want persisted one-second retry", store)
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
	if store.marked != 1 || transport.message.Stream != rolloutmessaging.PolicyRolloutAuditStream ||
		fields["eventName"] != "AssistantPolicyRolloutActivated" ||
		fields["aggregateRevision"] != "2" || transport.retention <= 0 {
		t.Fatalf("rollout delivery mismatch: marked=%d stream=%q fields=%v retention=%s",
			store.marked, transport.message.Stream, fields, transport.retention)
	}
	var payload map[string]any
	if err := json.Unmarshal([]byte(fields["payload"]), &payload); err != nil {
		t.Fatalf("decode payload: %v", err)
	}
	wantKeys := []string{"activatedAt", "assignments", "policyId", "revision", "status"}
	gotKeys := make([]string, 0, len(payload))
	for key := range payload {
		gotKeys = append(gotKeys, key)
	}
	sort.Strings(gotKeys)
	if !reflect.DeepEqual(gotKeys, wantKeys) || payload["policyId"] != "assistant-default" ||
		payload["revision"] != float64(2) || payload["status"] != "active" ||
		payload["activatedAt"] != "2026-08-05T13:00:00Z" {
		t.Fatalf("strict rollout payload mismatch: keys=%v payload=%v", gotKeys, payload)
	}
}

func TestPolicyRolloutRetryBackoffIsCapped(t *testing.T) {
	now := time.Date(2026, 8, 5, 14, 0, 0, 0, time.UTC)
	store := &rolloutOutboxFixture{event: rolloutports.OutboxEvent{
		EventID: "rollout-1:99", EventType: "AssistantPolicyRolloutActivated",
		AggregateID: "assistant-default", AggregateVersion: 99, AttemptCount: 99,
		Payload:    []byte(`{"policyId":"assistant-default","revision":99,"status":"active","assignments":[{"cohort":"all","releaseDigest":"sha256:dda18a0e21ae47c53b4309434cbc02ae8bf764fa83a6defbb719431242722aa7"}],"activatedAt":"2026-08-05T14:00:00Z"}`),
		OccurredAt: now,
	}}
	transport := &rolloutTransportFixture{fail: true}
	relay, err := rolloutmessaging.NewOutboxRelay(
		store, transport, time.Second, 1, nil,
		rolloutmessaging.WithRelayClock(func() time.Time { return now }),
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := relay.FlushOnce(t.Context()); err == nil {
		t.Fatal("FlushOnce() error = nil, want transport failure")
	}
	if store.nextAttemptAt != now.Add(32*time.Second) {
		t.Fatalf("capped retry = %s, want %s", store.nextAttemptAt, now.Add(32*time.Second))
	}
}

func TestPolicyRolloutRelayRejectsNonCanonicalPayloads(t *testing.T) {
	now := time.Date(2026, 8, 5, 15, 0, 0, 0, time.UTC)
	tests := map[string]string{
		"extra key":        `{"policyId":"assistant-default","revision":2,"status":"active","assignments":[{"cohort":"all","releaseDigest":"digest"}],"activatedAt":"2026-08-05T15:00:00Z","secret":"leak"}`,
		"wrong status":     `{"policyId":"assistant-default","revision":2,"status":"paused","assignments":[{"cohort":"all","releaseDigest":"digest"}],"activatedAt":"2026-08-05T15:00:00Z"}`,
		"null assignments": `{"policyId":"assistant-default","revision":2,"status":"active","assignments":null,"activatedAt":"2026-08-05T15:00:00Z"}`,
		"duplicate key":    `{"policyId":"assistant-default","policyId":"assistant-other","revision":2,"status":"active","assignments":[{"cohort":"all","releaseDigest":"digest"}],"activatedAt":"2026-08-05T15:00:00Z"}`,
	}
	for name, payload := range tests {
		t.Run(name, func(t *testing.T) {
			store := &rolloutOutboxFixture{event: rolloutports.OutboxEvent{
				EventID: "rollout-invalid:2", EventType: "AssistantPolicyRolloutActivated",
				AggregateID: "assistant-default", AggregateVersion: 2,
				AttemptCount: 1, Payload: []byte(payload), OccurredAt: now,
			}}
			transport := &rolloutTransportFixture{}
			relay, err := rolloutmessaging.NewOutboxRelay(
				store, transport, time.Second, 1, nil,
				rolloutmessaging.WithRelayClock(func() time.Time { return now }),
			)
			if err != nil {
				t.Fatal(err)
			}
			if count, err := relay.FlushOnce(t.Context()); err == nil || count != 0 {
				t.Fatalf("FlushOnce()=(%d,%v), want fail-closed", count, err)
			}
			if store.scheduled != 1 || store.marked != 0 || transport.message.Stream != "" {
				t.Fatalf("invalid payload escaped relay: store=%+v message=%+v", store, transport.message)
			}
		})
	}
}
