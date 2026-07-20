package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"

	notification "quwoquan_service/services/notification-service/internal/domain/notification"
)

const (
	incomingCallPresentationGrace = 750 * time.Millisecond
	incomingCallPendingStatus     = "pending"
)

type PersonaPresenceDevice struct {
	AccountID string `json:"accountId"`
	PersonaID string `json:"personaId"`
	DeviceID  string `json:"deviceId"`
	Online    bool   `json:"online"`
}

type PersonaPresenceView struct {
	PersonaID string                  `json:"personaId"`
	Devices   []PersonaPresenceDevice `json:"devices"`
}

type PushDestinationReader interface {
	ListPushDestinations(
		ctx context.Context,
		personaID string,
	) ([]notification.PushDestinationRef, error)
}

type PersonaPresenceReader interface {
	GetPersonaPresence(
		ctx context.Context,
		personaID string,
	) (PersonaPresenceView, error)
}

type IncomingCallRealtimeDispatcher interface {
	DispatchIncomingCall(
		ctx context.Context,
		job notification.IncomingCallDeliveryJob,
	) error
	DispatchCancellation(
		ctx context.Context,
		personaID string,
		event notification.IncomingCallCancellationEvent,
	) error
}

type IncomingCallPushSubmitter interface {
	SubmitIncomingCall(
		ctx context.Context,
		job notification.IncomingCallDeliveryJob,
	) (externalInteractionID string, err error)
	SubmitIncomingCallCancellation(
		ctx context.Context,
		job notification.IncomingCallDeliveryJob,
	) (externalInteractionID string, err error)
}

type IncomingCallDeliveryStore interface {
	EnsureIncomingCallJob(
		ctx context.Context,
		event notification.IncomingCallRingingEvent,
		destination notification.PushDestinationRef,
		now time.Time,
	) (job notification.IncomingCallDeliveryJob, created bool, err error)
	MarkIncomingCallRealtimeDispatched(
		ctx context.Context,
		jobID string,
		expectedVersion int64,
		dispatchedAt time.Time,
		ackDeadlineAt time.Time,
	) (notification.IncomingCallDeliveryJob, bool, error)
	QueueIncomingCallPush(
		ctx context.Context,
		jobID string,
		expectedStatuses []string,
		now time.Time,
	) (bool, error)
	QueueExpiredRealtimeDispatches(
		ctx context.Context,
		now time.Time,
	) (int64, error)
	ExpireIncomingCallJobs(
		ctx context.Context,
		now time.Time,
	) (int64, error)
	ClaimIncomingCallPush(
		ctx context.Context,
		now time.Time,
	) (*notification.IncomingCallDeliveryJob, error)
	RequeueIncomingCallPush(
		ctx context.Context,
		jobID string,
		version int64,
		now time.Time,
	) error
	MarkIncomingCallSentUnconfirmed(
		ctx context.Context,
		jobID string,
		version int64,
		externalInteractionID string,
		now time.Time,
	) error
	AckIncomingCallPresentation(
		ctx context.Context,
		personaID string,
		deviceID string,
		deliveryKey string,
		now time.Time,
	) (notification.AckIncomingCallPresentationResult, error)
	CancelIncomingCallJobs(
		ctx context.Context,
		event notification.IncomingCallCancellationEvent,
		now time.Time,
	) ([]notification.IncomingCallCancellationWork, error)
	MarkIncomingCallCancellationRealtimeDispatched(
		ctx context.Context,
		callID string,
		personaID string,
		eventID string,
		now time.Time,
	) error
	MarkIncomingCallCancellationPushSubmitted(
		ctx context.Context,
		jobID string,
		version int64,
		externalInteractionID string,
		now time.Time,
	) error
}

type IncomingCallObserver interface {
	RecordIncomingCallTransition(fromStatus, toStatus, outcome string)
	RecordIncomingCallAck(raced bool)
}

type noopIncomingCallObserver struct{}

func (noopIncomingCallObserver) RecordIncomingCallTransition(
	string,
	string,
	string,
) {
}

func (noopIncomingCallObserver) RecordIncomingCallAck(bool) {}

