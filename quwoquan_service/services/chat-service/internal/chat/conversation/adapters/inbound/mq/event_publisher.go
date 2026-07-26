package mq

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	conversationevent "quwoquan_service/services/chat-service/generated/chat/conversation/contract/event"
	membershipevent "quwoquan_service/services/chat-service/generated/chat/conversation_membership/contract/event"
	userstateevent "quwoquan_service/services/chat-service/generated/chat/conversation_user_state/contract/event"
	messageevent "quwoquan_service/services/chat-service/generated/chat/message/contract/event"
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

// SupportedEventTypes lists all event types published by the chat service.
var SupportedEventTypes = []string{
	conversationevent.ConversationCreated,
	conversationevent.ConversationRosterUpdated,
	conversationevent.ConversationAvatarUpdated,
	conversationevent.ConversationDissolved,
	membershipevent.ConversationMemberAdded,
	membershipevent.ConversationMemberRemoved,
	membershipevent.ConversationMemberLeft,
	membershipevent.ConversationMemberRoleChanged,
	userstateevent.ConversationReadWatermarkAdvanced,
	userstateevent.ConversationUserSettingsChanged,
	messageevent.MessageSent,
	messageevent.MessageRecalled,
	messageevent.AssistantMentioned,
}

const AssistantMentionedStream = "events.chat.assistant_mentions"

const (
	recipientCacheTTL        = 30 * time.Second
	recipientCacheMaxEntries = 4096
)

// ConversationRecipientResolver 返回会话事件的实时接收者（活跃成员）。
// realtime-gateway 按可信身份只订阅 rt:user:{userId}，因此授权语义
// （谁能收到会话事件）留在拥有成员数据的 chat-service 发布端。
type ConversationRecipientResolver interface {
	ResolveRecipients(ctx context.Context, conversationID string) ([]string, error)
}

// EventPublisher 发布实时扇出事件与持久跨服务事件。
// 具体 Redis client 只在 runtime MessageTransport 内部，业务 adapter 不直接选择 scene。
type EventPublisher struct {
	transport runtimemessaging.MessageTransport
	resolver  ConversationRecipientResolver

	mu    sync.Mutex
	cache map[string]recipientCacheEntry
}

type recipientCacheEntry struct {
	recipients []string
	expiresAt  time.Time
}

func NewEventPublisher(
	realtimeClient rtredis.Client,
	durableClient rtredis.Client,
	resolver ConversationRecipientResolver,
) *EventPublisher {
	transport, err := runtimemessaging.NewRedisMessageTransport(realtimeClient, durableClient)
	if err != nil {
		panic(err)
	}
	return NewEventPublisherWithTransport(transport, resolver)
}

// NewEventPublisherWithTransport is the production composition entrypoint.
// It accepts the preflighted provider-neutral MessageTransport rather than raw
// Redis clients, keeping stream selection inside the registered runtime adapter.
func NewEventPublisherWithTransport(
	transport runtimemessaging.MessageTransport,
	resolver ConversationRecipientResolver,
) *EventPublisher {
	if transport == nil || resolver == nil {
		panic("chat event publisher requires realtime, durable and recipient dependencies")
	}
	return &EventPublisher{
		transport: transport,
		resolver:  resolver,
		cache:     map[string]recipientCacheEntry{},
	}
}

// Publish serializes the event and fans it out to each recipient's channel.
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
	if rosterMutatingEventTypes[evt.Type] {
		p.invalidateRecipients(evt.ConversationID)
	}
	recipients, err := p.recipients(ctx, evt.ConversationID)
	if err != nil {
		return fmt.Errorf("resolve recipients for %s: %w", evt.ConversationID, err)
	}
	recipients = recipientsForEvent(recipients, evt)
	for _, userID := range recipients {
		if err := p.transport.PublishEphemeral(
			ctx,
			runtimemessaging.EphemeralMessage{
				Channel: "rt:user:" + userID,
				Payload: payload,
			},
		); err != nil {
			return fmt.Errorf("publish to rt:user:%s: %w", userID, err)
		}
	}
	return nil
}

