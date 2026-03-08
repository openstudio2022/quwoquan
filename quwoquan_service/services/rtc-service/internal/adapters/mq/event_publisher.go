package mq

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	event "quwoquan_service/services/rtc-service/internal/domain/call_session/event"
)

// DomainEvent represents a domain event published by the rtc service.
type DomainEvent struct {
	Type    string         `json:"type"`
	CallID  string         `json:"callId"`
	ActorID string         `json:"actorId,omitempty"`
	Timestamp time.Time    `json:"timestamp"`
	Payload map[string]any `json:"payload,omitempty"`
}

func (e DomainEvent) channel() string {
	return fmt.Sprintf("rt:rtc:call:%s", e.CallID)
}

// SupportedEventTypes lists all event types published by the rtc service.
var SupportedEventTypes = []string{
	event.CallInitiated,
	event.CallRinging,
	event.CallAnswered,
	event.CallConnected,
	event.CallEnded,
	event.ParticipantJoined,
	event.ParticipantLeft,
	event.CallRecordingStarted,
	event.CallRecordingStopped,
	event.ScreenShareStarted,
	event.ScreenShareStopped,
}

// EventPublisher publishes domain events to Redis Pub/Sub channels.
// Channel format: rt:rtc:call:{callId}
type EventPublisher struct {
	client rtredis.Client
}

func NewEventPublisher(client rtredis.Client) *EventPublisher {
	return &EventPublisher{client: client}
}

func (p *EventPublisher) Publish(ctx context.Context, evt DomainEvent) error {
	if evt.Timestamp.IsZero() {
		evt.Timestamp = time.Now()
	}
	payload, err := json.Marshal(evt)
	if err != nil {
		return fmt.Errorf("marshal event: %w", err)
	}
	return p.client.Publish(ctx, evt.channel(), string(payload))
}

func (p *EventPublisher) PublishBatch(ctx context.Context, events []DomainEvent) error {
	for i := range events {
		if err := p.Publish(ctx, events[i]); err != nil {
			return fmt.Errorf("publish event[%d] type=%s: %w", i, events[i].Type, err)
		}
	}
	return nil
}
