package mq

import (
	"context"
	"fmt"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/rtc-service/internal/application"
	event "quwoquan_service/services/rtc-service/internal/domain/call_session/event"
)

var rtcCallRelayTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "rtc_call_outbox_relay_total",
		Help: "RTC CallSession outbox relay outcomes by event and transport.",
	},
	[]string{"event_type", "transport", "outcome"},
)

var _ application.CallRealtimePublisher = (*RealtimePublisher)(nil)

const (
	RtcCallRingingStream  = "events.rtc.call_ringing"
	RtcCallAnsweredStream = "events.rtc.call_answered"
	RtcCallEndedStream    = "events.rtc.call_ended"
)

// SupportedEventTypes lists all realtime event types published by rtc-service.
var SupportedEventTypes = []string{
	event.CallInitiated,
	event.CallRinging,
	event.CallAnswered,
	event.CallConnected,
	event.CallEnded,
	event.ParticipantJoined,
	event.ParticipantLeft,
	event.ScreenShareStarted,
	event.ScreenShareStopped,
}

// RealtimePublisher 承担 CallSession outbox 的唯一 relay：
//   - CallRinging 只进入 durable stream，由 notification-service 做设备级
//     realtime→ACK grace→push 协调，禁止 RTC 无条件双投递；
//   - 其余信令发布到 rt:rtc:persona:{personaId}；
//   - CallAnswered/CallEnded 同时进入 durable cancellation stream。
type RealtimePublisher struct {
	transport runtimemessaging.MessageTransport
}

func NewRealtimePublisher(transport runtimemessaging.MessageTransport) *RealtimePublisher {
	return &RealtimePublisher{transport: transport}
}

func (p *RealtimePublisher) PublishToPersonas(
	ctx context.Context,
	personaIDs []string,
	wireType string,
	evt application.CallOutboxEvent,
) error {
	if stream := durableStream(evt.EventType); stream != "" {
		if _, err := p.transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
			Stream: stream,
			Fields: []runtimemessaging.DurableField{
				{Name: "eventId", Value: evt.EventID},
				{Name: "eventType", Value: evt.EventType},
				{Name: "wireType", Value: wireType},
				{Name: "callId", Value: evt.AggregateID},
				{Name: "deliveryKey", Value: evt.DeliveryKey},
				{Name: "occurredAt", Value: evt.OccurredAt.UTC().Format(time.RFC3339Nano)},
				{Name: "payloadJson", Value: string(evt.Payload)},
			},
		}); err != nil {
			rtcCallRelayTotal.WithLabelValues(
				evt.EventType,
				"durable_stream",
				"failure",
			).Inc()
			return fmt.Errorf("append rtc %s stream: %w", evt.EventType, err)
		}
		rtcCallRelayTotal.WithLabelValues(
			evt.EventType,
			"durable_stream",
			"success",
		).Inc()
	}
	if evt.EventType == event.CallRinging {
		return nil
	}

	seen := make(map[string]struct{}, len(personaIDs))
	for _, personaID := range personaIDs {
		if personaID == "" {
			continue
		}
		if _, ok := seen[personaID]; ok {
			continue
		}
		seen[personaID] = struct{}{}
		if err := p.transport.PublishEphemeral(
			ctx,
			runtimemessaging.EphemeralMessage{
				Channel: "rt:rtc:persona:" + personaID,
				Payload: evt.Payload,
			},
		); err != nil {
			rtcCallRelayTotal.WithLabelValues(
				evt.EventType,
				"persona_realtime",
				"failure",
			).Inc()
			return fmt.Errorf(
				"publish rtc event to rt:rtc:persona:%s: %w",
				personaID,
				err,
			)
		}
		rtcCallRelayTotal.WithLabelValues(
			evt.EventType,
			"persona_realtime",
			"success",
		).Inc()
	}
	return nil
}

func durableStream(eventType string) string {
	switch eventType {
	case event.CallRinging:
		return RtcCallRingingStream
	case event.CallAnswered:
		return RtcCallAnsweredStream
	case event.CallEnded:
		return RtcCallEndedStream
	default:
		return ""
	}
}
