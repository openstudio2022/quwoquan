package api_integration

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	serviceclients "quwoquan_service/generated/serviceclients"
	rtauth "quwoquan_service/runtime/auth"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/runtime/reliabletask"
	httpadapter "quwoquan_service/services/notification-service/internal/notification_delivery/notification/adapters/inbound/http"
	streamadapter "quwoquan_service/services/notification-service/internal/notification_delivery/notification/adapters/inbound/stream"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification/domain"
	integrationclient "quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/integration"
	realtimeclient "quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/realtime"
	userclient "quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/user"
)

func TestRTCIncomingCallCoordinationWithRealMongoAndRedis(t *testing.T) {
	resetNotificationCollections(t)
	now := time.Date(2026, 7, 20, 16, 0, 0, 0, time.UTC)
	personaID := "persona-incoming"
	callID := "51cdbd68-dc62-4728-8953-3cbb6e413c6a"
	deliveryKey := canonicalDeliveryKey(callID, personaID)
	onlineEndpointRef := strings.Repeat("a", 64)
	offlineEndpointRef := strings.Repeat("b", 64)

	userServer := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			expectedPath := serviceclients.
				UserResolveIncomingCallPushDestinationsPath(
					personaID,
				)
			if r.URL.Path != expectedPath {
				http.NotFound(w, r)
				return
			}
			if r.Header.Get("Authorization") != "Bearer service-token" {
				http.Error(w, "missing service credential", http.StatusUnauthorized)
				return
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"destinations": []map[string]string{
					{
						"deviceId":    "device-online",
						"endpointRef": onlineEndpointRef,
					},
					{
						"deviceId":    "device-offline",
						"endpointRef": offlineEndpointRef,
					},
				},
			})
		},
	))
	t.Cleanup(userServer.Close)
	presenceServer := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path !=
				"/internal/realtime/personas/"+personaID+"/presence" {
				http.NotFound(w, r)
				return
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"personaId": personaID,
				"devices": []map[string]string{{
					"accountId": "account-incoming",
					"personaId": personaID,
					"deviceId":  "device-online",
				}},
			})
		},
	))
	t.Cleanup(presenceServer.Close)
	var (
		integrationMu       sync.Mutex
		integrationRequests []map[string]any
	)
	integrationServer := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			var request map[string]any
			if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			integrationMu.Lock()
			integrationRequests = append(integrationRequests, request)
			integrationMu.Unlock()
			w.WriteHeader(http.StatusAccepted)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"requestId":  request["requestId"],
				"status":     reliabletask.ExternalInteractionStatusAccepted,
				"acceptedAt": now.Format(time.RFC3339),
			})
		},
	))
	t.Cleanup(integrationServer.Close)

	pushDestinations, err := userclient.NewPushDestinationClient(
		userclient.PushDestinationClientConfig{
			BaseURL:     userServer.URL,
			Credentials: fixedServiceCredential("service-token"),
			Timeout:     time.Second,
		},
		http.DefaultClient,
	)
	if err != nil {
		t.Fatal(err)
	}
	presenceReader, err := realtimeclient.NewPresenceClient(
		realtimeclient.PresenceClientConfig{
			BaseURL:     presenceServer.URL,
			Credentials: fixedServiceCredential("service-token"),
			Timeout:     time.Second,
		},
		http.DefaultClient,
	)
	if err != nil {
		t.Fatal(err)
	}
	push, err := integrationclient.NewExternalInteractionDeliveryAdapter(
		integrationclient.ExternalInteractionDeliveryConfig{
			BaseURL:     integrationServer.URL,
			Credentials: fixedServiceCredential("service-token"),
			Environment: "gamma",
			Timeout:     time.Second,
		},
		http.DefaultClient,
	)
	if err != nil {
		t.Fatal(err)
	}
	messageTransport, err := runtimemessaging.NewRedisMessageTransport(
		notificationRedisClient,
		notificationRedisClient,
	)
	if err != nil {
		t.Fatal(err)
	}
	realtimePublisher, err := realtimeclient.NewIncomingCallPublisher(
		messageTransport,
	)
	if err != nil {
		t.Fatal(err)
	}
	coordinator, err := application.NewIncomingCallDeliveryCoordinator(
		notificationReliableStore,
		pushDestinations,
		presenceReader,
		realtimePublisher,
		push,
		application.WithIncomingCallClock(func() time.Time { return now }),
	)
	if err != nil {
		t.Fatal(err)
	}
	consumer, err := streamadapter.NewRTCIncomingCallConsumer(
		messageTransport,
		coordinator,
		"incoming-api-integration",
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	subscription, err := notificationRedisClient.Subscribe(
		context.Background(),
		"rt:rtc:persona:"+personaID,
	)
	if err != nil {
		t.Fatal(err)
	}
	defer subscription.Close()

	event := notification.IncomingCallRingingEvent{
		EventID:         "rtc-event-incoming-1",
		CallID:          callID,
		TargetPersonaID: personaID,
		CallType:        "audio",
		CallerName:      "来电者",
		CallerAvatarURL: "https://cdn.example.invalid/caller.png",
		SourceLabel:     "conversation",
		TrustRelation:   "known",
		ExpiresAt:       now.Add(30 * time.Second),
		DeliveryKey:     deliveryKey,
	}
	appendRTCStreamEvent(
		t,
		streamadapter.RTCCallRingingStream,
		"CallRinging",
		event.EventID,
		callID,
		now,
		map[string]any{
			"callId":  callID,
			"payload": event,
		},
	)
	if processed, err := consumer.ProcessOnce(context.Background()); err != nil || processed != 1 {
		t.Fatalf("process CallRinging=%d err=%v", processed, err)
	}
	select {
	case message := <-subscription.Channel():
		var payload map[string]string
		if err := json.Unmarshal([]byte(message.Payload), &payload); err != nil {
			t.Fatal(err)
		}
		if payload["deliveryKey"] != deliveryKey ||
			payload["deviceId"] != "device-online" {
			t.Fatalf("realtime payload=%v", payload)
		}
	case <-time.After(time.Second):
		t.Fatal("online endpoint did not receive realtime dispatch")
	}
	jobs := loadIncomingCallJobs(t, callID)
	if len(jobs) != 2 {
		t.Fatalf("jobs=%+v", jobs)
	}
	assertIncomingStatus(
		t,
		jobs,
		"device-online",
		notification.IncomingCallStatusRealtimeDispatched,
	)
	assertIncomingStatus(
		t,
		jobs,
		"device-offline",
		notification.IncomingCallStatusPushQueued,
	)

	ackHandler := newIncomingCallHTTPHandler(t, coordinator)
	ackBody, _ := json.Marshal(map[string]string{
		"deliveryKey": deliveryKey,
	})
	ackRequest := httptest.NewRequest(
		http.MethodPost,
		"/notifications/incoming-calls/presentation:ack",
		bytes.NewReader(ackBody),
	)
	ackRequest = ackRequest.WithContext(rtauth.WithPrincipal(
		ackRequest.Context(),
		rtauth.Principal{
			Actor: operation.ActorContext{
				AccountID:     "account-different-from-persona",
				PersonaID:     personaID,
				DeviceActorID: "device-online",
			},
		},
	))
	ackRecorder := httptest.NewRecorder()
	ackHandler.ServeHTTP(ackRecorder, ackRequest)
	if ackRecorder.Code != http.StatusOK {
		t.Fatalf(
			"presentation ACK status=%d body=%s",
			ackRecorder.Code,
			ackRecorder.Body.String(),
		)
	}
	var ack notification.AckIncomingCallPresentationResult
	if err := json.Unmarshal(ackRecorder.Body.Bytes(), &ack); err != nil {
		t.Fatal(err)
	}
	if ack.Raced ||
		ack.Status != notification.IncomingCallStatusRealtimePresented {
		t.Fatalf("presentation ACK=%+v", ack)
	}
	if processed, err := coordinator.ProcessDue(context.Background()); err != nil || !processed {
		t.Fatalf("offline push process=%v err=%v", processed, err)
	}
	jobs = loadIncomingCallJobs(t, callID)
	assertIncomingStatus(
		t,
		jobs,
		"device-offline",
		notification.IncomingCallStatusExternalAccepted,
	)
	integrationMu.Lock()
	if len(integrationRequests) != 1 {
		t.Fatalf("integration requests=%d", len(integrationRequests))
	}
	externalRequestID, _ := integrationRequests[0]["requestId"].(string)
	requestPayload, _ := integrationRequests[0]["payload"].(map[string]any)
	integrationMu.Unlock()
	for _, field := range []string{
		"action",
		"endpointRef",
		"deliveryKey",
		"callId",
		"targetPersonaId",
		"callType",
		"callerName",
		"sourceLabel",
		"trustRelation",
		"expiresAt",
		"occurredAt",
	} {
		if _, ok := requestPayload[field]; !ok {
			t.Fatalf("integration payload misses %s: %v", field, requestPayload)
		}
	}
	if requestPayload["action"] != "ring" {
		t.Fatalf("initial integration action=%v", requestPayload["action"])
	}
	providerResult := notification.ExternalInteractionResultEvent{
		AttemptID:             "attempt-incoming-ring-1",
		RequestID:             externalRequestID,
		Operation:             reliabletask.ExternalInteractionOperationPush,
		Status:                reliabletask.ExternalInteractionStatusSentUnconfirmed,
		Provider:              "apns_voip",
		ProviderRequestDigest: "sha256:provider-request",
		RecoveryAction:        "none",
		OccurredAt:            now.Add(500 * time.Millisecond),
	}
	for replay := 0; replay < 2; replay++ {
		if err := notificationReliableStore.ApplyExternalInteractionResult(
			context.Background(),
			providerResult,
			now.Add(time.Second),
		); err != nil {
			t.Fatalf("apply provider result replay=%d: %v", replay, err)
		}
	}
	jobs = loadIncomingCallJobs(t, callID)
	assertIncomingStatus(
		t,
		jobs,
		"device-offline",
		notification.IncomingCallStatusSentUnconfirmed,
	)
	receiptCount, err := notificationMongoDB.Collection(
		"notification_external_interaction_result_inbox",
	).CountDocuments(context.Background(), bson.M{"_id": providerResult.AttemptID})
	if err != nil || receiptCount != 1 {
		t.Fatalf("provider result inbox count=%d err=%v", receiptCount, err)
	}
	timeline, err := notificationReliableStore.ReadIncomingCallDeliveryTimeline(
		context.Background(),
		callID,
	)
	if err != nil || len(timeline.Items) != 2 {
		t.Fatalf("incoming call timeline items=%d err=%v", len(timeline.Items), err)
	}
	if want := now.Add(time.Second).UTC(); !timeline.UpdatedAt.Equal(want) {
		t.Fatalf(
			"incoming call timeline updatedAt=%s want persisted fact time %s",
			timeline.UpdatedAt,
			want,
		)
	}
	timelineJSON, err := json.Marshal(timeline)
	if err != nil {
		t.Fatal(err)
	}
	for _, rawIdentifier := range []string{
		"device-online",
		"device-offline",
		deliveryKey,
		providerResult.AttemptID,
		externalRequestID,
	} {
		if bytes.Contains(timelineJSON, []byte(rawIdentifier)) {
			t.Fatalf("operator timeline leaked raw identifier %q: %s", rawIdentifier, timelineJSON)
		}
	}

	appendRTCStreamEvent(
		t,
		streamadapter.RTCCallRingingStream,
		"CallRinging",
		event.EventID,
		callID,
		now,
		map[string]any{
			"callId":  callID,
			"payload": event,
		},
	)
	if _, err := consumer.ProcessOnce(context.Background()); err != nil {
		t.Fatalf("replay CallRinging: %v", err)
	}
	if jobs = loadIncomingCallJobs(t, callID); len(jobs) != 2 {
		t.Fatalf("replay created duplicate jobs: %+v", jobs)
	}

	appendRTCStreamEvent(
		t,
		streamadapter.RTCCallAnsweredStream,
		"CallAnswered",
		"rtc-event-answered-1",
		callID,
		now.Add(time.Second),
		map[string]any{
			"callId":  callID,
			"actorId": personaID,
			"payload": map[string]any{"callId": callID},
		},
	)
	if _, err := consumer.ProcessOnce(context.Background()); err != nil {
		t.Fatalf("process CallAnswered: %v", err)
	}
	jobs = loadIncomingCallJobs(t, callID)
	for _, job := range jobs {
		if job.Status != notification.IncomingCallStatusCancelled {
			t.Fatalf("cancellation did not converge job: %+v", job)
		}
	}
	lateRingFailure := providerResult
	lateRingFailure.AttemptID = "attempt-incoming-ring-late-failure"
	lateRingFailure.Status = reliabletask.ExternalInteractionStatusFailed
	lateRingFailure.RecoveryAction = "escalate"
	lateRingFailure.OccurredAt = now.Add(2 * time.Second)
	if err := notificationReliableStore.ApplyExternalInteractionResult(
		context.Background(),
		lateRingFailure,
		now.Add(2*time.Second),
	); err != nil {
		t.Fatalf("record late ring provider result: %v", err)
	}
	jobs = loadIncomingCallJobs(t, callID)
	for _, job := range jobs {
		if job.Status != notification.IncomingCallStatusCancelled {
			t.Fatalf("late ring result revived cancelled delivery: %+v", job)
		}
	}
	select {
	case message := <-subscription.Channel():
		var payload map[string]string
		if err := json.Unmarshal([]byte(message.Payload), &payload); err != nil {
			t.Fatal(err)
		}
		if payload["type"] != "call.presentation_cancelled" {
			t.Fatalf("unexpected cancellation payload=%v", payload)
		}
	case <-time.After(time.Second):
		t.Fatal("cancellation did not close incoming call presentation")
	}
	integrationMu.Lock()
	if len(integrationRequests) != 3 {
		integrationMu.Unlock()
		t.Fatalf(
			"ring + two endpoint cancellations requests=%d",
			len(integrationRequests),
		)
	}
	cancelRequestIDs := map[string]struct{}{}
	for _, request := range integrationRequests[1:] {
		payload, _ := request["payload"].(map[string]any)
		if payload["action"] != "cancel" ||
			payload["deliveryKey"] != deliveryKey ||
			payload["occurredAt"] != now.Add(time.Second).Format(time.RFC3339) {
			integrationMu.Unlock()
			t.Fatalf("cancellation integration payload=%v", payload)
		}
		requestID, _ := request["requestId"].(string)
		cancelRequestIDs[requestID] = struct{}{}
	}
	integrationMu.Unlock()
	if len(cancelRequestIDs) != 2 {
		t.Fatalf("endpoint cancellation request IDs=%v", cancelRequestIDs)
	}

	appendRTCStreamEvent(
		t,
		streamadapter.RTCCallAnsweredStream,
		"CallAnswered",
		"rtc-event-answered-1",
		callID,
		now.Add(time.Second),
		map[string]any{
			"callId":  callID,
			"actorId": personaID,
			"payload": map[string]any{"callId": callID},
		},
	)
	if _, err := consumer.ProcessOnce(context.Background()); err != nil {
		t.Fatalf("replay CallAnswered: %v", err)
	}
	select {
	case message := <-subscription.Channel():
		t.Fatalf("cancellation replay emitted duplicate realtime frame: %+v", message)
	case <-time.After(20 * time.Millisecond):
	}
	integrationMu.Lock()
	requestCount := len(integrationRequests)
	integrationMu.Unlock()
	if requestCount != 3 {
		t.Fatalf("cancellation replay duplicated push requests=%d", requestCount)
	}
}

