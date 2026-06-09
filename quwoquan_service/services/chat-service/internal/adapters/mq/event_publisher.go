package mq

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	event "quwoquan_service/services/chat-service/internal/domain/conversation/event"
)

// DomainEvent represents a domain event published by the chat service.
type DomainEvent struct {
	Type           string         `json:"type"`
	ConversationID string         `json:"conversationId"`
	ActorID        string         `json:"actorId,omitempty"`
	Timestamp      time.Time      `json:"timestamp"`
	Payload        map[string]any `json:"payload,omitempty"`
}

func (e DomainEvent) channel() string {
	return fmt.Sprintf("rt:conversation:%s", e.ConversationID)
}

// SupportedEventTypes lists all event types published by the chat service.
var SupportedEventTypes = []string{
	event.MessageSent,
	event.MessageRecalled,
	event.MemberJoined,
	event.ConversationRosterUpdated,
	event.ConversationAvatarUpdated,
	event.MemberLeft,
	event.ConversationCreated,
	event.ConversationSettingsUpdated,
	event.ReadReceiptSent,
	event.AssistantInvited,
	event.AssistantMentioned,
	EventAssistantRemoved,
}

const EventAssistantRemoved = "AssistantRemoved"
const AssistantMentionedStream = "events.chat.assistant_mentions"

// EventPublisher publishes domain events to Redis Pub/Sub channels.
// Channel format: rt:conversation:{conversationId}
type EventPublisher struct {
	client rtredis.Client
}

func NewEventPublisher(client rtredis.Client) *EventPublisher {
	return &EventPublisher{client: client}
}

// Publish serializes the event and publishes it to the conversation's channel.
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

// PublishBatch publishes multiple events sequentially. Stops on first error.
func (p *EventPublisher) PublishBatch(ctx context.Context, events []DomainEvent) error {
	for i := range events {
		if err := p.Publish(ctx, events[i]); err != nil {
			return fmt.Errorf("publish event[%d] type=%s: %w", i, events[i].Type, err)
		}
	}
	return nil
}

// PublishDomainEvent satisfies application.EventPublisher interface,
// bridging the application layer abstraction to the concrete Redis Pub/Sub
// implementation without the application needing to import this package.
func (p *EventPublisher) PublishDomainEvent(ctx context.Context, eventType, conversationId, actorId string, payload map[string]any) error {
	evt := DomainEvent{
		Type:           eventType,
		ConversationID: conversationId,
		ActorID:        actorId,
		Payload:        payload,
	}
	if err := p.Publish(ctx, evt); err != nil {
		return err
	}
	if eventType == event.AssistantMentioned {
		if _, err := p.client.XAdd(ctx, AssistantMentionedStream, assistantMentionedStreamValues(evt)); err != nil {
			return fmt.Errorf("publish assistant mentioned stream: %w", err)
		}
	}
	return nil
}

func assistantMentionedStreamValues(evt DomainEvent) map[string]string {
	values := map[string]string{
		"eventType":      evt.Type,
		"conversationId": evt.ConversationID,
		"actorId":        evt.ActorID,
		"occurredAt":     evt.Timestamp.Format(time.RFC3339Nano),
	}
	for key, value := range evt.Payload {
		values[key] = streamString(value)
	}
	return values
}

func streamString(value any) string {
	switch v := value.(type) {
	case string:
		return v
	case fmt.Stringer:
		return v.String()
	case int:
		return strconv.Itoa(v)
	case int64:
		return strconv.FormatInt(v, 10)
	case float64:
		return strconv.FormatFloat(v, 'f', -1, 64)
	case bool:
		return strconv.FormatBool(v)
	default:
		raw, err := json.Marshal(v)
		if err != nil {
			return fmt.Sprint(v)
		}
		return string(raw)
	}
}
