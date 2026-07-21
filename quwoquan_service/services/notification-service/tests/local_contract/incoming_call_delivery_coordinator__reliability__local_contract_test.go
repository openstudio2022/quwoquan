package local_contract

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/reliabletask"
	streamadapter "quwoquan_service/services/notification-service/internal/adapters/stream"
	"quwoquan_service/services/notification-service/internal/application"
	notification "quwoquan_service/services/notification-service/internal/domain/notification"
)

func TestIncomingCallCoordinatorOnlineAckNoAckOfflineExpiryAndCancellation(
	t *testing.T,
) {
	t.Parallel()
	now := time.Date(2026, 7, 20, 17, 0, 0, 0, time.UTC)
	store := newIncomingCallStoreFake()
	destinations := &pushDestinationReaderFake{}
	presence := &presenceReaderFake{}
	realtime := &incomingRealtimeFake{}
	push := &incomingPushFake{}
	coordinator, err := application.NewIncomingCallDeliveryCoordinator(
		store,
		destinations,
		presence,
		realtime,
		push,
		application.WithIncomingCallClock(func() time.Time { return now }),
	)
	if err != nil {
		t.Fatal(err)
	}

	destinations.set("device-ack", "endpoint-ack")
	presence.setOnline("persona-target", "device-ack")
	ackEvent := incomingCallEvent(
		"6c7eb5db-a53c-44bf-a389-39fc8ea9af25",
		"persona-target",
		now,
	)
	if err := coordinator.HandleRinging(
		context.Background(),
		ackEvent,
	); err != nil {
		t.Fatalf("handle online ACK call: %v", err)
	}
	ack, err := coordinator.AckPresentation(
		context.Background(),
		ackEvent.TargetPersonaID,
		"device-ack",
		ackEvent.DeliveryKey,
	)
	if err != nil ||
		ack.Raced ||
		ack.Status != notification.IncomingCallStatusRealtimePresented {
		t.Fatalf("on-time ACK=%+v err=%v", ack, err)
	}
	now = now.Add(time.Second)
	if processed, err := coordinator.ProcessDue(context.Background()); err != nil || processed {
		t.Fatalf("ACKed call must not push: processed=%v err=%v", processed, err)
	}

	destinations.set("device-noack", "endpoint-noack")
	presence.setOnline("persona-target", "device-noack")
	noAckEvent := incomingCallEvent(
		"26ccae3e-577c-4c4a-b0a5-1a7675b4c28d",
		"persona-target",
		now,
	)
	if err := coordinator.HandleRinging(
		context.Background(),
		noAckEvent,
	); err != nil {
		t.Fatalf("handle no-ACK call: %v", err)
	}
	if err := coordinator.HandleRinging(
		context.Background(),
		noAckEvent,
	); err != nil {
		t.Fatalf("replay no-ACK call: %v", err)
	}
	if store.countByCall(noAckEvent.CallID) != 1 ||
		realtime.incomingCount(noAckEvent.CallID) != 1 {
		t.Fatal("durable replay must not duplicate job or realtime dispatch")
	}
	now = now.Add(751 * time.Millisecond)
	if processed, err := coordinator.ProcessDue(context.Background()); err != nil || !processed {
		t.Fatalf("no-ACK call must push after grace: %v %v", processed, err)
	}
	if status := store.status(noAckEvent.DeliveryKey, "device-noack"); status != notification.IncomingCallStatusSentUnconfirmed {
		t.Fatalf("no-ACK status=%s", status)
	}

	destinations.set("device-offline", "endpoint-offline")
	presence.clear()
	offlineEvent := incomingCallEvent(
		"f26628b7-059e-42c8-9800-1647643dc6cc",
		"persona-target",
		now,
	)
	if err := coordinator.HandleRinging(
		context.Background(),
		offlineEvent,
	); err != nil {
		t.Fatalf("handle offline call: %v", err)
	}
	if status := store.status(
		offlineEvent.DeliveryKey,
		"device-offline",
	); status != notification.IncomingCallStatusPushQueued {
		t.Fatalf("offline status=%s", status)
	}
	late, err := coordinator.AckPresentation(
		context.Background(),
		offlineEvent.TargetPersonaID,
		"device-offline",
		offlineEvent.DeliveryKey,
	)
	if err != nil || !late.Raced ||
		late.Status != notification.IncomingCallStatusPushQueued {
		t.Fatalf("late ACK=%+v err=%v", late, err)
	}
	if processed, err := coordinator.ProcessDue(context.Background()); err != nil || !processed {
		t.Fatalf("offline push process=%v err=%v", processed, err)
	}

	expiredEvent := incomingCallEvent(
		"d7e37c5a-843a-4ecb-8e3f-90afaf358fa5",
		"persona-target",
		now.Add(-time.Minute),
	)
	expiredEvent.ExpiresAt = now.Add(-time.Millisecond)
	if err := coordinator.HandleRinging(
		context.Background(),
		expiredEvent,
	); err != nil {
		t.Fatalf("expired event must be absorbed: %v", err)
	}
	if store.countByCall(expiredEvent.CallID) != 0 {
		t.Fatal("expired event must not create a delivery job")
	}

	if err := coordinator.HandleCancellation(
		context.Background(),
		notification.IncomingCallCancellationEvent{
			EventID:    "rtc-answer-noack",
			EventType:  "CallAnswered",
			CallID:     noAckEvent.CallID,
			ActorID:    "persona-target",
			OccurredAt: now,
		},
	); err != nil {
		t.Fatalf("cancel no-ACK call: %v", err)
	}
	if status := store.status(noAckEvent.DeliveryKey, "device-noack"); status != notification.IncomingCallStatusCancelled {
		t.Fatalf("cancelled status=%s", status)
	}
	if realtime.cancellationCount(noAckEvent.CallID) != 1 {
		t.Fatal("cancellation must close remaining incoming call UI")
	}
	if err := coordinator.HandleCancellation(
		context.Background(),
		notification.IncomingCallCancellationEvent{
			EventID:    "rtc-answer-noack",
			EventType:  "CallAnswered",
			CallID:     noAckEvent.CallID,
			ActorID:    "persona-target",
			OccurredAt: now,
		},
	); err != nil {
		t.Fatalf("replay cancellation: %v", err)
	}
	if realtime.cancellationCount(noAckEvent.CallID) != 1 {
		t.Fatal("cancellation replay must not close incoming call UI twice")
	}
	if push.count(noAckEvent.CallID) != 1 ||
		push.count(offlineEvent.CallID) != 1 ||
		push.count(ackEvent.CallID) != 0 {
		t.Fatalf("unexpected push calls=%v", push.calls)
	}
	if push.cancellationCount(noAckEvent.CallID) != 1 {
		t.Fatalf(
			"sent ring must receive one durable cancel push: %+v",
			push.cancellations,
		)
	}
}