func newTestIncomingCallCoordinator(
	t *testing.T,
) *application.IncomingCallDeliveryCoordinator {
	t.Helper()
	coordinator, err := application.NewIncomingCallDeliveryCoordinator(
		notificationReliableStore,
		emptyPushDestinationReader{},
		emptyPresenceReader{},
		discardIncomingRealtime{},
		acceptedIncomingPush{},
	)
	if err != nil {
		t.Fatalf("construct incoming call coordinator: %v", err)
	}
	return coordinator
}

func newIncomingCallHTTPHandler(
	t *testing.T,
	coordinator *application.IncomingCallDeliveryCoordinator,
) http.Handler {
	t.Helper()
	appCommands, err := application.NewAppMessageCommandFacade(
		notificationAppMessageStore,
		notificationAppMessageStore,
		notificationReliableStore,
	)
	if err != nil {
		t.Fatal(err)
	}
	appQueries, err := application.NewAppMessageQueryFacade(
		notificationAppMessageStore,
		notificationAppMessageStore,
		notificationAppMessageStore,
	)
	if err != nil {
		t.Fatal(err)
	}
	handler, err := httpadapter.NewHandler(
		httpadapter.HandlerDependencies{
			AppMessageCommands: appCommands,
			AppMessageQueries:  appQueries,
			IncomingCalls:      coordinator,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	return handler.Routes()
}

type emptyPushDestinationReader struct{}

func (emptyPushDestinationReader) ListPushDestinations(
	context.Context,
	string,
) ([]notification.PushDestinationRef, error) {
	return nil, nil
}

type emptyPresenceReader struct{}

func (emptyPresenceReader) GetPersonaPresence(
	context.Context,
	string,
) (application.PersonaPresenceView, error) {
	return application.PersonaPresenceView{}, nil
}

type discardIncomingRealtime struct{}

func (discardIncomingRealtime) DispatchIncomingCall(
	context.Context,
	notification.IncomingCallDeliveryJob,
) error {
	return nil
}

func (discardIncomingRealtime) DispatchCancellation(
	context.Context,
	string,
	notification.IncomingCallCancellationEvent,
) error {
	return nil
}

type acceptedIncomingPush struct{}

func (acceptedIncomingPush) SubmitIncomingCall(
	context.Context,
	notification.IncomingCallDeliveryJob,
) (string, error) {
	return "external-test", nil
}

func (acceptedIncomingPush) SubmitIncomingCallCancellation(
	context.Context,
	notification.IncomingCallDeliveryJob,
) (string, error) {
	return "external-cancel-test", nil
}

func canonicalDeliveryKey(callID string, personaID string) string {
	sum := sha256.Sum256([]byte(
		strings.TrimSpace(callID) + "\x00" +
			strings.TrimSpace(personaID),
	))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func appendRTCStreamEvent(
	t *testing.T,
	stream string,
	eventType string,
	eventID string,
	callID string,
	occurredAt time.Time,
	envelope map[string]any,
) {
	t.Helper()
	payload, err := json.Marshal(envelope)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := notificationRedisClient.XAdd(
		context.Background(),
		stream,
		map[string]string{
			"eventId":     eventID,
			"eventType":   eventType,
			"callId":      callID,
			"occurredAt":  occurredAt.UTC().Format(time.RFC3339Nano),
			"payloadJson": string(payload),
		},
	); err != nil {
		t.Fatal(err)
	}
}

func loadIncomingCallJobs(
	t *testing.T,
	callID string,
) []notification.IncomingCallDeliveryJob {
	t.Helper()
	cursor, err := notificationMongoDB.Collection(
		"notification_delivery_jobs",
	).Find(context.Background(), bson.M{"callId": callID})
	if err != nil {
		t.Fatal(err)
	}
	defer cursor.Close(context.Background())
	var jobs []notification.IncomingCallDeliveryJob
	if err := cursor.All(context.Background(), &jobs); err != nil {
		t.Fatal(err)
	}
	return jobs
}

func assertIncomingStatus(
	t *testing.T,
	jobs []notification.IncomingCallDeliveryJob,
	deviceID string,
	status string,
) {
	t.Helper()
	for _, job := range jobs {
		if job.DeviceID == deviceID {
			if job.Status != status {
				t.Fatalf(
					"device %s status=%s want=%s job=%+v",
					deviceID,
					job.Status,
					status,
					job,
				)
			}
			return
		}
	}
	t.Fatalf("device %s job not found: %+v", deviceID, jobs)
}
