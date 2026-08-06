// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-003
// readiness_case: ack-incoming-call-presentation-api
// readiness_case: get-incoming-call-delivery-timeline-api
// readiness_case: handle-incoming-call-ringing-api
// readiness_case: handle-incoming-call-cancellation-api
// readiness_case: record-external-interaction-result-api
package api_integration

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/operation"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/reliabletask"
	deliveryhttp "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/adapters/inbound/http"
	deliverystream "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/adapters/inbound/stream"
	deliveryapp "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/domain"
	deliverypersistence "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/infrastructure/persistence"
)

type incomingAPIDestinationReader struct {
	items []notification.PushDestinationRef
}

func (r *incomingAPIDestinationReader) ListPushDestinations(
	context.Context,
	string,
) ([]notification.PushDestinationRef, error) {
	return append([]notification.PushDestinationRef(nil), r.items...), nil
}

type incomingAPIPresenceReader struct {
	view deliveryapp.PersonaPresenceView
}

func (r *incomingAPIPresenceReader) GetPersonaPresence(
	context.Context,
	string,
) (deliveryapp.PersonaPresenceView, error) {
	return r.view, nil
}

type incomingAPIRealtimeDispatcher struct {
	incoming, cancellations int
}

func (d *incomingAPIRealtimeDispatcher) DispatchIncomingCall(
	context.Context,
	notification.IncomingCallDeliveryJob,
) error {
	d.incoming++
	return nil
}

func (d *incomingAPIRealtimeDispatcher) DispatchCancellation(
	context.Context,
	string,
	notification.IncomingCallCancellationEvent,
) error {
	d.cancellations++
	return nil
}

type incomingAPIPushSubmitter struct {
	ringRequestID string
	cancellations int
}

func (s *incomingAPIPushSubmitter) SubmitIncomingCall(
	context.Context,
	notification.IncomingCallDeliveryJob,
) (string, error) {
	s.ringRequestID = "incoming-call-request-notification-api-1"
	return s.ringRequestID, nil
}

func (s *incomingAPIPushSubmitter) SubmitIncomingCallCancellation(
	context.Context,
	notification.IncomingCallDeliveryJob,
) (string, error) {
	s.cancellations++
	return fmt.Sprintf("incoming-call-cancel-notification-api-%d", s.cancellations), nil
}