func TestIncomingCallDurableStreamReplayIsIdempotent(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 7, 20, 18, 0, 0, 0, time.UTC)
	store := newIncomingCallStoreFake()
	destinations := &pushDestinationReaderFake{}
	destinations.set("device-stream", "endpoint-stream")
	presence := &presenceReaderFake{}
	presence.setOnline("persona-stream", "device-stream")
	realtime := &incomingRealtimeFake{}
	coordinator, err := application.NewIncomingCallDeliveryCoordinator(
		store,
		destinations,
		presence,
		realtime,
		&incomingPushFake{},
		application.WithIncomingCallClock(func() time.Time { return now }),
	)
	if err != nil {
		t.Fatal(err)
	}
	client := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(client, client)
	if err != nil {
		t.Fatal(err)
	}
	consumer, err := streamadapter.NewRTCIncomingCallConsumer(
		transport,
		coordinator,
		"local-contract",
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	event := incomingCallEvent(
		"91c93cef-0892-4d54-927d-a863a5730f44",
		"persona-stream",
		now,
	)
	envelope, _ := json.Marshal(map[string]any{
		"callId":  event.CallID,
		"payload": event,
	})
	for replay := 0; replay < 2; replay++ {
		if _, err := client.XAdd(
			context.Background(),
			streamadapter.RTCCallRingingStream,
			map[string]string{
				"eventId":     event.EventID,
				"eventType":   "CallRinging",
				"callId":      event.CallID,
				"occurredAt":  now.Format(time.RFC3339Nano),
				"payloadJson": string(envelope),
			},
		); err != nil {
			t.Fatal(err)
		}
		if _, err := consumer.ProcessOnce(context.Background()); err != nil {
			t.Fatalf("process replay %d: %v", replay, err)
		}
	}
	if store.countByCall(event.CallID) != 1 ||
		realtime.incomingCount(event.CallID) != 1 {
		t.Fatalf(
			"durable replay duplicated delivery: jobs=%d realtime=%d",
			store.countByCall(event.CallID),
			realtime.incomingCount(event.CallID),
		)
	}
}

