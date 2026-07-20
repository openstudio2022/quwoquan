package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	streamadapter "quwoquan_service/services/notification-service/internal/adapters/stream"
	"quwoquan_service/services/notification-service/internal/application"
	"quwoquan_service/services/notification-service/internal/infrastructure/persistence"
)

func TestUserAccountClosedConsumerAtomicallyCleansOwnedNotificationData(
	t *testing.T,
) {
	resetNotificationCollections(t)
	seedAccountClosureOwnedData(t)
	consumer := newAccountClosureIntegrationConsumer(t, 3)
	appendAccountClosureIntegrationEvent(
		t,
		"evt-account-owner-closed",
		"account-owner",
		[]string{"persona-owner"},
	)

	processed, err := consumer.ProcessOnce(context.Background())
	if err != nil {
		t.Fatalf("process UserAccountClosed integration event: %v", err)
	}
	if processed != 1 {
		t.Fatalf("processed=%d want=1", processed)
	}
	if count := countAccountClosureDocuments(
		t,
		"app_messages",
		bson.M{"_id": bson.M{"$in": bson.A{
			"msg-account-owner",
			"msg-persona-owner",
		}}},
	); count != 0 {
		t.Fatalf("closed-account app messages remaining=%d", count)
	}
	if count := countAccountClosureDocuments(
		t,
		"app_messages",
		bson.M{"_id": "msg-unrelated"},
	); count != 1 {
		t.Fatalf("unrelated app message count=%d want=1", count)
	}
	if count := countAccountClosureDocuments(
		t,
		"notification_delivery_jobs",
		bson.M{"_id": bson.M{"$in": bson.A{
			"job-account-owner",
			"job-persona-owner",
		}}},
	); count != 0 {
		t.Fatalf("closed-account delivery jobs remaining=%d", count)
	}
	if count := countAccountClosureDocuments(
		t,
		"notification_delivery_jobs",
		bson.M{"_id": "job-unrelated"},
	); count != 1 {
		t.Fatalf("unrelated delivery job count=%d want=1", count)
	}
	if count := countAccountClosureDocuments(
		t,
		"notification_delivery_job_recipients",
		bson.M{"recipientId": "account-owner"},
	); count != 0 {
		t.Fatalf("closed-account recipient records remaining=%d", count)
	}

	var outbox struct {
		AggregateID string            `bson:"aggregateId"`
		Payload     map[string]string `bson:"payload"`
	}
	if err := notificationMongoDB.Collection(
		"notification_delivery_jobs_outbox",
	).FindOne(
		context.Background(),
		bson.M{"_id": "job-persona-owner:1:created"},
	).Decode(&outbox); err != nil {
		t.Fatalf("read anonymized delivery outbox: %v", err)
	}
	if outbox.AggregateID == "job-persona-owner" ||
		outbox.Payload["notificationId"] == "rtc-event-persona-owner" ||
		outbox.Payload["callId"] == "call-persona-owner" ||
		outbox.Payload["deviceId"] == "device-persona-owner" ||
		outbox.Payload["deliveryKey"] == "delivery-persona-owner" {
		t.Fatalf("delivery audit retained direct account references: %v", outbox)
	}

	var receipt struct {
		CommandDigest string `bson:"commandDigest"`
		Result        struct {
			JobID          string `bson:"jobId"`
			NotificationID string `bson:"notificationId"`
		} `bson:"result"`
	}
	if err := notificationMongoDB.Collection(
		"notification_delivery_jobs_command_receipts",
	).FindOne(
		context.Background(),
		bson.M{"_id": "receipt-account-owner"},
	).Decode(&receipt); err != nil {
		t.Fatalf("read anonymized command receipt: %v", err)
	}
	if receipt.CommandDigest == "digest-job-account-owner" ||
		receipt.Result.JobID == "job-account-owner" ||
		receipt.Result.NotificationID == "msg-account-owner" {
		t.Fatalf("command receipt retained direct account references: %v", receipt)
	}

	var attempt struct {
		TaskID            string `bson:"taskId"`
		RequestID         string `bson:"requestId"`
		ProviderRequestID string `bson:"providerRequestId"`
		MaskedRecipient   string `bson:"maskedRecipient"`
	}
	if err := notificationMongoDB.Collection(
		"external_provider_attempt_ledger",
	).FindOne(
		context.Background(),
		bson.M{"_id": "attempt-account-owner"},
	).Decode(&attempt); err != nil {
		t.Fatalf("read anonymized provider attempt: %v", err)
	}
	if attempt.TaskID == "job-account-owner" ||
		attempt.RequestID == "request-account-owner" ||
		attempt.ProviderRequestID == "provider-request-owner" ||
		attempt.MaskedRecipient != "" {
		t.Fatalf("provider attempt retained direct account references: %v", attempt)
	}

	var inbox bson.M
	if err := notificationMongoDB.Collection(
		persistence.UserAccountClosedInboxCollection,
	).FindOne(
		context.Background(),
		bson.M{"_id": "evt-account-owner-closed"},
	).Decode(&inbox); err != nil {
		t.Fatalf("read UserAccountClosed inbox: %v", err)
	}
	if inbox["eventDigest"] == "" {
		t.Fatal("UserAccountClosed inbox must retain event digest")
	}
	for _, forbidden := range []string{"userId", "personaIds", "payload"} {
		if _, exists := inbox[forbidden]; exists {
			t.Fatalf(
				"UserAccountClosed inbox must not retain %s: %v",
				forbidden,
				inbox,
			)
		}
	}

	appendAccountClosureIntegrationEvent(
		t,
		"evt-account-owner-closed",
		"account-owner",
		[]string{"persona-owner"},
	)
	if _, err := consumer.ProcessOnce(context.Background()); err != nil {
		t.Fatalf("process UserAccountClosed replay: %v", err)
	}
	if count := countAccountClosureDocuments(
		t,
		persistence.UserAccountClosedInboxCollection,
		bson.M{"_id": "evt-account-owner-closed"},
	); count != 1 {
		t.Fatalf("UserAccountClosed inbox replay count=%d want=1", count)
	}
}

