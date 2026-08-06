// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-003
// readiness_case: ack-incoming-call-presentation-local
// readiness_case: handle-incoming-call-ringing-local
// readiness_case: handle-incoming-call-cancellation-local
package local_contract

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"testing"
	"time"

	application "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/domain"
)

type localIncomingCallStore struct {
	job                        notification.IncomingCallDeliveryJob
	created                    bool
	cancellationRealtimeMarked bool
}

func (s *localIncomingCallStore) EnsureIncomingCallJob(
	_ context.Context,
	event notification.IncomingCallRingingEvent,
	destination notification.PushDestinationRef,
	now time.Time,
) (notification.IncomingCallDeliveryJob, bool, error) {
	if s.created {
		return s.job, false, nil
	}
	s.created = true
	s.job = notification.IncomingCallDeliveryJob{
		ID: "incoming-call-local-1", EventID: event.EventID, CallID: event.CallID,
		TargetPersonaID: event.TargetPersonaID, DeviceID: destination.DeviceID,
		DestinationRef: destination.EndpointRef, DeliveryKey: event.DeliveryKey,
		CallType: event.CallType, CallerName: event.CallerName,
		SourceLabel: event.SourceLabel, TrustRelation: event.TrustRelation,
		Status: "pending", ExpiresAt: event.ExpiresAt, Version: 1,
		CreatedAt: now, UpdatedAt: now,
	}
	return s.job, true, nil
}

func (s *localIncomingCallStore) MarkIncomingCallRealtimeDispatched(
	_ context.Context,
	_ string,
	_ int64,
	dispatchedAt, ackDeadlineAt time.Time,
) (notification.IncomingCallDeliveryJob, bool, error) {
	s.job.Status = notification.IncomingCallStatusRealtimeDispatched
	s.job.RealtimeDispatchedAt = &dispatchedAt
	s.job.AckDeadlineAt = &ackDeadlineAt
	s.job.Version++
	return s.job, true, nil
}

func (*localIncomingCallStore) QueueIncomingCallPush(
	context.Context, string, []string, time.Time,
) (bool, error) {
	return false, nil
}

func (*localIncomingCallStore) QueueExpiredRealtimeDispatches(
	context.Context, time.Time,
) (int64, error) {
	return 0, nil
}

func (*localIncomingCallStore) ExpireIncomingCallJobs(
	context.Context, time.Time,
) (int64, error) {
	return 0, nil
}

func (*localIncomingCallStore) ClaimIncomingCallPush(
	context.Context, time.Time,
) (*notification.IncomingCallDeliveryJob, error) {
	return nil, nil
}

func (*localIncomingCallStore) RequeueIncomingCallPush(
	context.Context, string, int64, time.Time,
) error {
	return nil
}

func (*localIncomingCallStore) MarkIncomingCallExternalAccepted(
	context.Context, string, int64, string, time.Time,
) error {
	return nil
}

func (s *localIncomingCallStore) AckIncomingCallPresentation(
	_ context.Context,
	personaID, deviceID, deliveryKey string,
	now time.Time,
) (notification.AckIncomingCallPresentationResult, error) {
	s.job.Status = notification.IncomingCallStatusRealtimePresented
	s.job.PresentedAt = &now
	return notification.AckIncomingCallPresentationResult{
		DeliveryKey:    deliveryKey,
		DeviceID:       deviceID,
		Status:         notification.IncomingCallStatusRealtimePresented,
		AcknowledgedAt: now,
	}, nil
}

func (s *localIncomingCallStore) CancelIncomingCallJobs(
	_ context.Context,
	event notification.IncomingCallCancellationEvent,
	now time.Time,
) ([]notification.IncomingCallCancellationWork, error) {
	s.job.Status = notification.IncomingCallStatusCancelled
	s.job.CancellationEventID = event.EventID
	s.job.CancellationEventType = event.EventType
	s.job.CancellationActorID = event.ActorID
	s.job.CancellationOccurredAt = &event.OccurredAt
	s.job.CancelledAt = &now
	s.job.Version++
	return []notification.IncomingCallCancellationWork{{
		Job:                      s.job,
		RealtimeDispatchRequired: true,
	}}, nil
}

func (s *localIncomingCallStore) MarkIncomingCallCancellationRealtimeDispatched(
	context.Context, string, string, string, time.Time,
) error {
	s.cancellationRealtimeMarked = true
	return nil
}

