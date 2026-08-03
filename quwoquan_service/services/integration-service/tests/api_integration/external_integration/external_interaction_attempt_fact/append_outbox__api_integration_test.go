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

func TestAttemptFactAndResultOutboxCommitAsOneImmutablePacket(t *testing.T) {
	integrationsupport.WithIntegrationMongo(t, func(runtime *integrationsupport.MongoRuntime) {
		runtime.ResetExternalInteraction(t)
		store := runtime.CanonicalExternalStore(t)
		now := time.Now().UTC().Truncate(time.Millisecond)
		record := reliabletask.ProviderAttemptRecord{
			AttemptID:             "attempt-object-api-001",
			RequestID:             "request-object-api-001",
			TaskID:                "task-object-api-001",
			Operation:             reliabletask.ExternalInteractionOperationPush,
			Provider:              "fcm",
			ProviderRequestID:     "provider-object-api-001",
			ProviderRequestDigest: reliabletask.ProviderRequestDigest("provider-object-api-001"),
			LatencyMs:             12,
			Status:                reliabletask.ExternalInteractionStatusSentUnconfirmed,
			RecoveryAction:        "none",
			CreatedAt:             now,
		}
		if _, err := store.RecordProviderAttemptWithResultOutbox(context.Background(), record); err != nil {
			t.Fatalf("append attempt fact and result outbox: %v", err)
		}
		if _, err := store.RecordProviderAttemptWithResultOutbox(context.Background(), record); err != nil {
			t.Fatalf("replay immutable attempt: %v", err)
		}
		for collection, filter := range map[string]bson.M{
			"external_provider_attempt_ledger":   {"_id": record.AttemptID},
			"external_interaction_result_outbox": {"_id": record.AttemptID},
		} {
			count, err := runtime.Database.Collection(collection).CountDocuments(
				context.Background(),
				filter,
			)
			if err != nil || count != 1 {
				t.Fatalf("%s count=%d err=%v, want one immutable row", collection, count, err)
			}
		}
		conflict := record
		conflict.Status = reliabletask.ExternalInteractionStatusFailed
		if _, err := store.RecordProviderAttemptWithResultOutbox(
			context.Background(),
			conflict,
		); err == nil {
			t.Fatal("same attempt identity with different payload must conflict")
		}
	})
}
