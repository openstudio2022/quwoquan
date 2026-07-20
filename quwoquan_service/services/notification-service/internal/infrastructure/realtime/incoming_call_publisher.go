package realtime

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	notification "quwoquan_service/services/notification-service/internal/domain/notification"
)

type IncomingCallPublisher struct {
	redis rtredis.Client
}

func NewIncomingCallPublisher(
	client rtredis.Client,
) (*IncomingCallPublisher, error) {
	if client == nil {
		return nil, errors.New(
			"incoming call realtime publisher requires Redis",
		)
	}
	return &IncomingCallPublisher{redis: client}, nil
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
	return p.redis.Publish(
		ctx,
		"rt:rtc:persona:"+strings.TrimSpace(job.TargetPersonaID),
		string(payload),
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
	return p.redis.Publish(
		ctx,
		"rt:rtc:persona:"+strings.TrimSpace(personaID),
		string(payload),
	)
}