func TestIncomingCallLifecycleUsesRealMongoAcrossRuntimeAndHTTPBoundaries(t *testing.T) {
	ctx, cancel := context.WithTimeout(t.Context(), 3*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(
		ctx,
		fmt.Sprintf("notification_incoming_readiness_%d", time.Now().UnixNano()),
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
	redisRuntime, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		t.Fatalf("start real notification Redis: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cleanupCancel()
		if err := redisRuntime.Close(cleanupCtx); err != nil {
			t.Errorf("close notification Redis: %v", err)
		}
	})
	if err := redisRuntime.FlushDBs(ctx, 0); err != nil {
		t.Fatalf("flush notification Redis: %v", err)
	}
	redisRouter, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode: "standalone", Addr: redisRuntime.Addr,
				Password: redisRuntime.Password, DB: 0, TLS: redisRuntime.TLS,
			},
		},
		DefaultScene: "general",
	})
	if err != nil {
		t.Fatalf("construct notification Redis router: %v", err)
	}
	redisClient := redisRouter.Scene("general")
	messageTransport, err := runtimemessaging.NewRedisMessageTransport(redisClient, redisClient)
	if err != nil {
		t.Fatalf("construct notification message transport: %v", err)
	}

	now := time.Date(2026, 8, 5, 14, 0, 0, 0, time.UTC)
	destinations := &incomingAPIDestinationReader{}
	presence := &incomingAPIPresenceReader{}
	realtime := &incomingAPIRealtimeDispatcher{}
	push := &incomingAPIPushSubmitter{}
	coordinator, err := deliveryapp.NewIncomingCallDeliveryCoordinator(
		store,
		destinations,
		presence,
		realtime,
		push,
		deliveryapp.WithIncomingCallClock(func() time.Time { return now }),
	)
	if err != nil {
		t.Fatalf("construct incoming-call coordinator: %v", err)
	}
	rtcConsumer, err := deliverystream.NewRTCIncomingCallConsumer(
		messageTransport,
		coordinator,
		"notification-delivery-job-readiness",
		nil,
	)
	if err != nil {
		t.Fatalf("construct incoming-call stream consumer: %v", err)
	}
	queries, err := deliveryapp.NewNotificationDeliveryJobQueryFacade(store, store, store)
	if err != nil {
		t.Fatalf("construct delivery query facade: %v", err)
	}
	commands, err := deliveryapp.NewNotificationDeliveryJobCommandFacade(store)
	if err != nil {
		t.Fatalf("construct delivery command facade: %v", err)
	}
	deliveryHandler, err := deliveryhttp.NewHandler(commands, queries)
	if err != nil {
		t.Fatalf("construct delivery HTTP handler: %v", err)
	}
	deliveryHandler.WithIncomingCallCoordinator(coordinator)

	onlineCallID := "51cdbd68-dc62-4728-8953-3cbb6e413c6a"
	onlinePersonaID := "persona-incoming-api-online"
	onlineDeliveryKey := incomingReadinessDeliveryKey(onlineCallID, onlinePersonaID)
	destinations.items = []notification.PushDestinationRef{{
		DeviceID: "device-incoming-api-online", EndpointRef: strings.Repeat("a", 64),
	}}
	presence.view = deliveryapp.PersonaPresenceView{
		PersonaID: onlinePersonaID,
		Devices: []deliveryapp.PersonaPresenceDevice{{
			PersonaID: onlinePersonaID,
			DeviceID:  "device-incoming-api-online",
			Online:    true,
		}},
	}
	onlineEvent := notification.IncomingCallRingingEvent{
		EventID: "event-incoming-api-online", CallID: onlineCallID,
		TargetPersonaID: onlinePersonaID, CallType: "audio", CallerName: "来电者",
		CallerAvatarURL: "https://assets.test/incoming-caller.png",
		SourceLabel:     "conversation", TrustRelation: "known",
		ExpiresAt: now.Add(30 * time.Second), DeliveryKey: onlineDeliveryKey,
	}
	onlineMessageID := appendRTCTestEvent(
		t, ctx, messageTransport, deliverystream.RTCCallRingingStream,
		"CallRinging", onlineEvent.EventID, onlineCallID, onlinePersonaID,
		onlineEvent, now,
	)
	if processed, err := rtcConsumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("consume online CallRinging: processed=%d err=%v", processed, err)
	}
	assertRTCTestEventAcked(
		t, ctx, messageTransport, deliverystream.RTCCallRingingStream, onlineMessageID,
	)
	if realtime.incoming != 1 {
		t.Fatalf("online realtime dispatches=%d want=1", realtime.incoming)
	}

	ackBody, err := json.Marshal(map[string]string{"deliveryKey": onlineDeliveryKey})
	if err != nil {
		t.Fatal(err)
	}
	ackRequest := httptest.NewRequest(
		http.MethodPost,
		"/notifications/incoming-calls/presentation:ack",
		bytes.NewReader(ackBody),
	)
	ackRequest = ackRequest.WithContext(rtauth.WithPrincipal(
		ackRequest.Context(),
		rtauth.Principal{Actor: operation.ActorContext{
			AccountID: "account-incoming-api", PersonaID: onlinePersonaID,
			DeviceActorID: "device-incoming-api-online",
		}},
	))
	ackRecorder := httptest.NewRecorder()
	deliveryHandler.Routes().ServeHTTP(ackRecorder, ackRequest)
	if ackRecorder.Code != http.StatusOK {
		t.Fatalf("presentation ACK status=%d body=%s", ackRecorder.Code, ackRecorder.Body.String())
	}
	var ack notification.AckIncomingCallPresentationResult
	if err := json.Unmarshal(ackRecorder.Body.Bytes(), &ack); err != nil ||
		ack.Status != notification.IncomingCallStatusRealtimePresented || ack.Raced {
		t.Fatalf("presentation ACK=%+v err=%v", ack, err)
	}

	cancellationEventID := "event-incoming-api-cancel"
	cancellationMessageID := appendRTCTestEvent(
		t, ctx, messageTransport, deliverystream.RTCCallAnsweredStream,
		"CallAnswered", cancellationEventID, onlineCallID, onlinePersonaID,
		map[string]any{}, now,
	)
	if processed, err := rtcConsumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("consume CallAnswered cancellation: processed=%d err=%v", processed, err)
	}
	assertRTCTestEventAcked(
		t, ctx, messageTransport, deliverystream.RTCCallAnsweredStream,
		cancellationMessageID,
	)
	if realtime.cancellations != 1 {
		t.Fatalf("realtime cancellations=%d want=1", realtime.cancellations)
	}
	var cancelledJob struct {
		ID string `bson:"_id"`
	}
	if err := runtime.Database.Collection("notification_delivery_jobs").FindOne(
		ctx,
		bson.M{"callId": onlineCallID},
	).Decode(&cancelledJob); err != nil {
		t.Fatalf("read cancelled incoming-call job: %v", err)
	}
	cursor, err := runtime.Database.Collection("notification_delivery_jobs_outbox").Find(
		ctx,
		bson.M{
			"aggregateId": cancelledJob.ID,
			"eventType": bson.M{"$in": []string{
				"IncomingCallCancellationPushSubmitted",
				"IncomingCallCancellationExternalInteractionAccepted",
			}},
		},
	)
	if err != nil {
		t.Fatalf("read cancellation outbox facts: %v", err)
	}
	defer cursor.Close(ctx)
	var cancellationFacts []struct {
		EventType        string `bson:"eventType"`
		AggregateVersion int64  `bson:"aggregateVersion"`
	}
	if err := cursor.All(ctx, &cancellationFacts); err != nil {
		t.Fatalf("decode cancellation outbox facts: %v", err)
	}
	versions := map[string]int64{}
	for _, fact := range cancellationFacts {
		versions[fact.EventType] = fact.AggregateVersion
	}
	if len(versions) != 2 ||
		versions["IncomingCallCancellationExternalInteractionAccepted"] !=
			versions["IncomingCallCancellationPushSubmitted"]+1 {
		t.Fatalf("cancellation facts must own consecutive aggregate versions: %+v", versions)
	}

	offlineCallID := "26ccae3e-577c-4c4a-b0a5-1a7675b4c28d"
	offlinePersonaID := "persona-incoming-api-offline"
	destinations.items = []notification.PushDestinationRef{{
		DeviceID: "device-incoming-api-offline", EndpointRef: strings.Repeat("b", 64),
	}}
	presence.view = deliveryapp.PersonaPresenceView{PersonaID: offlinePersonaID}
	offlineEvent := notification.IncomingCallRingingEvent{
		EventID: "event-incoming-api-offline", CallID: offlineCallID,
		TargetPersonaID: offlinePersonaID, CallType: "video", CallerName: "来电者",
		CallerAvatarURL: "https://assets.test/incoming-caller.png",
		SourceLabel:     "conversation", TrustRelation: "known",
		ExpiresAt:   now.Add(30 * time.Second),
		DeliveryKey: incomingReadinessDeliveryKey(offlineCallID, offlinePersonaID),
	}
	offlineMessageID := appendRTCTestEvent(
		t, ctx, messageTransport, deliverystream.RTCCallRingingStream,
		"CallRinging", offlineEvent.EventID, offlineCallID, offlinePersonaID,
		offlineEvent, now,
	)
	if processed, err := rtcConsumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("consume offline CallRinging: processed=%d err=%v", processed, err)
	}
	assertRTCTestEventAcked(
		t, ctx, messageTransport, deliverystream.RTCCallRingingStream, offlineMessageID,
	)
	if processed, err := coordinator.ProcessDue(ctx); err != nil || !processed {
		t.Fatalf("process offline incoming call: processed=%v err=%v", processed, err)
	}
	recorder, err := deliveryapp.NewExternalInteractionResultRecorder(store)
	if err != nil {
		t.Fatalf("construct external result recorder: %v", err)
	}
	result := notification.ExternalInteractionResultEvent{
		AttemptID: "attempt-incoming-api-1", RequestID: push.ringRequestID,
		Operation:             reliabletask.ExternalInteractionOperationPush,
		Status:                reliabletask.ExternalInteractionStatusSentUnconfirmed,
		Provider:              "apns_voip",
		ProviderRequestDigest: "sha256:" + strings.Repeat("c", 64),
		RecoveryAction:        "none", OccurredAt: now.Add(time.Second),
	}
	if err := recorder.RecordExternalInteractionResult(ctx, result, now.Add(time.Second)); err != nil {
		t.Fatalf("record external interaction result: %v", err)
	}

	for _, expected := range []struct {
		callID string
		status string
	}{
		{callID: onlineCallID, status: notification.IncomingCallStatusCancelled},
		{callID: offlineCallID, status: notification.IncomingCallStatusSentUnconfirmed},
	} {
		timelineRecorder := httptest.NewRecorder()
		deliveryHandler.Routes().ServeHTTP(
			timelineRecorder,
			httptest.NewRequest(
				http.MethodGet,
				"/internal/notifications/delivery-jobs/incoming-call-timeline?callId="+expected.callID,
				nil,
			),
		)
		if timelineRecorder.Code != http.StatusOK {
			t.Fatalf("timeline status=%d body=%s", timelineRecorder.Code, timelineRecorder.Body.String())
		}
		var timeline notification.IncomingCallDeliveryTimeline
		if err := json.Unmarshal(timelineRecorder.Body.Bytes(), &timeline); err != nil ||
			len(timeline.Items) != 1 || timeline.Items[0].Status != expected.status {
			t.Fatalf("timeline for %s=%+v err=%v", expected.callID, timeline, err)
		}
	}
}