func incomingCallEvent(
	callID string,
	personaID string,
	now time.Time,
) notification.IncomingCallRingingEvent {
	sum := sha256.Sum256([]byte(callID + "\x00" + personaID))
	return notification.IncomingCallRingingEvent{
		EventID:         "event-" + callID,
		CallID:          callID,
		TargetPersonaID: personaID,
		CallType:        "audio",
		CallerName:      "caller",
		CallerAvatarURL: "",
		SourceLabel:     "direct_call",
		TrustRelation:   "known",
		ExpiresAt:       now.Add(30 * time.Second),
		DeliveryKey:     "sha256:" + hex.EncodeToString(sum[:]),
	}
}

type pushDestinationReaderFake struct {
	mu    sync.Mutex
	items []notification.PushDestinationRef
}

func (f *pushDestinationReaderFake) set(deviceID, endpointRef string) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.items = []notification.PushDestinationRef{{
		DeviceID:    deviceID,
		EndpointRef: endpointRef,
	}}
}

func (f *pushDestinationReaderFake) ListPushDestinations(
	context.Context,
	string,
) ([]notification.PushDestinationRef, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]notification.PushDestinationRef(nil), f.items...), nil
}

type presenceReaderFake struct {
	mu   sync.Mutex
	view application.PersonaPresenceView
}

func (f *presenceReaderFake) setOnline(personaID, deviceID string) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.view = application.PersonaPresenceView{
		PersonaID: personaID,
		Devices: []application.PersonaPresenceDevice{{
			PersonaID: personaID,
			DeviceID:  deviceID,
			Online:    true,
		}},
	}
}

func (f *presenceReaderFake) clear() {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.view = application.PersonaPresenceView{}
}

func (f *presenceReaderFake) GetPersonaPresence(
	context.Context,
	string,
) (application.PersonaPresenceView, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.view, nil
}

type incomingRealtimeFake struct {
	mu            sync.Mutex
	incoming      []notification.IncomingCallDeliveryJob
	cancellations []notification.IncomingCallCancellationEvent
}

func (f *incomingRealtimeFake) DispatchIncomingCall(
	_ context.Context,
	job notification.IncomingCallDeliveryJob,
) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.incoming = append(f.incoming, job)
	return nil
}

func (f *incomingRealtimeFake) DispatchCancellation(
	_ context.Context,
	_ string,
	event notification.IncomingCallCancellationEvent,
) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.cancellations = append(f.cancellations, event)
	return nil
}

func (f *incomingRealtimeFake) incomingCount(callID string) int {
	f.mu.Lock()
	defer f.mu.Unlock()
	count := 0
	for _, job := range f.incoming {
		if job.CallID == callID {
			count++
		}
	}
	return count
}