func TestUserAccountClosedConflictStaysPendingThenDLQCanBeRecovered(
	t *testing.T,
) {
	resetNotificationCollections(t)
	firstEvent := application.UserAccountClosedEvent{
		EventID:      "evt-account-conflict",
		UserID:       "account-first",
		PersonaIDs:   []string{},
		AccountState: "closed",
		UpdatedAt:    accountClosureContractTime,
	}
	if _, err := notificationAccountClosure.ApplyUserAccountClosed(
		context.Background(),
		firstEvent,
	); err != nil {
		t.Fatalf("seed first UserAccountClosed inbox record: %v", err)
	}
	if _, err := notificationMongoDB.Collection("app_messages").InsertOne(
		context.Background(),
		bson.M{
			"_id":            "msg-conflicting-account",
			"idempotencyKey": "idem-conflicting-account",
			"userId":         "account-conflicting",
			"destination": bson.M{
				"type": "user",
				"id":   "account-conflicting",
			},
			"createdAt": accountClosureContractTime,
		},
	); err != nil {
		t.Fatalf("seed conflicting account message: %v", err)
	}
	consumer := newAccountClosureIntegrationConsumer(t, 2)
	appendAccountClosureIntegrationEvent(
		t,
		"evt-account-conflict",
		"account-conflicting",
		[]string{},
	)

	if _, err := consumer.ProcessOnce(context.Background()); err == nil {
		t.Fatal("eventId reuse conflict must fail closed")
	}
	pending, _, err := notificationRedisClient.XAutoClaim(
		context.Background(),
		streamadapter.UserAccountEventStream,
		streamadapter.UserAccountClosedConsumerGroup,
		"account-closure-pending-inspector",
		0,
		"0-0",
		10,
	)
	if err != nil {
		t.Fatalf("inspect conflict pending state: %v", err)
	}
	if len(pending) != 1 {
		t.Fatalf("pending conflict messages=%d want=1", len(pending))
	}
	if count := countAccountClosureDocuments(
		t,
		"app_messages",
		bson.M{"_id": "msg-conflicting-account"},
	); count != 1 {
		t.Fatalf("conflict must not clean second account, count=%d", count)
	}
	var failure bson.M
	if err := notificationMongoDB.Collection(
		persistence.UserAccountClosedFailureCollection,
	).FindOne(context.Background(), bson.M{}).Decode(&failure); err != nil {
		t.Fatalf("read UserAccountClosed failure state: %v", err)
	}
	if failure["eventDigest"] == "" || failure["errorDigest"] == "" {
		t.Fatalf("failure state must retain only digests: %v", failure)
	}
	if _, exists := failure["eventId"]; exists {
		t.Fatal("failure state must not retain raw eventId")
	}
	if _, exists := failure["lastError"]; exists {
		t.Fatal("failure state must not retain raw error text")
	}

	if _, err := consumer.ProcessOnce(context.Background()); err != nil {
		t.Fatalf("second conflict attempt should move to DLQ: %v", err)
	}
	pending, _, err = notificationRedisClient.XAutoClaim(
		context.Background(),
		streamadapter.UserAccountEventStream,
		streamadapter.UserAccountClosedConsumerGroup,
		"account-closure-post-dlq-inspector",
		0,
		"0-0",
		10,
	)
	if err != nil {
		t.Fatalf("inspect pending state after DLQ: %v", err)
	}
	if len(pending) != 0 {
		t.Fatalf("pending after DLQ=%d want=0", len(pending))
	}
	if err := notificationRedisClient.XGroupCreateMkStream(
		context.Background(),
		streamadapter.UserAccountClosedDeadLetterStream,
		"account-closure-dlq-recovery",
		"0",
	); err != nil {
		t.Fatalf("create account-closure DLQ recovery group: %v", err)
	}
	deadLetters, err := notificationRedisClient.XReadGroup(
		context.Background(),
		"account-closure-dlq-recovery",
		"recovery",
		map[string]string{
			streamadapter.UserAccountClosedDeadLetterStream: ">",
		},
		10,
		100*time.Millisecond,
	)
	if err != nil {
		t.Fatalf("read account-closure DLQ: %v", err)
	}
	if len(deadLetters) != 1 {
		t.Fatalf("account-closure DLQ entries=%d want=1", len(deadLetters))
	}
	if deadLetters[0].Values["errorDigest"] == "" {
		t.Fatalf("DLQ must retain a non-PII error digest: %v", deadLetters[0].Values)
	}
	if _, exists := deadLetters[0].Values["error"]; exists {
		t.Fatal("DLQ must not retain raw error text")
	}

	recoveryValues := make(map[string]string)
	for _, key := range []string{
		"eventId",
		"eventName",
		"accountId",
		"accountVersion",
		"payload",
		"occurredAt",
	} {
		recoveryValues[key] = deadLetters[0].Values[key]
	}
	recoveryValues["eventId"] = "evt-account-conflict-recovered"
	if _, err := notificationRedisClient.XAdd(
		context.Background(),
		streamadapter.UserAccountEventStream,
		recoveryValues,
	); err != nil {
		t.Fatalf("requeue corrected account-closure event: %v", err)
	}
	if _, err := consumer.ProcessOnce(context.Background()); err != nil {
		t.Fatalf("recover corrected account-closure event: %v", err)
	}
	if count := countAccountClosureDocuments(
		t,
		"app_messages",
		bson.M{"_id": "msg-conflicting-account"},
	); count != 0 {
		t.Fatalf("recovered cleanup left app messages=%d", count)
	}
	if count := countAccountClosureDocuments(
		t,
		persistence.UserAccountClosedInboxCollection,
		bson.M{},
	); count != 2 {
		t.Fatalf("account-closure inbox records=%d want=2", count)
	}
}
