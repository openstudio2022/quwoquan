// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
package connector_invocation_test

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/infrastructure/persistence"
)

func TestConnectorInvocationMongoKeepsPayloadProtectedAndCommitsContinuationAtomically(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "integration_connector_invocation")
	if err != nil {
		t.Fatalf("start real MongoDB replica set: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := runtime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	store := persistence.NewMongoStore(runtime.Database)
	if err := store.EnsureIndexes(startupCtx); err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, time.August, 2, 13, 0, 0, 0, time.UTC)
	command, err := model.NewAcceptCommand(model.AcceptInput{
		InvocationID: "invocation-1", AccountID: "account-1",
		ConnectionID: "connection-1", AssistantRunID: "run-1",
		Capability:      "calendar.event.create",
		PayloadRef:      "protected://artifact/calendar-payload-1",
		ContinuationRef: "continuation-1", IdempotencyKey: "invoke-calendar",
		ConfirmationRequired: true, OccurredAt: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	accepted, err := store.Accept(startupCtx, command)
	if err != nil || accepted.Invocation.Status != model.StatusAwaitingConfirmation {
		t.Fatalf("accept failed: result=%+v err=%v", accepted, err)
	}
	replay, err := store.Accept(startupCtx, command)
	if err != nil || !replay.Replayed || replay.Invocation.InvocationID != "invocation-1" {
		t.Fatalf("accept replay failed: result=%+v err=%v", replay, err)
	}
	var raw bson.M
	if err := runtime.Database.Collection("connector_invocations").FindOne(startupCtx, bson.M{"invocationId": "invocation-1"}).Decode(&raw); err != nil {
		t.Fatal(err)
	}
	if _, leaked := raw["payloadRef"]; leaked {
		t.Fatalf("payloadRef leaked into invocation aggregate: %#v", raw)
	}
	continued, err := store.Continue(startupCtx, model.ContinueInput{
		InvocationID: "invocation-1", AccountID: "account-1",
		ConfirmationRef: "protected://confirmation/1",
		ContinuationRef: "continuation-1", ExpectedRevision: 1,
		IdempotencyKey: "continue-calendar", OccurredAt: now.Add(time.Minute),
	})
	if err != nil || continued.Invocation.Status != model.StatusAccepted ||
		continued.Invocation.Revision != 2 {
		t.Fatalf("continue failed: result=%+v err=%v", continued, err)
	}
	encoded, err := json.Marshal(continued.Invocation)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(encoded), "protected://") {
		t.Fatalf("invocation response leaked protected reference: %s", encoded)
	}
	_, err = store.Continue(startupCtx, model.ContinueInput{
		InvocationID: "invocation-1", AccountID: "account-1",
		ConfirmationRef:  "protected://confirmation/different",
		ExpectedRevision: 1, IdempotencyKey: "continue-calendar",
		OccurredAt: now.Add(2 * time.Minute),
	})
	if !errors.Is(err, model.ErrIdempotencyConflict) {
		t.Fatalf("want continuation idempotency conflict, got %v", err)
	}
	claim, found, err := store.ClaimNext(startupCtx, "worker-1", now.Add(3*time.Minute), time.Minute)
	if err != nil || !found || claim.Invocation.Status != model.StatusExecuting ||
		claim.Invocation.Revision != 3 || claim.Invocation.Attempt != 1 ||
		claim.PayloadRef != "protected://artifact/calendar-payload-1" {
		t.Fatalf("claim failed: claim=%+v found=%v err=%v", claim, found, err)
	}
	_, err = store.Complete(startupCtx, model.CompleteInput{
		InvocationID: "invocation-1", AccountID: "account-1",
		LeaseOwner: "wrong-worker", ExpectedRevision: 3,
		Status:         model.StatusCompleted,
		ResultRef:      "protected://result/calendar-1",
		ResultDigest:   "sha256:1111111111111111111111111111111111111111111111111111111111111111",
		RecoveryAction: "none", OccurredAt: now.Add(4 * time.Minute),
	})
	if !errors.Is(err, model.ErrRevisionConflict) {
		t.Fatalf("wrong lease owner must fail CAS, got %v", err)
	}
	completed, err := store.Complete(startupCtx, model.CompleteInput{
		InvocationID: "invocation-1", AccountID: "account-1",
		LeaseOwner: "worker-1", ExpectedRevision: 3,
		Status:         model.StatusCompleted,
		ResultRef:      "protected://result/calendar-1",
		ResultDigest:   "sha256:1111111111111111111111111111111111111111111111111111111111111111",
		RecoveryAction: "none", OccurredAt: now.Add(4 * time.Minute),
	})
	if err != nil || completed.Invocation.Status != model.StatusCompleted ||
		completed.Invocation.Revision != 4 || completed.Invocation.CompletedAt == nil {
		t.Fatalf("complete failed: result=%+v err=%v", completed, err)
	}
	encoded, err = json.Marshal(completed.Invocation)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(encoded), "protected://") || strings.Contains(string(encoded), "worker-1") {
		t.Fatalf("terminal response leaked protected/lease state: %s", encoded)
	}
	for collection, want := range map[string]int64{
		"connector_invocations":                 1,
		"connector_invocation_payload_refs":     0,
		"connector_invocation_command_receipts": 2,
		"connector_invocation_outbox":           4,
	} {
		count, countErr := runtime.Database.Collection(collection).CountDocuments(startupCtx, bson.M{})
		if countErr != nil || count != want {
			t.Fatalf("%s count=%d want=%d err=%v", collection, count, want, countErr)
		}
	}
}
