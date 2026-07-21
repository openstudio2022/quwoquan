package realtime

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	notification "quwoquan_service/services/notification-service/internal/domain/notification"
)

type IncomingCallPublisher struct {
	transport runtimemessaging.MessageTransport
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
	payload, err := json.Marshal(map[string]string{
		"type":            "call.ringing",
		"eventId":         job.EventID,
		"callId":          job.CallID,
		"targetPersonaId": job.TargetPersonaID,
		"deviceId":        job.DeviceID,
		"deliveryKey":     job.DeliveryKey,
		"callType":        job.CallType,
		"callerName":      job.CallerName,
		"callerAvatarUrl": job.CallerAvatarURL,
		"sourceLabel":     job.SourceLabel,
		"trustRelation":   job.TrustRelation,
		"expiresAt":       job.ExpiresAt.UTC().Format(time.RFC3339Nano),
	})
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
	payload, err := json.Marshal(map[string]string{
		"type":      "call.presentation_cancelled",
		"eventId":   event.EventID,
		"eventType": event.EventType,
		"callId":    event.CallID,
		"actorId":   event.ActorID,
	})
	if err != nil {
		return err
	}
	return p.transport.PublishEphemeral(
		ctx,
		runtimemessaging.EphemeralMessage{
			Channel: "rt:rtc:persona:" + strings.TrimSpace(personaID),
			Payload: payload,
		},
	)
}