func (f *incomingRealtimeFake) cancellationCount(callID string) int {
	f.mu.Lock()
	defer f.mu.Unlock()
	count := 0
	for _, event := range f.cancellations {
		if event.CallID == callID {
			count++
		}
	}
	return count
}

type incomingPushFake struct {
	mu            sync.Mutex
	calls         []notification.IncomingCallDeliveryJob
	cancellations []notification.IncomingCallDeliveryJob
}

func (f *incomingPushFake) SubmitIncomingCall(
	_ context.Context,
	job notification.IncomingCallDeliveryJob,
) (string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls = append(f.calls, job)
	return "external-" + job.ID, nil
}

func (f *incomingPushFake) SubmitIncomingCallCancellation(
	_ context.Context,
	job notification.IncomingCallDeliveryJob,
) (string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.cancellations = append(f.cancellations, job)
	return "external-cancel-" + job.ID, nil
}

func (f *incomingPushFake) count(callID string) int {
	f.mu.Lock()
	defer f.mu.Unlock()
	count := 0
	for _, job := range f.calls {
		if job.CallID == callID {
			count++
		}
	}
	return count
}

func (f *incomingPushFake) cancellationCount(callID string) int {
	f.mu.Lock()
	defer f.mu.Unlock()
	count := 0
	for _, job := range f.cancellations {
		if job.CallID == callID {
			count++
		}
	}
	return count
}

type incomingCallStoreFake struct {
	mu   sync.Mutex
	jobs map[string]notification.IncomingCallDeliveryJob
}

func newIncomingCallStoreFake() *incomingCallStoreFake {
	return &incomingCallStoreFake{
		jobs: map[string]notification.IncomingCallDeliveryJob{},
	}
}

func (s *incomingCallStoreFake) EnsureIncomingCallJob(
	_ context.Context,
	event notification.IncomingCallRingingEvent,
	destination notification.PushDestinationRef,
	now time.Time,
) (notification.IncomingCallDeliveryJob, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	id := event.DeliveryKey + ":" + destination.DeviceID
	if job, found := s.jobs[id]; found {
		return job, false, nil
	}
	job := notification.IncomingCallDeliveryJob{
		ID:              id,
		NotificationID:  event.EventID,
		EventID:         event.EventID,
		CallID:          event.CallID,
		TargetPersonaID: event.TargetPersonaID,
		DeviceID:        destination.DeviceID,
		DestinationRef:  destination.EndpointRef,
		DeliveryKey:     event.DeliveryKey,
		CallType:        event.CallType,
		CallerName:      event.CallerName,
		CallerAvatarURL: event.CallerAvatarURL,
		SourceLabel:     event.SourceLabel,
		TrustRelation:   event.TrustRelation,
		Status:          reliabletask.NotificationStatusPending,
		ExpiresAt:       event.ExpiresAt,
		Version:         1,
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	s.jobs[id] = job
	return job, true, nil
}

func (s *incomingCallStoreFake) MarkIncomingCallRealtimeDispatched(
	_ context.Context,
	jobID string,
	expectedVersion int64,
	dispatchedAt time.Time,
	ackDeadlineAt time.Time,
) (notification.IncomingCallDeliveryJob, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	job, found := s.jobs[jobID]
	if !found ||
		job.Version != expectedVersion ||
		job.Status != reliabletask.NotificationStatusPending {
		return job, false, nil
	}
	job.Status = notification.IncomingCallStatusRealtimeDispatched
	job.Version++
	job.RealtimeDispatchedAt = &dispatchedAt
	job.AckDeadlineAt = &ackDeadlineAt
	job.UpdatedAt = dispatchedAt
	s.jobs[jobID] = job
	return job, true, nil
}

func (s *incomingCallStoreFake) QueueIncomingCallPush(
	_ context.Context,
	jobID string,
	expectedStatuses []string,
	now time.Time,
) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	job, found := s.jobs[jobID]
	if !found || !containsStatus(expectedStatuses, job.Status) ||
		!job.ExpiresAt.After(now) {
		return false, nil
	}
	job.Status = notification.IncomingCallStatusPushQueued
	job.Version++
	job.PushQueuedAt = &now
	job.UpdatedAt = now
	job.AckDeadlineAt = nil
	s.jobs[jobID] = job
	return true, nil
}