type IncomingCallDeliveryCoordinator struct {
	store        IncomingCallDeliveryStore
	destinations PushDestinationReader
	presence     PersonaPresenceReader
	realtime     IncomingCallRealtimeDispatcher
	push         IncomingCallPushSubmitter
	observer     IncomingCallObserver
	now          func() time.Time
	grace        time.Duration
}

type IncomingCallCoordinatorOption func(*IncomingCallDeliveryCoordinator)

func WithIncomingCallClock(now func() time.Time) IncomingCallCoordinatorOption {
	return func(coordinator *IncomingCallDeliveryCoordinator) {
		if now != nil {
			coordinator.now = now
		}
	}
}

func WithIncomingCallObserver(
	observer IncomingCallObserver,
) IncomingCallCoordinatorOption {
	return func(coordinator *IncomingCallDeliveryCoordinator) {
		if observer != nil {
			coordinator.observer = observer
		}
	}
}

func NewIncomingCallDeliveryCoordinator(
	store IncomingCallDeliveryStore,
	destinations PushDestinationReader,
	presence PersonaPresenceReader,
	realtime IncomingCallRealtimeDispatcher,
	push IncomingCallPushSubmitter,
	options ...IncomingCallCoordinatorOption,
) (*IncomingCallDeliveryCoordinator, error) {
	if isNilDependency(store) ||
		isNilDependency(destinations) ||
		isNilDependency(presence) ||
		isNilDependency(realtime) ||
		isNilDependency(push) {
		return nil, errors.New(
			"incoming call coordinator requires store, destination, presence, realtime and push ports",
		)
	}
	coordinator := &IncomingCallDeliveryCoordinator{
		store:        store,
		destinations: destinations,
		presence:     presence,
		realtime:     realtime,
		push:         push,
		observer:     noopIncomingCallObserver{},
		now:          time.Now,
		grace:        incomingCallPresentationGrace,
	}
	for _, option := range options {
		if option != nil {
			option(coordinator)
		}
	}
	return coordinator, nil
}

func (c *IncomingCallDeliveryCoordinator) HandleRinging(
	ctx context.Context,
	event notification.IncomingCallRingingEvent,
) error {
	if err := validateIncomingCallRingingEvent(event); err != nil {
		return err
	}
	now := c.now().UTC()
	if !event.ExpiresAt.After(now) {
		return nil
	}
	destinations, err := c.destinations.ListPushDestinations(
		ctx,
		event.TargetPersonaID,
	)
	if err != nil {
		return fmt.Errorf("read incoming call push destinations: %w", err)
	}
	presence, err := c.presence.GetPersonaPresence(
		ctx,
		event.TargetPersonaID,
	)
	if err != nil {
		return fmt.Errorf("read incoming call presence: %w", err)
	}
	onlineDevices := make(map[string]struct{}, len(presence.Devices))
	for _, device := range presence.Devices {
		if device.Online &&
			strings.TrimSpace(device.PersonaID) == event.TargetPersonaID {
			onlineDevices[strings.TrimSpace(device.DeviceID)] = struct{}{}
		}
	}
	for _, destination := range normalizePushDestinations(destinations) {
		job, created, err := c.store.EnsureIncomingCallJob(
			ctx,
			event,
			destination,
			now,
		)
		if err != nil {
			return fmt.Errorf("ensure incoming call endpoint job: %w", err)
		}
		if !created {
			continue
		}
		if _, online := onlineDevices[job.DeviceID]; !online {
			if _, err := c.store.QueueIncomingCallPush(
				ctx,
				job.ID,
				[]string{incomingCallPendingStatus},
				now,
			); err != nil {
				return fmt.Errorf("queue offline incoming call push: %w", err)
			}
			c.observer.RecordIncomingCallTransition(
				incomingCallPendingStatus,
				notification.IncomingCallStatusPushQueued,
				"offline",
			)
			continue
		}
		deadline := now.Add(c.grace)
		dispatched, transitioned, err :=
			c.store.MarkIncomingCallRealtimeDispatched(
				ctx,
				job.ID,
				job.Version,
				now,
				deadline,
			)
		if err != nil {
			return fmt.Errorf("mark incoming call realtime dispatch: %w", err)
		}
		if !transitioned {
			continue
		}
		if err := c.realtime.DispatchIncomingCall(ctx, dispatched); err != nil {
			if _, queueErr := c.store.QueueIncomingCallPush(
				ctx,
				dispatched.ID,
				[]string{
					notification.IncomingCallStatusRealtimeDispatched,
				},
				now,
			); queueErr != nil {
				return errors.Join(
					fmt.Errorf("dispatch incoming call realtime: %w", err),
					fmt.Errorf("queue push after realtime failure: %w", queueErr),
				)
			}
			c.observer.RecordIncomingCallTransition(
				notification.IncomingCallStatusRealtimeDispatched,
				notification.IncomingCallStatusPushQueued,
				"realtime_failed",
			)
			continue
		}
		c.observer.RecordIncomingCallTransition(
			incomingCallPendingStatus,
			notification.IncomingCallStatusRealtimeDispatched,
			"online",
		)
	}
	return nil
}