func (*localIncomingCallStore) MarkIncomingCallCancellationExternalAccepted(
	context.Context, string, int64, string, time.Time,
) error {
	return nil
}

type localDestinationReader struct {
	destination notification.PushDestinationRef
}

func (r localDestinationReader) ListPushDestinations(
	context.Context,
	string,
) ([]notification.PushDestinationRef, error) {
	return []notification.PushDestinationRef{r.destination}, nil
}

type localPresenceReader struct {
	view application.PersonaPresenceView
}

func (r localPresenceReader) GetPersonaPresence(
	context.Context,
	string,
) (application.PersonaPresenceView, error) {
	return r.view, nil
}

type localRealtimeDispatcher struct {
	incoming, cancellation int
}

func (d *localRealtimeDispatcher) DispatchIncomingCall(
	context.Context,
	notification.IncomingCallDeliveryJob,
) error {
	d.incoming++
	return nil
}

func (d *localRealtimeDispatcher) DispatchCancellation(
	context.Context,
	string,
	notification.IncomingCallCancellationEvent,
) error {
	d.cancellation++
	return nil
}

type localPushSubmitter struct{}

func (localPushSubmitter) SubmitIncomingCall(
	context.Context,
	notification.IncomingCallDeliveryJob,
) (string, error) {
	return "incoming-call-request-local", nil
}

func (localPushSubmitter) SubmitIncomingCallCancellation(
	context.Context,
	notification.IncomingCallDeliveryJob,
) (string, error) {
	return "incoming-call-cancel-local", nil
}

func TestIncomingCallCoordinatorOwnsRingingPresentationAckAndCancellation(t *testing.T) {
	now := time.Date(2026, 8, 5, 13, 0, 0, 0, time.UTC)
	callID := "51cdbd68-dc62-4728-8953-3cbb6e413c6a"
	personaID := "persona-notification-local"
	deliveryKeySum := sha256.Sum256([]byte(callID + "\x00" + personaID))
	deliveryKey := "sha256:" + hex.EncodeToString(deliveryKeySum[:])
	store := &localIncomingCallStore{}
	realtime := &localRealtimeDispatcher{}
	coordinator, err := application.NewIncomingCallDeliveryCoordinator(
		store,
		localDestinationReader{destination: notification.PushDestinationRef{
			DeviceID: "device-notification-local", EndpointRef: "endpoint-notification-local",
		}},
		localPresenceReader{view: application.PersonaPresenceView{
			PersonaID: personaID,
			Devices: []application.PersonaPresenceDevice{{
				PersonaID: personaID, DeviceID: "device-notification-local", Online: true,
			}},
		}},
		realtime,
		localPushSubmitter{},
		application.WithIncomingCallClock(func() time.Time { return now }),
	)
	if err != nil {
		t.Fatalf("construct incoming-call coordinator: %v", err)
	}
	event := notification.IncomingCallRingingEvent{
		EventID: "event-notification-local", CallID: callID,
		TargetPersonaID: personaID, CallType: "audio", CallerName: "来电者",
		SourceLabel: "conversation", TrustRelation: "known",
		ExpiresAt: now.Add(30 * time.Second), DeliveryKey: deliveryKey,
	}
	if err := coordinator.HandleRinging(t.Context(), event); err != nil {
		t.Fatalf("handle ringing: %v", err)
	}
	if realtime.incoming != 1 || store.job.Status != notification.IncomingCallStatusRealtimeDispatched {
		t.Fatalf("ringing did not reach typed realtime boundary: dispatches=%d job=%+v", realtime.incoming, store.job)
	}
	ack, err := coordinator.AckPresentation(t.Context(), personaID, "device-notification-local", deliveryKey)
	if err != nil || ack.Status != notification.IncomingCallStatusRealtimePresented || ack.Raced {
		t.Fatalf("presentation ACK=%+v err=%v", ack, err)
	}
	if err := coordinator.HandleCancellation(t.Context(), notification.IncomingCallCancellationEvent{
		EventID: "event-notification-cancel-local", EventType: "CallAnswered",
		CallID: callID, ActorID: personaID, OccurredAt: now,
	}); err != nil {
		t.Fatalf("handle cancellation: %v", err)
	}
	if realtime.cancellation != 1 || !store.cancellationRealtimeMarked ||
		store.job.Status != notification.IncomingCallStatusCancelled {
		t.Fatalf("cancellation did not converge: dispatcher=%+v store=%+v", realtime, store)
	}
}