func (s *incomingCallStoreFake) QueueExpiredRealtimeDispatches(
	_ context.Context,
	now time.Time,
) (int64, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	var count int64
	for id, job := range s.jobs {
		if job.Status ==
			notification.IncomingCallStatusRealtimeDispatched &&
			job.AckDeadlineAt != nil &&
			!job.AckDeadlineAt.After(now) &&
			job.ExpiresAt.After(now) {
			job.Status = notification.IncomingCallStatusPushQueued
			job.Version++
			job.PushQueuedAt = &now
			job.AckDeadlineAt = nil
			s.jobs[id] = job
			count++
		}
	}
	return count, nil
}

func (s *incomingCallStoreFake) ExpireIncomingCallJobs(
	_ context.Context,
	now time.Time,
) (int64, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	var count int64
	for id, job := range s.jobs {
		if !job.ExpiresAt.After(now) &&
			job.Status != notification.IncomingCallStatusCancelled &&
			job.Status != notification.IncomingCallStatusSentUnconfirmed {
			job.Status = notification.IncomingCallStatusExpired
			job.Version++
			s.jobs[id] = job
			count++
		}
	}
	return count, nil
}

func (s *incomingCallStoreFake) ClaimIncomingCallPush(
	_ context.Context,
	now time.Time,
) (*notification.IncomingCallDeliveryJob, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	ids := make([]string, 0, len(s.jobs))
	for id := range s.jobs {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		job := s.jobs[id]
		if job.Status == notification.IncomingCallStatusPushQueued &&
			job.ExpiresAt.After(now) {
			job.Status = "leased"
			job.Version++
			s.jobs[id] = job
			copy := job
			return &copy, nil
		}
	}
	return nil, nil
}

func (s *incomingCallStoreFake) RequeueIncomingCallPush(
	_ context.Context,
	jobID string,
	version int64,
	_ time.Time,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	job := s.jobs[jobID]
	if job.Version == version && job.Status == "leased" {
		job.Status = notification.IncomingCallStatusPushQueued
		job.Version++
		s.jobs[jobID] = job
	}
	return nil
}

func (s *incomingCallStoreFake) MarkIncomingCallSentUnconfirmed(
	_ context.Context,
	jobID string,
	version int64,
	externalInteractionID string,
	now time.Time,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	job := s.jobs[jobID]
	if job.Version != version || job.Status != "leased" {
		return errors.New("lease mismatch")
	}
	job.Status = notification.IncomingCallStatusSentUnconfirmed
	job.ExternalInteractionID = externalInteractionID
	job.SentUnconfirmedAt = &now
	job.Version++
	s.jobs[jobID] = job
	return nil
}

func (s *incomingCallStoreFake) AckIncomingCallPresentation(
	_ context.Context,
	personaID string,
	deviceID string,
	deliveryKey string,
	now time.Time,
) (notification.AckIncomingCallPresentationResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for id, job := range s.jobs {
		if job.TargetPersonaID != personaID ||
			job.DeviceID != deviceID ||
			job.DeliveryKey != deliveryKey {
			continue
		}
		result := notification.AckIncomingCallPresentationResult{
			DeliveryKey:    deliveryKey,
			DeviceID:       deviceID,
			Status:         job.Status,
			AcknowledgedAt: now,
		}
		if job.Status ==
			notification.IncomingCallStatusRealtimeDispatched &&
			job.AckDeadlineAt != nil &&
			!now.After(*job.AckDeadlineAt) {
			job.Status =
				notification.IncomingCallStatusRealtimePresented
			job.PresentedAt = &now
			job.Version++
			s.jobs[id] = job
			result.Status = job.Status
			return result, nil
		}
		if job.Status !=
			notification.IncomingCallStatusRealtimePresented {
			job.AckRaceCount++
			job.Version++
			s.jobs[id] = job
			result.Raced = true
		}
		return result, nil
	}
	return notification.AckIncomingCallPresentationResult{},
		notification.ErrDeliveryJobNotFound
}

