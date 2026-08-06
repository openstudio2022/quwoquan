package api_integration

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/reliabletask"
	streamadapter "quwoquan_service/services/notification-service/internal/notification_delivery/notification/adapters/inbound/stream"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
)

var accountClosureContractTime = time.Date(
	2026,
	time.July,
	20,
	12,
	0,
	0,
	0,
	time.UTC,
)

func newAccountClosureIntegrationConsumer(
	t *testing.T,
	maxAttempts int64,
) *streamadapter.UserAccountClosedConsumer {
	t.Helper()
	config := streamadapter.DefaultUserAccountClosedConsumerConfig()
	config.MinIdle = 0
	config.MaxAttempts = maxAttempts
	transport, err := runtimemessaging.NewRedisMessageTransport(
		notificationRedisClient,
		notificationRedisClient,
	)
	if err != nil {
		t.Fatalf("create message transport: %v", err)
	}
	consumer, err := streamadapter.NewUserAccountClosedConsumer(
		transport,
		notificationClosureFacet,
		notificationAccountClosure,
		"notification-account-closure-integration",
		nil,
		config,
	)
	if err != nil {
		t.Fatalf("create account-closure consumer: %v", err)
	}
	consumer.WithUserAccountRestrictionProjection(notificationRestrictionFacet)
	return consumer
}