func (c *IncomingCallDeliveryCoordinator) AckPresentation(
	ctx context.Context,
	personaID string,
	deviceID string,
	deliveryKey string,
) (notification.AckIncomingCallPresentationResult, error) {
	result, err := c.store.AckIncomingCallPresentation(
		ctx,
		strings.TrimSpace(personaID),
		strings.TrimSpace(deviceID),
		strings.TrimSpace(deliveryKey),
		c.now().UTC(),
	)
	if err == nil {
		c.observer.RecordIncomingCallAck(result.Raced)
	}
	return result, err
}

func (c *IncomingCallDeliveryCoordinator) ProcessDue(
	ctx context.Context,
) (bool, error) {
	now := c.now().UTC()
	if _, err := c.store.ExpireIncomingCallJobs(ctx, now); err != nil {
		return false, fmt.Errorf("expire incoming call jobs: %w", err)
	}
	queued, err := c.store.QueueExpiredRealtimeDispatches(ctx, now)
	if err != nil {
		return false, fmt.Errorf("queue unacknowledged incoming call jobs: %w", err)
	}
	for index := int64(0); index < queued; index++ {
		c.observer.RecordIncomingCallTransition(
			notification.IncomingCallStatusRealtimeDispatched,
			notification.IncomingCallStatusPushQueued,
			"ack_timeout",
		)
	}
	job, err := c.store.ClaimIncomingCallPush(ctx, now)
	if err != nil || job == nil {
		return false, err
	}
	externalID, err := c.push.SubmitIncomingCall(ctx, *job)
	if err != nil {
		c.observer.RecordIncomingCallTransition(
			notification.IncomingCallStatusPushQueued,
			notification.IncomingCallStatusPushQueued,
			"external_accept_failure",
		)
		requeueErr := c.store.RequeueIncomingCallPush(
			ctx,
			job.ID,
			job.Version,
			now,
		)
		return true, errors.Join(err, requeueErr)
	}
	if err := c.store.MarkIncomingCallSentUnconfirmed(
		ctx,
		job.ID,
		job.Version,
		externalID,
		now,
	); err != nil {
		return true, err
	}
	c.observer.RecordIncomingCallTransition(
		notification.IncomingCallStatusPushQueued,
		notification.IncomingCallStatusSentUnconfirmed,
		"accepted",
	)
	return true, nil
}

