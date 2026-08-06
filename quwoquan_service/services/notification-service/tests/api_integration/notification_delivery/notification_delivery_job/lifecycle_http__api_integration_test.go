// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/chat-offline-push-delivery/spec.md#gwt-002
// readiness_case: get-notification-delivery-job-metrics-api
// readiness_case: list-notification-delivery-job-dead-letters-api
// readiness_case: recover-notification-delivery-job-api
package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/reliabletask"
	deliveryhttp "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/adapters/inbound/http"
	deliveryapplication "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
	deliverydomain "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/domain"
	deliverypersistence "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/infrastructure/persistence"
)

type unrestrictedSubjects struct{}

func (unrestrictedSubjects) RestrictedSubjects(
	context.Context,
	[]string,
) (map[string]bool, error) {
	return map[string]bool{}, nil
}

func TestDeliveryJobDeadLetterAndRecoveryUseOneAtomicAggregatePacket(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(
		ctx,
		fmt.Sprintf("notification_delivery_job_%d", time.Now().UnixNano()),
	)
	if err != nil {
		t.Fatalf("start real notification MongoDB: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cleanupCancel()
		if err := runtime.Close(cleanupCtx); err != nil {
			t.Errorf("close notification MongoDB: %v", err)
		}
	})
	store := deliverypersistence.NewMongoNotificationDeliveryJobStore(
		runtime.Database,
		unrestrictedSubjects{},
	)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure NotificationDeliveryJob indexes: %v", err)
	}
	now := time.Now().UTC().Truncate(time.Millisecond)
	created, err := store.CreateNotification(ctx, reliabletask.NotificationOutboxRecord{
		NotificationID:        "ndj-object-api-001",
		SubjectNotificationID: "notification-object-api-001",
		Channel:               "push",
		DestinationRef:        "account-object-api-001",
		EventType:             "NotificationPushRequested",
		OwnerDomain:           "notification",
		AggregateType:         "NotificationDeliveryJob",
		AggregateID:           "notification-object-api-001",
		DedupeKey:             "push:notification-object-api-001",
		RecipientIDs:          []string{"account-object-api-001"},
		NextAttemptAt:         now.Add(-time.Second),
	})
	if err != nil {
		t.Fatalf("create NotificationDeliveryJob: %v", err)
	}
	claimed, err := store.ClaimNotification(
		ctx,
		[]string{created.EventType},
		"notification-object-api-worker",
		time.Minute,
		now,
	)
	if err != nil || claimed == nil {
		t.Fatalf("claim NotificationDeliveryJob=%#v err=%v", claimed, err)
	}
	if err := store.RetryNotification(
		ctx,
		claimed.NotificationID,
		claimed.LeaseToken,
		reliabletask.RuntimeFailure{
			Code:    "INTEGRATION.MIDDLEWARE.provider_rejected",
			Message: "provider rejected canonical request",
			Attributes: map[string]string{
				"recoveryAction": "manual_recover",
			},
		},
		reliabletask.RetryPolicy{MaxAttempts: 1},
		now,
	); err != nil {
		t.Fatalf("move NotificationDeliveryJob to dead-letter: %v", err)
	}
	queries, err := deliveryapplication.NewNotificationDeliveryJobQueryFacade(store, store)
	if err != nil {
		t.Fatal(err)
	}
	commands, err := deliveryapplication.NewNotificationDeliveryJobCommandFacade(store)
	if err != nil {
		t.Fatal(err)
	}
	handler, err := deliveryhttp.NewHandler(commands, queries)
	if err != nil {
		t.Fatal(err)
	}
	metricsRecorder := httptest.NewRecorder()
	handler.Routes().ServeHTTP(
		metricsRecorder,
		httptest.NewRequest(
			http.MethodGet,
			"/internal/notifications/delivery-jobs/metrics",
			nil,
		),
	)
	if metricsRecorder.Code != http.StatusOK {
		t.Fatalf("metrics status=%d body=%s", metricsRecorder.Code, metricsRecorder.Body.String())
	}
	var metrics deliverydomain.NotificationDeliveryJobMetricsSnapshot
	if err := json.Unmarshal(metricsRecorder.Body.Bytes(), &metrics); err != nil ||
		metrics.DeadJobs != 1 {
		t.Fatalf("delivery-job metrics=%+v err=%v", metrics, err)
	}

	listRecorder := httptest.NewRecorder()
	handler.Routes().ServeHTTP(
		listRecorder,
		httptest.NewRequest(
			http.MethodGet,
			"/internal/notifications/delivery-jobs/dead-letters?eventType="+created.EventType,
			nil,
		),
	)
	if listRecorder.Code != http.StatusOK {
		t.Fatalf("list dead letters status=%d body=%s", listRecorder.Code, listRecorder.Body.String())
	}
	var slice deliverydomain.NotificationDeliveryJobDeadLetterSlice
	if err := json.Unmarshal(listRecorder.Body.Bytes(), &slice); err != nil ||
		len(slice.Items) != 1 || slice.Items[0].JobID != created.NotificationID {
		t.Fatalf("dead-letter slice=%#v err=%v", slice, err)
	}

	recoveryPath := "/internal/notifications/delivery-jobs/" + created.NotificationID + ":recover"
	for attempt := 0; attempt < 2; attempt++ {
		recorder := httptest.NewRecorder()
		request := httptest.NewRequest(http.MethodPost, recoveryPath, nil)
		request.Header.Set("Idempotency-Key", "recover-ndj-object-api-001")
		handler.Routes().ServeHTTP(recorder, request)
		if recorder.Code != http.StatusOK {
			t.Fatalf("recover attempt=%d status=%d body=%s", attempt, recorder.Code, recorder.Body.String())
		}
		var result deliverydomain.RecoverNotificationDeliveryJobResult
		if err := json.Unmarshal(recorder.Body.Bytes(), &result); err != nil {
			t.Fatal(err)
		}
		if result.JobID != created.NotificationID || result.Replayed != (attempt == 1) {
			t.Fatalf("recover attempt=%d result=%#v", attempt, result)
		}
	}
	for collection, filter := range map[string]bson.M{
		"notification_delivery_jobs_command_receipts": {"_id": "recover-ndj-object-api-001"},
		"notification_delivery_jobs_outbox": {
			"aggregateId": created.NotificationID,
			"eventType":   "NotificationDeliveryJobRecovered",
		},
	} {
		count, err := runtime.Database.Collection(collection).CountDocuments(ctx, filter)
		if err != nil || count != 1 {
			t.Fatalf("%s count=%d err=%v, want one", collection, count, err)
		}
	}
}