func incomingReadinessDeliveryKey(callID, personaID string) string {
	sum := sha256.Sum256([]byte(callID + "\x00" + personaID))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func appendRTCTestEvent(
	t *testing.T,
	ctx context.Context,
	transport *runtimemessaging.RedisMessageTransport,
	stream string,
	eventType string,
	eventID string,
	callID string,
	actorID string,
	payload any,
	occurredAt time.Time,
) string {
	t.Helper()
	payloadJSON, err := json.Marshal(map[string]any{
		"callId":  callID,
		"actorId": actorID,
		"payload": payload,
	})
	if err != nil {
		t.Fatalf("marshal RTC lifecycle event: %v", err)
	}
	messageID, err := transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: stream,
		Fields: []runtimemessaging.DurableField{
			{Name: "eventType", Value: eventType},
			{Name: "eventId", Value: eventID},
			{Name: "payloadJson", Value: string(payloadJSON)},
			{Name: "occurredAt", Value: occurredAt.UTC().Format(time.RFC3339Nano)},
		},
	})
	if err != nil {
		t.Fatalf("append RTC lifecycle event: %v", err)
	}
	return messageID
}

func assertRTCTestEventAcked(
	t *testing.T,
	ctx context.Context,
	transport *runtimemessaging.RedisMessageTransport,
	stream string,
	messageID string,
) {
	t.Helper()
	pending, _, err := transport.ReclaimDurable(
		ctx,
		stream,
		deliverystream.RTCIncomingCallConsumerGroup,
		"notification-delivery-job-ack-probe",
		0,
		"0-0",
		100,
	)
	if err != nil {
		t.Fatalf("read RTC pending state after ACK: %v", err)
	}
	for _, delivery := range pending {
		if delivery.ID == messageID {
			t.Fatalf("RTC lifecycle event %s remained pending after consumer ACK", messageID)
		}
	}
}