func appendAccountClosureIntegrationEvent(
	t *testing.T,
	eventID string,
	userID string,
	personaIDs []string,
) string {
	t.Helper()
	payload, err := json.Marshal(map[string]any{
		"userId":       userID,
		"personaIds":   personaIDs,
		"accountState": "closed",
		"updatedAt":    accountClosureContractTime.Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatalf("marshal UserAccountClosed payload: %v", err)
	}
	messageID, err := notificationRedisClient.XAdd(
		context.Background(),
		streamadapter.UserAccountEventStream,
		map[string]string{
			"eventId":        eventID,
			"eventName":      application.UserAccountClosedEventName,
			"accountId":      userID,
			"accountVersion": "11",
			"payload":        string(payload),
			"occurredAt": accountClosureContractTime.Format(
				time.RFC3339Nano,
			),
		},
	)
	if err != nil {
		t.Fatalf("append UserAccountClosed integration event: %v", err)
	}
	return messageID
}

func seedAccountClosureOwnedData(t *testing.T) {
	t.Helper()
	ctx := context.Background()
	now := accountClosureContractTime
	if _, err := notificationMongoDB.Collection("app_messages").InsertMany(
		ctx,
		[]any{
			bson.M{
				"_id":            "msg-account-owner",
				"idempotencyKey": "idem-account-owner",
				"userId":         "account-owner",
				"destination": bson.M{
					"type": "user",
					"id":   "account-owner",
				},
				"createdAt": now,
			},
			bson.M{
				"_id":            "msg-persona-owner",
				"idempotencyKey": "idem-persona-owner",
				"userId":         "persona-owner",
				"destination": bson.M{
					"type": "user",
					"id":   "persona-owner",
				},
				"createdAt": now,
			},
			bson.M{
				"_id":            "msg-unrelated",
				"idempotencyKey": "idem-unrelated",
				"userId":         "account-unrelated",
				"destination": bson.M{
					"type": "user",
					"id":   "account-unrelated",
				},
				"createdAt": now,
			},
		},
	); err != nil {
		t.Fatalf("seed account-closure app messages: %v", err)
	}
	if _, err := notificationMongoDB.Collection(
		"notification_delivery_jobs",
	).InsertMany(
		ctx,
		[]any{
			bson.M{
				"_id":            "job-account-owner",
				"notificationId": "msg-account-owner",
				"destinationRef": "account-owner",
				"recipientIds":   bson.A{"account-owner"},
				"aggregateId":    "msg-account-owner",
				"dedupeKey":      "dedupe-account-owner",
				"status":         reliabletask.NotificationStatusPending,
				"nextAttemptAt":  now,
				"createdAt":      now,
				"updatedAt":      now,
			},
			bson.M{
				"_id":             "job-persona-owner",
				"notificationId":  "rtc-event-persona-owner",
				"targetPersonaId": "persona-owner",
				"destinationRef":  "endpoint-persona-owner",
				"deviceId":        "device-persona-owner",
				"deliveryKey":     "delivery-persona-owner",
				"dedupeKey":       "dedupe-persona-owner",
				"status":          reliabletask.NotificationStatusPending,
				"nextAttemptAt":   now,
				"createdAt":       now,
				"updatedAt":       now,
			},
			bson.M{
				"_id":            "job-unrelated",
				"notificationId": "msg-unrelated",
				"destinationRef": "account-unrelated",
				"recipientIds":   bson.A{"account-unrelated"},
				"aggregateId":    "msg-unrelated",
				"dedupeKey":      "dedupe-unrelated",
				"status":         reliabletask.NotificationStatusPending,
				"nextAttemptAt":  now,
				"createdAt":      now,
				"updatedAt":      now,
			},
		},
	); err != nil {
		t.Fatalf("seed account-closure delivery jobs: %v", err)
	}
	if _, err := notificationMongoDB.Collection(
		"notification_delivery_job_recipients",
	).InsertMany(
		ctx,
		[]any{
			bson.M{
				"_id":            "ledger-account-owner",
				"notificationId": "job-account-owner",
				"recipientId":    "account-owner",
				"status":         "pending",
				"updatedAt":      now,
			},
			bson.M{
				"_id":            "ledger-unrelated",
				"notificationId": "job-unrelated",
				"recipientId":    "account-unrelated",
				"status":         "pending",
				"updatedAt":      now,
			},
		},
	); err != nil {
		t.Fatalf("seed account-closure recipient projection: %v", err)
	}
	if _, err := notificationMongoDB.Collection(
		"notification_delivery_jobs_outbox",
	).InsertMany(
		ctx,
		[]any{
			bson.M{
				"_id":              "job-account-owner:1:created",
				"aggregateId":      "job-account-owner",
				"aggregateVersion": int64(1),
				"eventType":        "NotificationDeliveryJobCreated",
				"payload": bson.M{
					"jobId":          "job-account-owner",
					"notificationId": "msg-account-owner",
					"status":         "pending",
				},
				"status":    "pending",
				"createdAt": now,
			},
			bson.M{
				"_id":              "job-persona-owner:1:created",
				"aggregateId":      "job-persona-owner",
				"aggregateVersion": int64(1),
				"eventType":        "NotificationDeliveryJobCreated",
				"payload": bson.M{
					"jobId":          "job-persona-owner",
					"notificationId": "rtc-event-persona-owner",
					"callId":         "call-persona-owner",
					"deviceId":       "device-persona-owner",
					"deliveryKey":    "delivery-persona-owner",
					"status":         "pending",
				},
				"status":    "pending",
				"createdAt": now,
			},
		},
	); err != nil {
		t.Fatalf("seed account-closure delivery audit: %v", err)
	}
	if _, err := notificationMongoDB.Collection(
		"notification_delivery_jobs_command_receipts",
	).InsertOne(
		ctx,
		bson.M{
			"_id":           "receipt-account-owner",
			"commandName":   "RecoverNotificationDeliveryJob",
			"commandDigest": "digest-job-account-owner",
			"result": bson.M{
				"jobId":          "job-account-owner",
				"notificationId": "msg-account-owner",
				"version":        int64(2),
				"attemptEpoch":   2,
				"recoveredAt":    now,
			},
			"createdAt": now,
		},
	); err != nil {
		t.Fatalf("seed account-closure command receipt: %v", err)
	}
}

func countAccountClosureDocuments(
	t *testing.T,
	collection string,
	filter bson.M,
) int64 {
	t.Helper()
	count, err := notificationMongoDB.Collection(collection).CountDocuments(
		context.Background(),
		filter,
	)
	if err != nil {
		t.Fatalf("count %s: %v", collection, err)
	}
	return count
}
