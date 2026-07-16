package mq

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	membershipevent "quwoquan_service/services/chat-service/internal/domain/chat/conversation_membership/event"
	userstateevent "quwoquan_service/services/chat-service/internal/domain/chat/conversation_user_state/event"
	conversationevent "quwoquan_service/services/chat-service/internal/domain/chat/event"
	messageevent "quwoquan_service/services/chat-service/internal/domain/chat/message/event"
)

// DomainEvent represents a domain event published by the chat service.
type DomainEvent struct {
	EventID        string         `json:"eventId,omitempty"`
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
	conversationevent.ConversationCreated,
	conversationevent.ConversationRosterUpdated,
	conversationevent.ConversationAvatarUpdated,
	conversationevent.ConversationArchived,
	membershipevent.ConversationMemberAdded,
	membershipevent.ConversationMemberRemoved,
	membershipevent.ConversationMemberRoleChanged,
	userstateevent.ConversationReadWatermarkAdvanced,
	userstateevent.ConversationUserSettingsChanged,
	messageevent.MessageSent,
	messageevent.MessageRecalled,
	messageevent.AssistantMentioned,
}

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
	if !isSupportedEventType(evt.Type) {
		return fmt.Errorf("unsupported chat domain event type %q", evt.Type)
	}
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
	if eventType == messageevent.AssistantMentioned {
		if _, err := p.client.XAdd(ctx, AssistantMentionedStream, assistantMentionedStreamValues(evt)); err != nil {
			return fmt.Errorf("publish assistant mentioned stream: %w", err)
		}
	}
	return nil
}

// PublishRecordedDomainEvent publishes an event whose stable identity comes from
// an aggregate outbox record. Consumers can therefore deduplicate a retry after
// transport success but before the producer marks the outbox row dispatched.
func (p *EventPublisher) PublishRecordedDomainEvent(
	ctx context.Context,
	eventID string,
	eventType string,
	conversationID string,
	actorID string,
	payload map[string]any,
) error {
	if strings.TrimSpace(eventID) == "" {
		return errors.New("recorded domain event id is required")
	}
	evt := DomainEvent{
		EventID:        eventID,
		Type:           eventType,
		ConversationID: conversationID,
		ActorID:        actorID,
		Payload:        payload,
	}
	if err := p.Publish(ctx, evt); err != nil {
		return err
	}
	if eventType == messageevent.AssistantMentioned {
		if _, err := p.client.XAdd(ctx, AssistantMentionedStream, assistantMentionedStreamValues(evt)); err != nil {
			return fmt.Errorf("publish assistant mentioned stream: %w", err)
		}
	}
	return nil
}

func isSupportedEventType(eventType string) bool {
	for _, supported := range SupportedEventTypes {
		if eventType == supported {
			return true
		}
	}
	return false
}

func assistantMentionedStreamValues(evt DomainEvent) map[string]string {
	values := map[string]string{
		"eventId":        evt.EventID,
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