// rosterMutatingEventTypes 触发接收者缓存失效：新成员必须立即可达，
// 被移除成员不得继续收到后续事件。
var rosterMutatingEventTypes = map[string]bool{
	membershipevent.ConversationMemberAdded:       true,
	membershipevent.ConversationMemberRemoved:     true,
	membershipevent.ConversationMemberLeft:        true,
	conversationevent.ConversationRosterUpdated:   true,
	membershipevent.ConversationMemberRoleChanged: true,
}

// recipientsForEvent preserves the post-mutation active roster and explicitly
// adds the affected user for a terminal membership event. The resolver runs
// after the transaction, so a removed/left user is no longer in that roster;
// without this supplement their app would retain private local conversation
// and offline-search data indefinitely.
func recipientsForEvent(activeRecipients []string, evt DomainEvent) []string {
	seen := make(map[string]struct{}, len(activeRecipients)+1)
	recipients := make([]string, 0, len(activeRecipients)+1)
	appendRecipient := func(raw string) {
		userID := strings.TrimSpace(raw)
		if userID == "" {
			return
		}
		if _, exists := seen[userID]; exists {
			return
		}
		seen[userID] = struct{}{}
		recipients = append(recipients, userID)
	}
	for _, userID := range activeRecipients {
		appendRecipient(userID)
	}
	if evt.Type == membershipevent.ConversationMemberRemoved ||
		evt.Type == membershipevent.ConversationMemberLeft {
		appendRecipient(stringPayload(evt.Payload, "userId"))
	}
	return recipients
}

func stringPayload(payload map[string]any, key string) string {
	if payload == nil {
		return ""
	}
	value, _ := payload[key].(string)
	return value
}

func (p *EventPublisher) recipients(
	ctx context.Context,
	conversationID string,
) ([]string, error) {
	conversationID = strings.TrimSpace(conversationID)
	if conversationID == "" {
		return nil, errors.New("conversation id is required")
	}
	now := time.Now()
	p.mu.Lock()
	if entry, ok := p.cache[conversationID]; ok && entry.expiresAt.After(now) {
		cached := entry.recipients
		p.mu.Unlock()
		return cached, nil
	}
	p.mu.Unlock()

	recipients, err := p.resolver.ResolveRecipients(ctx, conversationID)
	if err != nil {
		return nil, err
	}
	p.mu.Lock()
	if len(p.cache) >= recipientCacheMaxEntries {
		p.cache = map[string]recipientCacheEntry{}
	}
	p.cache[conversationID] = recipientCacheEntry{
		recipients: recipients,
		expiresAt:  now.Add(recipientCacheTTL),
	}
	p.mu.Unlock()
	return recipients, nil
}

func (p *EventPublisher) invalidateRecipients(conversationID string) {
	p.mu.Lock()
	delete(p.cache, strings.TrimSpace(conversationID))
	p.mu.Unlock()
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
// bridging the application layer abstraction to the injected runtime
// MessageTransport without the application needing to import this package.
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
		if _, err := p.transport.AppendDurable(
			ctx,
			assistantMentionedDurableMessage(evt),
		); err != nil {
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
		if _, err := p.transport.AppendDurable(
			ctx,
			assistantMentionedDurableMessage(evt),
		); err != nil {
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

func assistantMentionedDurableMessage(evt DomainEvent) runtimemessaging.DurableMessage {
	values := assistantMentionedStreamValues(evt)
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	fields := make([]runtimemessaging.DurableField, 0, len(keys))
	for _, key := range keys {
		fields = append(fields, runtimemessaging.DurableField{Name: key, Value: values[key]})
	}
	return runtimemessaging.DurableMessage{
		Stream: AssistantMentionedStream,
		Fields: fields,
	}
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
