package local_contract

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
	pushapp "quwoquan_service/services/integration-service/internal/external_integration/push_delivery/application"
	integrationsupport "quwoquan_service/services/integration-service/tests/support"
)

func TestExternalInteractionDeadLetterUsesCanonicalTaskAndAttemptFacts(t *testing.T) {
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	store := integrationsupport.NewMemoryExternalStore(reliabletask.NewMemoryStore())
	service, err := application.NewExternalInteractionService(
		store,
		map[string]reliabletask.ExternalProvider{
			"push_dispatch": pushapp.LocalRecorderPushProvider{},
		},
		map[string]reliabletask.ProviderPolicy{
			reliabletask.ExternalInteractionOperationPush: {
				Providers:   []string{"push_dispatch"},
				Timeout:     time.Second,
				RetryPolicy: reliabletask.RetryPolicy{MaxAttempts: 1},
			},
		},
	)
	if err != nil {
		t.Fatalf("create external interaction service: %v", err)
	}
	record, err := store.DeclareTask(ctx, reliabletask.DeclareTaskRequest{
		TaskType:       reliabletask.TaskTypeForExternalInteraction(reliabletask.ExternalInteractionOperationPush),
		OwnerDomain:    "integration",
		AggregateType:  "external_interaction",
		AggregateID:    "request-dead-1",
		DedupeKey:      "request-dead-1",
		IdempotencyKey: "request-dead-1",
		PartitionKey:   "request-dead-1",
		Payload:        map[string]string{"requestId": "request-dead-1"},
		PayloadAllow:   []string{"requestId"},
		StartAt:        now,
	})
	if err != nil {
		t.Fatalf("declare external interaction task: %v", err)
	}
	if _, err := store.DispatchDueTasks(ctx, now, 1); err != nil {
		t.Fatalf("dispatch external interaction task: %v", err)
	}
	task, err := store.ClaimReadyTask(
		ctx,
		[]string{record.TaskType},
		"dead-letter-test-worker",
		time.Second,
		now,
	)
	if err != nil || task == nil {
		t.Fatalf("claim external interaction task: task=%#v err=%v", task, err)
	}
	if _, err := store.RecordProviderAttempt(ctx, reliabletask.ProviderAttemptRecord{
		AttemptID:             "attempt-dead-1",
		RequestID:             "request-dead-1",
		TaskID:                task.TaskID,
		Operation:             reliabletask.ExternalInteractionOperationPush,
		Provider:              "apns_voip",
		ProviderRequestDigest: reliabletask.ProviderRequestDigest("provider-request-dead-1"),
		Status:                reliabletask.ExternalInteractionStatusFailed,
		NormalizedError:       "provider rejected request",
		Retryable:             false,
		RecoveryAction:        "manual_recover",
		CreatedAt:             now,
	}); err != nil {
		t.Fatalf("record provider attempt fact: %v", err)
	}
	if err := store.FailTask(
		ctx,
		task.TaskID,
		task.LeaseToken,
		reliabletask.RuntimeFailure{
			Code:    "INTEGRATION.MIDDLEWARE.provider_rejected",
			Message: "provider rejected request",
		},
		reliabletask.RetryPolicy{MaxAttempts: 1},
		now,
	); err != nil {
		t.Fatalf("dead-letter external interaction task: %v", err)
	}
	deadLetters, err := service.ListDeadLetters(ctx, "request-dead-1")
	if err != nil {
		t.Fatalf("list external interaction dead letters: %v", err)
	}
	if len(deadLetters) != 1 {
		t.Fatalf("dead letters=%#v", deadLetters)
	}
	deadLetter := deadLetters[0]
	if deadLetter.DeadLetterID != "dead-letter-"+task.TaskID ||
		deadLetter.TaskID != task.TaskID ||
		deadLetter.RequestID != "request-dead-1" ||
		deadLetter.Operation != reliabletask.ExternalInteractionOperationPush ||
		deadLetter.Provider != "apns_voip" ||
		deadLetter.FinalError != "provider rejected request" ||
		deadLetter.Retryable ||
		deadLetter.RecoveryAction != "manual_recover" {
		t.Fatalf("non-canonical external interaction dead letter: %#v", deadLetter)
	}
	if err := service.RecoverDeadTask(ctx, task.TaskID, "recover-request-dead-1"); err != nil {
		t.Fatalf("recover external interaction dead letter: %v", err)
	}
	if err := service.RecoverDeadTask(ctx, task.TaskID, "recover-request-dead-1"); err != nil {
		t.Fatalf("replay external interaction dead-letter recovery: %v", err)
	}
	deadLetters, err = service.ListDeadLetters(ctx, "request-dead-1")
	if err != nil || len(deadLetters) != 1 || deadLetters[0] != deadLetter {
		t.Fatalf("immutable dead-letter fact changed after recovery: %#v err=%v", deadLetters, err)
	}
}
