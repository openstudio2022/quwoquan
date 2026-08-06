package realtime

import (
	"context"
	"errors"
	"strings"
	"time"

	"quwoquan_service/runtime/clientrealtime"
	runtimemessaging "quwoquan_service/runtime/messaging"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
)

type IncomingCallPublisher struct {
	transport runtimemessaging.MessageTransport
}

type rtcRingingSignalPayload struct {
	EventID         string `json:"eventId"`
	CallID          string `json:"callId"`
	TargetPersonaID string `json:"targetPersonaId"`
	CallType        string `json:"callType"`
	CallerName      string `json:"callerName"`
	CallerAvatarURL string `json:"callerAvatarUrl"`
	SourceLabel     string `json:"sourceLabel"`
	TrustRelation   string `json:"trustRelation"`
	ExpiresAt       string `json:"expiresAt"`
	DeliveryKey     string `json:"deliveryKey"`
}

type rtcCancellationSignalPayload struct {
	CallID string `json:"callId"`
	UserID string `json:"userId,omitempty"`
}

func NewIncomingCallPublisher(
	transport runtimemessaging.MessageTransport,
) (*IncomingCallPublisher, error) {
	if transport == nil {
		return nil, errors.New(
			"incoming call realtime publisher requires message transport",
		)
	}
	return &IncomingCallPublisher{transport: transport}, nil
}

func (p *IncomingCallPublisher) DispatchIncomingCall(
	ctx context.Context,
	job notification.IncomingCallDeliveryJob,
) error {
	if job.CreatedAt.IsZero() {
		return errors.New("incoming call realtime signal timestamp is required")
	}
	clientSignal, err := clientrealtime.MarshalClientRealtimeEventEnvelope(
		"call.ringing",
		strings.TrimSpace(job.EventID),
		job.CreatedAt,
		rtcRingingSignalPayload{
			EventID:         strings.TrimSpace(job.EventID),
			CallID:          strings.TrimSpace(job.CallID),
			TargetPersonaID: strings.TrimSpace(job.TargetPersonaID),
			CallType:        strings.TrimSpace(job.CallType),
			CallerName:      strings.TrimSpace(job.CallerName),
			CallerAvatarURL: strings.TrimSpace(job.CallerAvatarURL),
			SourceLabel:     strings.TrimSpace(job.SourceLabel),
			TrustRelation:   strings.TrimSpace(job.TrustRelation),
			ExpiresAt:       job.ExpiresAt.UTC().Format(time.RFC3339Nano),
			DeliveryKey:     strings.TrimSpace(job.DeliveryKey),
		},
	)
	if err != nil {
		return err
	}
	payload, err := runtimemessaging.WrapTargetedEphemeralPayload(
		runtimemessaging.EphemeralRoutingTarget{
			PersonaID: job.TargetPersonaID,
			DeviceID:  job.DeviceID,
		},
		clientSignal,
	)
	if err != nil {
		return err
	}
	return p.transport.PublishEphemeral(
		ctx,
		runtimemessaging.EphemeralMessage{
			Channel: "rt:rtc:persona:" + strings.TrimSpace(job.TargetPersonaID),
			Payload: payload,
		},
	)
}

func (p *IncomingCallPublisher) DispatchCancellation(
	ctx context.Context,
	personaID string,
	event notification.IncomingCallCancellationEvent,
) error {
	if event.OccurredAt.IsZero() {
		return errors.New("incoming call cancellation signal timestamp is required")
	}
	wireType := ""
	payload := rtcCancellationSignalPayload{CallID: strings.TrimSpace(event.CallID)}
	switch strings.TrimSpace(event.EventType) {
	case "CallAnswered":
		wireType = "call.answered"
		payload.UserID = strings.TrimSpace(event.ActorID)
	case "CallEnded":
		wireType = "call.ended"
	default:
		return errors.New("incoming call cancellation event type is unsupported")
	}
	clientSignal, err := clientrealtime.MarshalClientRealtimeEventEnvelope(
		wireType,
		strings.TrimSpace(event.EventID),
		event.OccurredAt,
		payload,
	)
	if err != nil {
		return err
	}
	return p.transport.PublishEphemeral(
		ctx,
		runtimemessaging.EphemeralMessage{
			Channel: "rt:rtc:persona:" + strings.TrimSpace(personaID),
			Payload: clientSignal,
		},
	)
}