func (c *IncomingCallDeliveryCoordinator) HandleCancellation(
	ctx context.Context,
	event notification.IncomingCallCancellationEvent,
) error {
	if strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.CallID) == "" {
		return errors.New("incoming call cancellation requires eventId and callId")
	}
	if event.EventType != "CallAnswered" && event.EventType != "CallEnded" {
		return errors.New("incoming call cancellation eventType is invalid")
	}
	if event.OccurredAt.IsZero() {
		return errors.New("incoming call cancellation occurredAt is required")
	}
	now := c.now().UTC()
	if event.OccurredAt.After(now.Add(5 * time.Minute)) {
		return errors.New("incoming call cancellation occurredAt is too far in the future")
	}
	works, err := c.store.CancelIncomingCallJobs(
		ctx,
		event,
		now,
	)
	if err != nil {
		return err
	}
	var errs []error
	realtimeByPersona := make(map[string]notification.IncomingCallDeliveryJob)
	for _, work := range works {
		if work.RealtimeDispatchRequired {
			realtimeByPersona[work.Job.TargetPersonaID] = work.Job
		}
	}
	for _, work := range works {
		if !work.PushDispatchRequired {
			continue
		}
		externalID, err := c.push.SubmitIncomingCallCancellation(ctx, work.Job)
		if err != nil {
			errs = append(errs, err)
			continue
		}
		if err := c.store.MarkIncomingCallCancellationPushSubmitted(
			ctx,
			work.Job.ID,
			work.Job.Version,
			externalID,
			now,
		); err != nil {
			errs = append(errs, err)
		}
	}
	for personaID, job := range realtimeByPersona {
		cancellation := cancellationEventFromJob(job)
		if err := c.realtime.DispatchCancellation(
			ctx,
			personaID,
			cancellation,
		); err != nil {
			errs = append(errs, err)
			continue
		}
		if err := c.store.MarkIncomingCallCancellationRealtimeDispatched(
			ctx,
			job.CallID,
			personaID,
			job.CancellationEventID,
			now,
		); err != nil {
			errs = append(errs, err)
		}
	}
	return errors.Join(errs...)
}

func cancellationEventFromJob(
	job notification.IncomingCallDeliveryJob,
) notification.IncomingCallCancellationEvent {
	occurredAt := job.CancelledAt
	if job.CancellationOccurredAt != nil {
		occurredAt = job.CancellationOccurredAt
	}
	event := notification.IncomingCallCancellationEvent{
		EventID:   job.CancellationEventID,
		EventType: job.CancellationEventType,
		CallID:    job.CallID,
		ActorID:   job.CancellationActorID,
	}
	if occurredAt != nil {
		event.OccurredAt = occurredAt.UTC()
	}
	return event
}

func validateIncomingCallRingingEvent(
	event notification.IncomingCallRingingEvent,
) error {
	required := map[string]string{
		"eventId":         event.EventID,
		"callId":          event.CallID,
		"targetPersonaId": event.TargetPersonaID,
		"callType":        event.CallType,
		"callerName":      event.CallerName,
		"sourceLabel":     event.SourceLabel,
		"trustRelation":   event.TrustRelation,
		"deliveryKey":     event.DeliveryKey,
	}
	for field, value := range required {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("incoming call %s is required", field)
		}
	}
	if event.ExpiresAt.IsZero() {
		return errors.New("incoming call expiresAt is required")
	}
	if _, err := uuid.Parse(strings.TrimSpace(event.CallID)); err != nil {
		return errors.New("incoming call callId must be an RFC4122 UUID")
	}
	switch strings.TrimSpace(event.CallType) {
	case "audio", "video":
	default:
		return errors.New("incoming call callType is invalid")
	}
	switch strings.TrimSpace(event.TrustRelation) {
	case "known", "possibly_unknown":
	default:
		return errors.New("incoming call trustRelation is invalid")
	}
	sum := sha256.Sum256([]byte(
		strings.TrimSpace(event.CallID) + "\x00" +
			strings.TrimSpace(event.TargetPersonaID),
	))
	expected := "sha256:" + hex.EncodeToString(sum[:])
	if !strings.EqualFold(strings.TrimSpace(event.DeliveryKey), expected) {
		return errors.New("incoming call deliveryKey is not canonical SHA256")
	}
	return nil
}

func normalizePushDestinations(
	destinations []notification.PushDestinationRef,
) []notification.PushDestinationRef {
	seen := make(map[string]struct{}, len(destinations))
	normalized := make([]notification.PushDestinationRef, 0, len(destinations))
	for _, destination := range destinations {
		destination.DeviceID = strings.TrimSpace(destination.DeviceID)
		destination.EndpointRef = strings.TrimSpace(destination.EndpointRef)
		if destination.DeviceID == "" || destination.EndpointRef == "" {
			continue
		}
		key := destination.DeviceID + "\x00" + destination.EndpointRef
		if _, exists := seen[key]; exists {
			continue
		}
		seen[key] = struct{}{}
		normalized = append(normalized, destination)
	}
	return normalized
}
