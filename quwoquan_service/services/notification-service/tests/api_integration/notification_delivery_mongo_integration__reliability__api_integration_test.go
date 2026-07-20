package api_integration

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/reliabletask"
	httpadapter "quwoquan_service/services/notification-service/internal/adapters/http"
	"quwoquan_service/services/notification-service/internal/application"
	notification "quwoquan_service/services/notification-service/internal/domain/notification"
	integrationclient "quwoquan_service/services/notification-service/internal/infrastructure/integration"
)

type fixedServiceCredential string

func (c fixedServiceCredential) AuthorizationHeader(context.Context) (string, error) {
	return "Bearer " + string(c), nil
}

type integrationRequestSpy struct {
	mu            sync.Mutex
	requests      []map[string]any
	authorization []string
}

func (s *integrationRequestSpy) accept(w http.ResponseWriter, r *http.Request) {
	var body map[string]any
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	s.mu.Lock()
	s.requests = append(s.requests, body)
	s.authorization = append(s.authorization, r.Header.Get("Authorization"))
	s.mu.Unlock()
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"requestId":  body["requestId"],
		"status":     reliabletask.ExternalInteractionStatusAccepted,
		"acceptedAt": time.Now().UTC().Format(time.RFC3339),
	})
}

func (s *integrationRequestSpy) snapshot() ([]map[string]any, []string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	requests := append([]map[string]any(nil), s.requests...)
	authorization := append([]string(nil), s.authorization...)
	return requests, authorization
}

func TestNotificationDeliveryPersistsRecipientLedgerAndSubmitsIntegrationRequest(t *testing.T) {
	resetNotificationCollections(t)
	spy := &integrationRequestSpy{}
	integrationServer := httptest.NewTLSServer(http.HandlerFunc(spy.accept))
	t.Cleanup(integrationServer.Close)

	adapter, err := integrationclient.NewExternalInteractionDeliveryAdapter(
		integrationclient.ExternalInteractionDeliveryConfig{
			BaseURL:     integrationServer.URL,
			Credentials: fixedServiceCredential("service-token"),
			Environment: "gamma",
			Timeout:     2 * time.Second,
		},
		integrationServer.Client(),
	)
	if err != nil {
		t.Fatalf("construct integration delivery adapter: %v", err)
	}
	service, err := application.NewNotificationDeliveryService(
		notificationReliableStore,
		adapter,
		reliabletask.RateLimitPolicy{
			ClaimPerSecond:    100,
			DispatchPerSecond: 100,
			RetryPerSecond:    20,
		},
	)
	if err != nil {
		t.Fatalf("construct notification delivery service: %v", err)
	}
	record := reliabletask.NotificationOutboxRecord{
		NotificationID:        "ndj_real_001",
		SubjectNotificationID: "msg_real_001",
		Channel:               "push",
		DestinationRef:        "user-real-001",
		EventType:             application.NotificationPushRequestedEvent,
		OwnerDomain:           "notification",
		AggregateType:         "NotificationDeliveryJob",
		AggregateID:           "msg_real_001",
		DedupeKey:             "push:msg_real_001",
		Payload: map[string]string{
			"providerHint": "vendor_push",
			"deeplink":     "quwoquan://chat/message-real-001",
		},
		RecipientIDs:  []string{"user-real-001"},
		NextAttemptAt: time.Now().UTC().Add(-time.Second),
	}
	created, err := notificationReliableStore.CreateNotification(context.Background(), record)
	if err != nil {
		t.Fatalf("persist notification outbox: %v", err)
	}
	duplicate, err := notificationReliableStore.CreateNotification(context.Background(), record)
	if err != nil {
		t.Fatalf("persist idempotent notification outbox: %v", err)
	}
	if created.NotificationID != duplicate.NotificationID {
		t.Fatalf("notification dedupe drifted: first=%+v duplicate=%+v", created, duplicate)
	}

	processed, err := service.ProcessOne(context.Background())
	if err != nil {
		t.Fatalf("process notification delivery: %v", err)
	}
	if !processed {
		t.Fatal("expected notification delivery to process one record")
	}
	processed, err = service.ProcessOne(context.Background())
	if err != nil {
		t.Fatalf("process empty notification queue: %v", err)
	}
	if processed {
		t.Fatal("delivered notification must not be processed twice")
	}

	requests, authorization := spy.snapshot()
	if len(requests) != 1 {
		t.Fatalf("integration endpoint must receive exactly one request, got %d", len(requests))
	}
	if authorization[0] != "Bearer service-token" {
		t.Fatalf("service authorization header not injected: %q", authorization[0])
	}
	if requests[0]["operation"] != reliabletask.ExternalInteractionOperationPush {
		t.Fatalf("notification did not submit push operation: %+v", requests[0])
	}
	payload, ok := requests[0]["payload"].(map[string]any)
	if !ok || payload["jobId"] != record.NotificationID ||
		payload["notificationId"] != record.SubjectNotificationID ||
		payload["recipientId"] != record.RecipientIDs[0] {
		t.Fatalf("notification request payload is not traceable: %+v", requests[0])
	}

	var persistedNotification reliabletask.NotificationOutboxRecord
	if err := notificationMongoDB.Collection("notification_delivery_jobs").FindOne(
		context.Background(),
		bson.M{"_id": record.NotificationID},
	).Decode(&persistedNotification); err != nil {
		t.Fatalf("read persisted notification: %v", err)
	}
	if persistedNotification.Status != reliabletask.NotificationStatusSucceeded {
		t.Fatalf("notification status=%q, want succeeded", persistedNotification.Status)
	}
	var ledger reliabletask.NotificationDeliveryLedgerRecord
	if err := notificationMongoDB.Collection("notification_delivery_job_recipients").FindOne(
		context.Background(),
		bson.M{
			"notificationId": record.NotificationID,
			"recipientId":    record.RecipientIDs[0],
		},
	).Decode(&ledger); err != nil {
		t.Fatalf("read recipient delivery ledger: %v", err)
	}
	if ledger.Status != reliabletask.RecipientStatusDelivered || ledger.DeliveredSeq <= 0 {
		t.Fatalf("unexpected delivery ledger: %+v", ledger)
	}
	if count, err := notificationMongoDB.Collection("notification_delivery_jobs_outbox").CountDocuments(
		context.Background(),
		bson.M{"aggregateId": record.NotificationID},
	); err != nil || count != 2 {
		t.Fatalf("created and dispatched events count=%d err=%v", count, err)
	}
}

