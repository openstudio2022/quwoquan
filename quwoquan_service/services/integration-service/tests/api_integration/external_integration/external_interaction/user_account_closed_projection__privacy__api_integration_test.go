// spec_ref: specs/feature-tree/runtime/runtime-external-integration/integration-service-foundation/spec.md#gwt-001
// readiness_case: apply-external-interaction-account-closure-api
package api_integration

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/reliabletask"
	streamadapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/adapters/inbound/stream"
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
	applicationFacet, err := application.NewUserAccountClosedProjection(projection)
	if err != nil {
		t.Fatal(err)
	}
	redisRuntime, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		t.Fatalf("start real Redis: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := redisRuntime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real Redis: %v", closeErr)
		}
	})
	if err := redisRuntime.FlushDBs(ctx, 0); err != nil {
		t.Fatalf("flush real Redis: %v", err)
	}
	redisRouter := platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode:     "standalone",
				Addr:     redisRuntime.Addr,
				Password: redisRuntime.Password,
				DB:       0,
				TLS:      redisRuntime.TLS,
			},
		},
		DefaultScene: "general",
	})
	t.Cleanup(func() {
		if closeErr := redisRouter.Close(); closeErr != nil {
			t.Errorf("close real Redis router: %v", closeErr)
		}
	})
	redisClient := redisRouter.Scene("general")
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"integration-account-closure-api",
		runtimemessaging.RedisMessageTransportAdapter,
		redisClient,
		redisClient,
	)
	if err != nil {
		t.Fatal(err)
	}
	config := streamadapter.DefaultUserAccountClosedConsumerConfig()
	config.MinIdle = 0
	consumer, err := streamadapter.NewUserAccountClosedConsumer(
		transport,
		applicationFacet,
		projection,
		"integration-account-closure-api",
		nil,
		config,
	)
	if err != nil {
		t.Fatal(err)
	}
	appendIntegrationAccountClosureEvent(t, redisClient, event)
	if processed, err := consumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("process UserAccountClosed: processed=%d err=%v", processed, err)
	}
	pending, _, err := redisClient.XAutoClaim(
		ctx,
		streamadapter.UserAccountEventStream,
		streamadapter.UserAccountClosedConsumerGroup,
		"integration-account-closure-api-inspector",
		0,
		"0-0",
		10,
	)
	if err != nil || len(pending) != 0 {
		t.Fatalf("UserAccountClosed ACK pending=%d err=%v", len(pending), err)
	}
	var inboxReceipt struct {
		DeletedRequests        int64 `bson:"deletedRequests"`
		DeletedTasks           int64 `bson:"deletedTasks"`
		DeletedAttempts        int64 `bson:"deletedAttempts"`
		DeletedResultOutboxes  int64 `bson:"deletedResultOutboxes"`
		DeletedRecoveryRecords int64 `bson:"deletedRecoveryRecords"`
	}
	if err := integrationMongoDB.Collection("integration_user_account_closed_inbox").
		FindOne(ctx, bson.M{"_id": event.EventID}).Decode(&inboxReceipt); err != nil {
		t.Fatalf("read account closure receipt: %v", err)
	}
	if inboxReceipt.DeletedRequests != 1 || inboxReceipt.DeletedTasks != 1 ||
		inboxReceipt.DeletedAttempts != 1 || inboxReceipt.DeletedResultOutboxes != 1 ||
		inboxReceipt.DeletedRecoveryRecords != 1 {
		t.Fatalf("unexpected integration account closure receipt: %+v", inboxReceipt)
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
	appendIntegrationAccountClosureEvent(t, redisClient, event)
	if processed, err := consumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("process UserAccountClosed replay: processed=%d err=%v", processed, err)
	}
	inboxCount, err := integrationMongoDB.Collection("integration_user_account_closed_inbox").
		CountDocuments(ctx, bson.M{"_id": event.EventID})
	if err != nil || inboxCount != 1 {
		t.Fatalf("account closure replay receipt count=%d err=%v", inboxCount, err)
	}
}

func appendIntegrationAccountClosureEvent(
	t *testing.T,
	client rtredis.Client,
	event application.UserAccountClosedEvent,
) string {
	t.Helper()
	payload, err := json.Marshal(map[string]any{
		"userId":       event.UserID,
		"personaIds":   event.PersonaIDs,
		"accountState": event.AccountState,
		"updatedAt":    event.UpdatedAt.UTC().Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatal(err)
	}
	messageID, err := client.XAdd(t.Context(), streamadapter.UserAccountEventStream, map[string]string{
		"eventId":        event.EventID,
		"eventName":      application.UserAccountClosedEventName,
		"accountId":      event.UserID,
		"accountVersion": "9",
		"payload":        string(payload),
		"occurredAt":     event.OccurredAt.UTC().Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatal(err)
	}
	return messageID
}