func (s *incomingCallStoreFake) CancelIncomingCallJobs(
	_ context.Context,
	event notification.IncomingCallCancellationEvent,
	now time.Time,
) ([]notification.IncomingCallCancellationWork, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for id, job := range s.jobs {
		if job.CallID != event.CallID {
			continue
		}
		if job.Status == notification.IncomingCallStatusCancelled ||
			job.Status == notification.IncomingCallStatusExpired {
			continue
		}
		pushRequired := fakeCancellationPushRequired(job.Status) &&
			job.ExpiresAt.After(now)
		job.Status = notification.IncomingCallStatusCancelled
		job.CancelledAt = &now
		job.CancellationEventID = event.EventID
		job.CancellationEventType = event.EventType
		job.CancellationActorID = event.ActorID
		job.CancellationOccurredAt = &event.OccurredAt
		job.CancellationPushRequired = pushRequired
		job.Version++
		s.jobs[id] = job
	}
	var works []notification.IncomingCallCancellationWork
	for _, job := range s.jobs {
		if job.CallID != event.CallID ||
			job.CancellationEventID != event.EventID {
			continue
		}
		realtimeRequired := job.CancellationRealtimeDispatchedAt == nil
		pushRequired := job.CancellationPushRequired &&
			job.CancellationPushSubmittedAt == nil &&
			job.ExpiresAt.After(now)
		if realtimeRequired || pushRequired {
			works = append(works, notification.IncomingCallCancellationWork{
				Job:                      job,
				RealtimeDispatchRequired: realtimeRequired,
				PushDispatchRequired:     pushRequired,
			})
		}
	}
	return works, nil
}

func (s *incomingCallStoreFake) MarkIncomingCallCancellationPushSubmitted(
	_ context.Context,
	jobID string,
	version int64,
	externalInteractionID string,
	now time.Time,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	job := s.jobs[jobID]
	if job.Version != version {
		return errors.New("cancellation push version mismatch")
	}
	job.CancellationExternalInteractionID = externalInteractionID
	job.CancellationPushSubmittedAt = &now
	job.Version++
	s.jobs[jobID] = job
	return nil
}

func (s *incomingCallStoreFake) MarkIncomingCallCancellationRealtimeDispatched(
	_ context.Context,
	callID string,
	personaID string,
	eventID string,
	now time.Time,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	for id, job := range s.jobs {
		if job.CallID != callID ||
			job.TargetPersonaID != personaID ||
			job.CancellationEventID != eventID ||
			job.CancellationRealtimeDispatchedAt != nil {
			continue
		}
		job.CancellationRealtimeDispatchedAt = &now
		job.Version++
		s.jobs[id] = job
	}
	return nil
}

func (s *incomingCallStoreFake) countByCall(callID string) int {
	s.mu.Lock()
	defer s.mu.Unlock()
	count := 0
	for _, job := range s.jobs {
		if job.CallID == callID {
			count++
		}
	}
	return count
}

func (s *incomingCallStoreFake) status(
	deliveryKey string,
	deviceID string,
) string {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, job := range s.jobs {
		if job.DeliveryKey == deliveryKey && job.DeviceID == deviceID {
			return job.Status
		}
	}
	return ""
}

func containsStatus(values []string, target string) bool {
	for _, value := range values {
		if strings.TrimSpace(value) == target {
			return true
		}
	}
	return false
}

func fakeCancellationPushRequired(status string) bool {
	switch status {
	case notification.IncomingCallStatusRealtimeDispatched,
		notification.IncomingCallStatusRealtimePresented,
		"leased",
		notification.IncomingCallStatusSentUnconfirmed:
		return true
	default:
		return false
	}
}