func TestNotificationDeliveryReturnsStructuredRemoteFailure(t *testing.T) {
	integrationServer := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusServiceUnavailable)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"code":      "INTEGRATION.MIDDLEWARE.provider_rejected",
			"requestId": "upstream-request-503",
			"traceId":   "trace-503",
			"recovery": map[string]any{
				"action": "retry",
			},
		})
	}))
	t.Cleanup(integrationServer.Close)
	adapter, err := integrationclient.NewExternalInteractionDeliveryAdapter(
		integrationclient.ExternalInteractionDeliveryConfig{
			BaseURL:     integrationServer.URL,
			Credentials: fixedServiceCredential("service-token"),
			Environment: "gamma",
			Timeout:     2 * time.Second,
		},
		integrationServer.Client(),
	)
	if err != nil {
		t.Fatalf("construct integration delivery adapter: %v", err)
	}

	_, err = adapter.Deliver(
		context.Background(),
		reliabletask.NotificationOutboxRecord{
			NotificationID: "notification-failure-001",
			EventType:      application.NotificationPushRequestedEvent,
			AggregateType:  "message",
			AggregateID:    "message-failure-001",
			Payload:        map[string]string{"providerHint": "vendor_push"},
		},
		"user-failure-001",
	)
	if err == nil {
		t.Fatal("expected integration rejection")
	}
	var deliveryErr *integrationclient.DeliveryError
	if !errors.As(err, &deliveryErr) {
		t.Fatalf("expected structured DeliveryError, got %T: %v", err, err)
	}
	if deliveryErr.Code != "INTEGRATION.MIDDLEWARE.provider_rejected" ||
		deliveryErr.StatusCode != http.StatusServiceUnavailable ||
		deliveryErr.RecoveryAction != failures.RecoveryActionRetry ||
		deliveryErr.RequestID != "upstream-request-503" ||
		deliveryErr.TraceID != "trace-503" {
		t.Fatalf("unexpected structured delivery failure: %+v", deliveryErr)
	}
}

