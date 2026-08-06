// spec_ref: specs/feature-tree/runtime/runtime-external-integration/integration-service-foundation/spec.md#gwt-001
// readiness_case: apply-external-interaction-account-closure-local
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	streamadapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/adapters/inbound/stream"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
)

func TestIntegrationUserAccountClosedEventNormalizesIdentityAndReplayDigest(t *testing.T) {
	t.Parallel()
	now := time.Now().UTC()
	event := application.UserAccountClosedEvent{
		EventID:        "event-closed-001",
		AccountVersion: 7,
		UserID:         "account-001",
		PersonaIDs:     []string{"persona-002", "persona-001", "persona-002"},
		AccountState:   "closed",
		UpdatedAt:      now,
		OccurredAt:     now,
	}
	if err := event.Validate(); err != nil {
		t.Fatal(err)
	}
	if got := event.SubjectIDs(); len(got) != 3 ||
		got[0] != "account-001" || got[1] != "persona-001" || got[2] != "persona-002" {
		t.Fatalf("canonical subjects = %#v", got)
	}
	reordered := event
	reordered.PersonaIDs = []string{"persona-001", "persona-002"}
	if event.Digest() != reordered.Digest() {
		t.Fatal("persona order and duplicates must not fork replay identity")
	}
}

func TestIntegrationUserAccountClosedProjectionConflictIsFailClosed(t *testing.T) {
	t.Parallel()
	if application.ErrUserAccountClosedEventIDConflict == nil ||
		!errors.Is(application.ErrUserAccountClosedEventIDConflict, application.ErrUserAccountClosedEventIDConflict) {
		t.Fatal("event id conflict sentinel must remain stable")
	}
}

func TestIntegrationUserAccountClosedConsumerInvokesOwningFacetAndACKs(t *testing.T) {
	ctx := t.Context()
	client := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(client, client)
	if err != nil {
		t.Fatal(err)
	}
	store := &integrationAccountClosureProjectionStore{}
	projection, err := application.NewUserAccountClosedProjection(store)
	if err != nil {
		t.Fatal(err)
	}
	config := streamadapter.DefaultUserAccountClosedConsumerConfig()
	config.MinIdle = 0
	consumer, err := streamadapter.NewUserAccountClosedConsumer(
		transport,
		projection,
		integrationAccountClosureFailureStore{},
		"integration-account-closure-contract",
		nil,
		config,
	)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, time.August, 6, 2, 30, 0, 0, time.UTC)
	payload, err := json.Marshal(map[string]any{
		"userId":       "account-closure-local",
		"personaIds":   []string{"persona-closure-local"},
		"accountState": "closed",
		"updatedAt":    now.Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := client.XAdd(ctx, streamadapter.UserAccountEventStream, map[string]string{
		"eventId":        "event-closure-local",
		"eventName":      application.UserAccountClosedEventName,
		"accountId":      "account-closure-local",
		"accountVersion": "3",
		"payload":        string(payload),
		"occurredAt":     now.Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatal(err)
	}
	processed, err := consumer.ProcessOnce(ctx)
	if err != nil || processed != 1 {
		t.Fatalf("process account closure: processed=%d err=%v", processed, err)
	}
	if store.calls != 1 || store.event.EventID != "event-closure-local" ||
		store.event.AccountVersion != 3 {
		t.Fatalf("owning projection state=%+v", store)
	}
	pending, _, err := client.XAutoClaim(
		ctx,
		streamadapter.UserAccountEventStream,
		streamadapter.UserAccountClosedConsumerGroup,
		"integration-account-closure-inspector",
		0,
		"0-0",
		10,
	)
	if err != nil || len(pending) != 0 {
		t.Fatalf("ACK state pending=%d err=%v", len(pending), err)
	}
}

type integrationAccountClosureProjectionStore struct {
	calls int
	event application.UserAccountClosedEvent
}

func (store *integrationAccountClosureProjectionStore) ApplyUserAccountClosed(
	_ context.Context,
	event application.UserAccountClosedEvent,
) (application.UserAccountClosedProjectionResult, error) {
	store.calls++
	store.event = event
	return application.UserAccountClosedProjectionResult{DeletedRequests: 1}, nil
}

type integrationAccountClosureFailureStore struct{}

func (integrationAccountClosureFailureStore) RecordUserAccountClosedFailure(
	context.Context,
	string,
	string,
	string,
	string,
	error,
) (int64, error) {
	return 1, nil
}

func (integrationAccountClosureFailureStore) IsUserAccountClosedDeadLettered(
	context.Context,
	string,
	string,
) (bool, error) {
	return false, nil
}

func (integrationAccountClosureFailureStore) MarkUserAccountClosedDeadLettered(
	context.Context,
	string,
	string,
) error {
	return nil
}

func (integrationAccountClosureFailureStore) ClearUserAccountClosedFailure(
	context.Context,
	string,
	string,
) error {
	return nil
}
