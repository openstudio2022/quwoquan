// spec_ref: specs/feature-tree/runtime/runtime-external-integration/integration-service-foundation/spec.md#gwt-001
package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/runtime/reliabletask"
	integrationsupport "quwoquan_service/services/integration-service/tests/support"
)

func TestDeadTaskTransitionAtomicallyAppendsImmutableDeadLetterFact(t *testing.T) {
	integrationsupport.WithIntegrationMongo(t, func(runtime *integrationsupport.MongoRuntime) {
		runtime.ResetExternalInteraction(t)
		store := runtime.CanonicalExternalStore(t)
		ctx := context.Background()
		now := time.Now().UTC().Truncate(time.Millisecond)
		outbox, err := store.DeclareTask(ctx, reliabletask.DeclareTaskRequest{
			TaskType:       reliabletask.TaskTypeForExternalInteraction(reliabletask.ExternalInteractionOperationPush),
			OwnerDomain:    "integration",
			AggregateType:  "external_interaction",
			AggregateID:    "request-dead-object-api-001",
			DedupeKey:      "request-dead-object-api-001",
			IdempotencyKey: "request-dead-object-api-001",
			PartitionKey:   "request-dead-object-api-001",
			Payload:        map[string]string{"requestId": "request-dead-object-api-001"},
			PayloadAllow:   []string{"requestId"},
			StartAt:        now.Add(-time.Second),
		})
		if err != nil {
			t.Fatal(err)
		}
		if _, err := store.DispatchDueTasks(ctx, now, 1); err != nil {
			t.Fatal(err)
		}
		task, err := store.ClaimReadyTask(ctx, []string{outbox.TaskType}, "dead-object-api", time.Minute, now)
		if err != nil || task == nil {
			t.Fatalf("claim task=%#v err=%v", task, err)
		}
		if _, err := store.RecordProviderAttempt(ctx, reliabletask.ProviderAttemptRecord{
			AttemptID:             "attempt-dead-object-api-001",
			RequestID:             "request-dead-object-api-001",
			TaskID:                task.TaskID,
			Operation:             reliabletask.ExternalInteractionOperationPush,
			Provider:              "fcm",
			ProviderRequestDigest: reliabletask.ProviderRequestDigest("provider-dead-object-api-001"),
			Status:                reliabletask.ExternalInteractionStatusFailed,
			NormalizedError:       "provider rejected canonical request",
			RecoveryAction:        "manual_recover",
			CreatedAt:             now,
		}); err != nil {
			t.Fatal(err)
		}
		if err := store.FailTask(
			ctx,
			task.TaskID,
			task.LeaseToken,
			reliabletask.RuntimeFailure{Code: "INTEGRATION.MIDDLEWARE.provider_rejected", Message: "provider rejected canonical request"},
			reliabletask.RetryPolicy{MaxAttempts: 1},
			now,
		); err != nil {
			t.Fatal(err)
		}
		facts, err := store.ListExternalInteractionDeadLetterFacts(ctx, "request-dead-object-api-001")
		if err != nil || len(facts) != 1 || facts[0].TaskID != task.TaskID {
			t.Fatalf("dead-letter facts=%#v err=%v", facts, err)
		}
		if _, _, err := store.RecoverDeadTaskIdempotently(
			ctx,
			task.TaskID,
			"recover-dead-object-api-001",
			now.Add(time.Second),
		); err != nil {
			t.Fatal(err)
		}
		count, err := runtime.Database.Collection("external_interaction_dead_letters").
			CountDocuments(ctx, bson.M{"taskId": task.TaskID})
		if err != nil || count != 1 {
			t.Fatalf("immutable dead-letter count=%d err=%v", count, err)
		}
	})
}