func TestNotificationDeliveryOperatorFacadesListRecoverAndConvergeMetrics(t *testing.T) {
	resetNotificationCollections(t)
	ctx := context.Background()
	record := reliabletask.NotificationOutboxRecord{
		NotificationID:        "ndj_dead_operator_001",
		SubjectNotificationID: "msg_dead_001",
		Channel:               "push",
		DestinationRef:        "account-operator-target-001",
		EventType:             application.NotificationPushRequestedEvent,
		OwnerDomain:           "notification",
		AggregateType:         "NotificationDeliveryJob",
		AggregateID:           "msg_dead_001",
		DedupeKey:             "push:msg_dead_001",
		RecipientIDs:          []string{"account-operator-target-001"},
		NextAttemptAt:         time.Now().UTC().Add(-time.Minute),
		Version:               1,
		AttemptEpoch:          1,
	}
	if _, err := notificationReliableStore.CreateNotification(ctx, record); err != nil {
		t.Fatalf("create notification outbox: %v", err)
	}
	deadAt := time.Now().UTC().Add(-time.Second)
	if result, err := notificationMongoDB.Collection("notification_delivery_jobs").UpdateOne(
		ctx,
		bson.M{"_id": record.NotificationID},
		bson.M{"$set": bson.M{
			"status":    reliabletask.NotificationStatusDead,
			"attempts":  5,
			"updatedAt": deadAt,
			"lastFailure": bson.M{
				"code":    "INTEGRATION.MIDDLEWARE.provider_rejected",
				"message": "provider rejected",
				"attributes": bson.M{
					"recoveryAction": "surface",
				},
			},
		}},
	); err != nil || result.MatchedCount != 1 {
		t.Fatalf("mark notification dead matched=%d err=%v", result.MatchedCount, err)
	}

	handler := newNotificationOperatorHTTPHandler(t)
	listRecorder := httptest.NewRecorder()
	handler.ServeHTTP(
		listRecorder,
		httptest.NewRequest(
			http.MethodGet,
			"/internal/notifications/delivery-jobs/dead-letters?eventType="+application.NotificationPushRequestedEvent+"&limit=20",
			nil,
		),
	)
	if listRecorder.Code != http.StatusOK {
		t.Fatalf("list dead letters status=%d body=%s", listRecorder.Code, listRecorder.Body.String())
	}
	var deadLetters notification.NotificationDeliveryJobDeadLetterSlice
	if err := json.Unmarshal(listRecorder.Body.Bytes(), &deadLetters); err != nil {
		t.Fatalf("decode dead-letter slice: %v", err)
	}
	if len(deadLetters.Items) != 1 ||
		deadLetters.Items[0].JobID != record.NotificationID ||
		deadLetters.Items[0].NotificationID != record.SubjectNotificationID ||
		deadLetters.Items[0].FailureCode != "INTEGRATION.MIDDLEWARE.provider_rejected" {
		t.Fatalf("unexpected dead-letter slice: %+v", deadLetters)
	}

	metricsBefore := requestNotificationMetrics(t, handler)
	if metricsBefore.DeadJobs != 1 ||
		metricsBefore.JobsByStatus[reliabletask.NotificationStatusDead] != 1 {
		t.Fatalf("metrics before recovery did not expose dead delivery: %+v", metricsBefore)
	}

	recoveryPath := "/internal/notifications/delivery-jobs/" + record.NotificationID + ":recover"
	recoverRecorder := httptest.NewRecorder()
	recoverRequest := httptest.NewRequest(http.MethodPost, recoveryPath, nil)
	recoverRequest.Header.Set("Idempotency-Key", "recover-dead-operator-001")
	handler.ServeHTTP(
		recoverRecorder,
		recoverRequest,
	)
	if recoverRecorder.Code != http.StatusOK {
		t.Fatalf("recover dead letter status=%d body=%s", recoverRecorder.Code, recoverRecorder.Body.String())
	}
	var recovered notification.RecoverNotificationDeliveryJobResult
	if err := json.Unmarshal(recoverRecorder.Body.Bytes(), &recovered); err != nil {
		t.Fatalf("decode recovery result: %v", err)
	}
	if recovered.JobID != record.NotificationID ||
		recovered.NotificationID != record.SubjectNotificationID ||
		recovered.Version != 2 || recovered.AttemptEpoch != 2 ||
		recovered.Replayed || recovered.RecoveredAt.IsZero() {
		t.Fatalf("unexpected recovery result: %+v", recovered)
	}

	metricsAfter := requestNotificationMetrics(t, handler)
	if metricsAfter.DeadJobs != 0 ||
		metricsAfter.JobsByStatus[reliabletask.NotificationStatusPending] != 1 {
		t.Fatalf("metrics after recovery did not converge: %+v", metricsAfter)
	}

	replayRecorder := httptest.NewRecorder()
	replayRequest := httptest.NewRequest(http.MethodPost, recoveryPath, nil)
	replayRequest.Header.Set("Idempotency-Key", "recover-dead-operator-001")
	handler.ServeHTTP(
		replayRecorder,
		replayRequest,
	)
	if replayRecorder.Code != http.StatusOK {
		t.Fatalf("repeated recovery status=%d body=%s", replayRecorder.Code, replayRecorder.Body.String())
	}
	var replayed notification.RecoverNotificationDeliveryJobResult
	if err := json.Unmarshal(replayRecorder.Body.Bytes(), &replayed); err != nil {
		t.Fatalf("decode replayed recovery: %v", err)
	}
	if !replayed.Replayed || replayed.JobID != record.NotificationID || replayed.Version != recovered.Version {
		t.Fatalf("unexpected replayed recovery: %+v", replayed)
	}

	newKeyRecorder := httptest.NewRecorder()
	newKeyRequest := httptest.NewRequest(http.MethodPost, recoveryPath, nil)
	newKeyRequest.Header.Set("Idempotency-Key", "recover-dead-operator-002")
	handler.ServeHTTP(newKeyRecorder, newKeyRequest)
	if newKeyRecorder.Code != http.StatusNotFound {
		t.Fatalf("new-key recovery of non-dead job status=%d body=%s", newKeyRecorder.Code, newKeyRecorder.Body.String())
	}
	var failure rterr.ErrorResponse
	if err := json.Unmarshal(newKeyRecorder.Body.Bytes(), &failure); err != nil {
		t.Fatalf("decode non-dead recovery failure: %v", err)
	}
	if failure.Code != "NOTIFICATION.USER.delivery_not_found" {
		t.Fatalf("repeated recovery stable code=%q", failure.Code)
	}
	removedRouteRecorder := httptest.NewRecorder()
	handler.ServeHTTP(
		removedRouteRecorder,
		httptest.NewRequest(http.MethodPost, "/internal/notifications/dead-letters/"+record.NotificationID+"/recovery", nil),
	)
	if removedRouteRecorder.Code != http.StatusNotFound {
		t.Fatalf("removed recovery route must stay unavailable, status=%d", removedRouteRecorder.Code)
	}
	if count, err := notificationMongoDB.Collection("notification_delivery_jobs_command_receipts").CountDocuments(
		ctx, bson.M{"_id": "recover-dead-operator-001"},
	); err != nil || count != 1 {
		t.Fatalf("recovery receipt count=%d err=%v", count, err)
	}
	if count, err := notificationMongoDB.Collection("notification_delivery_jobs_outbox").CountDocuments(
		ctx, bson.M{"aggregateId": record.NotificationID, "eventType": "NotificationDeliveryJobRecovered"},
	); err != nil || count != 1 {
		t.Fatalf("recovery event count=%d err=%v", count, err)
	}
}

