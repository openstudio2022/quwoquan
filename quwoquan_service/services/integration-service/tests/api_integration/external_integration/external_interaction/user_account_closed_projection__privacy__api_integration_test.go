package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
	interactionpersistence "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/persistence"
	attemptpersistence "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_attempt_fact/infrastructure/persistence"
)

func TestIntegrationUserAccountClosedDeletesOwnedRequestsDeadLettersAndAttempts(t *testing.T) {
	resetReliableTaskCollections(t)
	ctx := context.Background()
	attemptClosure, err := attemptpersistence.NewMongoSubjectClosure(integrationMongoDB)
	if err != nil {
		t.Fatal(err)
	}
	projection, err := interactionpersistence.NewMongoUserAccountClosedProjection(
		integrationMongoDB,
		attemptClosure,
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := attemptClosure.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	if err := projection.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}

	now := time.Now().UTC()
	closedSubject := "persona-closed-001"
	subjectDigest := reliabletask.ExternalInteractionSubjectDigest(
		map[string]string{"subjectId": closedSubject},
	)
	requestID := "request-closed-001"
	taskID := "task-closed-001"
	for collection, document := range map[string]any{
		"reliable_task_outbox": bson.M{
			"_id":         "outbox-closed-001",
			"aggregateId": requestID,
			"payload": bson.M{
				"requestId":       requestID,
				"targetPersonaId": closedSubject,
			},
		},
		"reliable_async_task": bson.M{
			"_id":         taskID,
			"aggregateId": requestID,
			"status":      reliabletask.TaskStatusDead,
			"payload": bson.M{
				"requestId":       requestID,
				"targetPersonaId": closedSubject,
			},
		},
		"external_provider_attempt_ledger": bson.M{
			"_id":           "attempt-closed-001",
			"requestId":     requestID,
			"taskId":        taskID,
			"subjectDigest": subjectDigest,
			"operation":     reliabletask.ExternalInteractionOperationPush,
			"provider":      "fcm",
			"status":        reliabletask.ExternalInteractionStatusFailed,
			"createdAt":     now,
		},
		"external_interaction_result_outbox": bson.M{
			"_id":            "attempt-closed-001",
			"requestId":      requestID,
			"subjectDigest":  subjectDigest,
			"deliveryStatus": reliabletask.ExternalInteractionResultOutboxPending,
			"createdAt":      now,
		},
		"reliable_task_recovery_receipts": bson.M{
			"_id":    "recovery-closed-001",
			"taskId": taskID,
		},
	} {
		if _, err := integrationMongoDB.Collection(collection).InsertOne(ctx, document); err != nil {
			t.Fatalf("seed %s: %v", collection, err)
		}
	}
	if _, err := integrationMongoDB.Collection("external_provider_attempt_ledger").InsertOne(
		ctx,
		bson.M{
			"_id":           "attempt-unrelated",
			"requestId":     "request-unrelated",
			"taskId":        "task-unrelated",
			"subjectDigest": reliabletask.ExternalInteractionSubjectDigest(map[string]string{"subjectId": "persona-unrelated"}),
			"operation":     reliabletask.ExternalInteractionOperationPush,
			"provider":      "fcm",
			"status":        reliabletask.ExternalInteractionStatusSentUnconfirmed,
			"createdAt":     now,
		},
	); err != nil {
		t.Fatal(err)
	}

	event := application.UserAccountClosedEvent{
		EventID:        "event-closed-001",
		AccountVersion: 9,
		UserID:         "account-closed-001",
		PersonaIDs:     []string{closedSubject},
		AccountState:   "closed",
		UpdatedAt:      now,
		OccurredAt:     now,
	}
	result, err := projection.ApplyUserAccountClosed(ctx, event)
	if err != nil {
		t.Fatal(err)
	}
	if result.DeletedRequests != 1 || result.DeletedTasks != 1 ||
		result.DeletedAttempts != 1 || result.DeletedResultOutboxes != 1 ||
		result.DeletedRecoveryRecords != 1 {
		t.Fatalf("unexpected integration account closure result: %+v", result)
	}
	for _, collection := range []string{
		"reliable_task_outbox",
		"reliable_async_task",
		"external_interaction_result_outbox",
		"reliable_task_recovery_receipts",
	} {
		count, err := integrationMongoDB.Collection(collection).CountDocuments(ctx, bson.M{})
		if err != nil || count != 0 {
			t.Fatalf("closed-subject %s remaining=%d err=%v", collection, count, err)
		}
	}
	count, err := integrationMongoDB.Collection("external_provider_attempt_ledger").CountDocuments(ctx, bson.M{})
	if err != nil || count != 1 {
		t.Fatalf("provider attempt isolation count=%d err=%v", count, err)
	}
	replayed, err := projection.ApplyUserAccountClosed(ctx, event)
	if err != nil || !replayed.Replayed {
		t.Fatalf("account closure replay=%+v err=%v", replayed, err)
	}
}