func newNotificationOperatorHTTPHandler(t *testing.T) http.Handler {
	t.Helper()
	appMessageCommands, err := application.NewAppMessageCommandFacade(
		notificationAppMessageStore,
		notificationAppMessageStore,
		notificationReliableStore,
	)
	if err != nil {
		t.Fatalf("construct app message command facade: %v", err)
	}
	appMessageQueries, err := application.NewAppMessageQueryFacade(
		notificationAppMessageStore,
		notificationAppMessageStore,
		notificationAppMessageStore,
	)
	if err != nil {
		t.Fatalf("construct app message query facade: %v", err)
	}
	deliveryQueries, err := application.NewNotificationDeliveryJobQueryFacade(
		notificationReliableStore,
		notificationReliableStore,
	)
	if err != nil {
		t.Fatalf("construct delivery query facade: %v", err)
	}
	deliveryCommands, err := application.NewNotificationDeliveryJobCommandFacade(
		notificationReliableStore,
	)
	if err != nil {
		t.Fatalf("construct delivery command facade: %v", err)
	}
	handler, err := httpadapter.NewHandler(httpadapter.HandlerDependencies{
		AppMessageCommands: appMessageCommands,
		AppMessageQueries:  appMessageQueries,
		DeliveryCommands:   deliveryCommands,
		DeliveryQueries:    deliveryQueries,
		IncomingCalls:      newTestIncomingCallCoordinator(t),
	})
	if err != nil {
		t.Fatalf("construct notification handler: %v", err)
	}
	return handler.Routes()
}

func requestNotificationMetrics(
	t *testing.T,
	handler http.Handler,
) notification.NotificationDeliveryJobMetricsSnapshot {
	t.Helper()
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(
		recorder,
		httptest.NewRequest(
			http.MethodGet,
			"/internal/notifications/delivery-jobs/metrics",
			nil,
		),
	)
	if recorder.Code != http.StatusOK {
		t.Fatalf("read notification metrics status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var snapshot notification.NotificationDeliveryJobMetricsSnapshot
	if err := json.Unmarshal(recorder.Body.Bytes(), &snapshot); err != nil {
		t.Fatalf("decode notification metrics: %v", err)
	}
	return snapshot
}
