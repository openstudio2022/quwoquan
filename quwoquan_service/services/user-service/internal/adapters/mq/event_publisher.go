package mq

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/user-service/internal/application"
	accountports "quwoquan_service/services/user-service/internal/domain/account/user_account/ports"
	relmodel "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/model"
	sfmodel "quwoquan_service/services/user-service/internal/domain/relationship/subject_follow/model"
)

const PersonaRelationshipEventStream = "events.user.persona_relationship"

const SubjectFollowEventStream = "events.user.subject_follow"

const GreetingEventStream = "events.user.greeting"

const UserAccountEventStream = "events.user.account"

type DomainEvent struct {
	Type      string         `json:"type"`
	UserID    string         `json:"userId"`
	ActorID   string         `json:"actorId,omitempty"`
	Timestamp time.Time      `json:"timestamp"`
	Payload   map[string]any `json:"payload,omitempty"`
}

type EventPublisher struct {
	client rtredis.Client
}

func NewEventPublisher(client rtredis.Client) *EventPublisher {
	return &EventPublisher{client: client}
}

func (p *EventPublisher) PublishUserEvent(
	ctx context.Context,
	eventType, userID, actorID string,
	payload map[string]any,
) error {
	if p == nil || p.client == nil {
		return nil
	}
	event := DomainEvent{
		Type:      eventType,
		UserID:    userID,
		ActorID:   actorID,
		Timestamp: time.Now().UTC(),
		Payload:   payload,
	}
	body, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("marshal user event: %w", err)
	}
	return p.client.Publish(ctx, "event:user-profile", string(body))
}

// AppendUserAccountClosed 写 durable stream。消费者必须按 eventId 去重；
// 发布确认丢失时 relay 会安全重放。
func (p *EventPublisher) AppendUserAccountClosed(
	ctx context.Context,
	event accountports.CloseOutboxEvent,
	payload map[string]any,
) error {
	if p == nil || p.client == nil {
		return fmt.Errorf("UserAccount event publisher is unavailable")
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal UserAccountClosed payload: %w", err)
	}
	if _, err := p.client.XAdd(ctx, UserAccountEventStream, map[string]string{
		"eventId":        event.EventID,
		"eventName":      event.EventType,
		"accountId":      event.AccountID,
		"accountVersion": strconv.FormatInt(event.AccountVersion, 10),
		"payload":        string(body),
		"occurredAt":     event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}); err != nil {
		return fmt.Errorf("append UserAccount event stream: %w", err)
	}
	return nil
}

// PublishPersonaRelationship writes the replayable relationship stream before
// emitting the existing realtime user event. The relationship outbox is marked
// delivered only after this method returns, so recommendation projections never
// rely on lossy Pub/Sub delivery.
func (p *EventPublisher) PublishPersonaRelationship(ctx context.Context, event relmodel.OutboxEvent) error {
	if p == nil || p.client == nil {
		return fmt.Errorf("persona relationship event publisher is unavailable")
	}
	payload := event.Payload
	if event.EventID == "" || event.EventName == "" || payload.PairID == "" ||
		payload.SourcePersonaID == "" || payload.TargetPersonaID == "" || payload.Version <= 0 {
		return fmt.Errorf("invalid persona relationship event")
	}
	values := map[string]string{
		"eventId":         event.EventID,
		"eventName":       event.EventName,
		"pairId":          payload.PairID,
		"sourcePersonaId": payload.SourcePersonaID,
		"targetPersonaId": payload.TargetPersonaID,
		"following":       strconv.FormatBool(payload.Following),
		"version":         strconv.FormatInt(payload.Version, 10),
		"occurredAt":      payload.OccurredAt.UTC().Format(time.RFC3339Nano),
	}
	if payload.ClearedFollowDirections > 0 {
		values["clearedFollowDirections"] = strconv.Itoa(payload.ClearedFollowDirections)
	}
	if payload.SourceFollowCleared {
		values["sourceFollowCleared"] = strconv.FormatBool(true)
	}
	if payload.TargetFollowCleared {
		values["targetFollowCleared"] = strconv.FormatBool(true)
	}
	if _, err := p.client.XAdd(ctx, PersonaRelationshipEventStream, values); err != nil {
		return fmt.Errorf("append persona relationship stream: %w", err)
	}
	return p.PublishUserEvent(
		ctx,
		event.EventName,
		payload.TargetPersonaID,
		payload.SourcePersonaID,
		relationshipRealtimePayload(event),
	)
}

// PublishGreetingEvent appends the replayable greeting stream consumed by
// notification-service. Delivery is at-least-once; consumers dedupe by eventId.
func (p *EventPublisher) PublishGreetingEvent(
	ctx context.Context,
	event application.GreetingStreamEvent,
) error {
	if p == nil || p.client == nil {
		return fmt.Errorf("greeting event publisher is unavailable")
	}
	if event.EventID == "" || event.EventName == "" || event.GreetingID == "" ||
		event.RequesterSubAccountID == "" || event.TargetSubAccountID == "" ||
		event.OccurredAt.IsZero() {
		return fmt.Errorf("invalid greeting event")
	}
	values := map[string]string{
		"eventId":                      event.EventID,
		"eventName":                    event.EventName,
		"id":                           event.GreetingID,
		"requesterSubAccountId":        event.RequesterSubAccountID,
		"targetSubAccountId":           event.TargetSubAccountID,
		"targetAllowsStrangerGreeting": strconv.FormatBool(event.TargetAllowsStrangerGreeting),
		"occurredAt":                   event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}
	if event.Source != "" {
		values["source"] = event.Source
	}
	if event.PromotedConversationID != "" {
		values["promotedConversationId"] = event.PromotedConversationID
	}
	if _, err := p.client.XAdd(ctx, GreetingEventStream, values); err != nil {
		return fmt.Errorf("append greeting stream: %w", err)
	}
	return nil
}

// PublishSubjectFollow appends the replayable subject follow stream consumed
// by entity-service (homepage follower projection), circle-service and the
// recommendation engine. The subject follow outbox is marked delivered only
// after this method returns.
func (p *EventPublisher) PublishSubjectFollow(ctx context.Context, event sfmodel.OutboxEvent) error {
	if p == nil || p.client == nil {
		return fmt.Errorf("subject follow event publisher is unavailable")
	}
	payload := event.Payload
	if event.EventID == "" || event.EventName == "" || payload.ID == "" ||
		payload.PersonaID == "" || payload.SubjectID == "" || payload.Version <= 0 {
		return fmt.Errorf("invalid subject follow event")
	}
	values := map[string]string{
		"eventId":     event.EventID,
		"eventName":   event.EventName,
		"id":          payload.ID,
		"personaId":   payload.PersonaID,
		"subjectType": payload.SubjectType,
		"subjectId":   payload.SubjectID,
		"state":       payload.State,
		"version":     strconv.FormatInt(payload.Version, 10),
		"occurredAt":  payload.OccurredAt.UTC().Format(time.RFC3339Nano),
	}
	if _, err := p.client.XAdd(ctx, SubjectFollowEventStream, values); err != nil {
		return fmt.Errorf("append subject follow stream: %w", err)
	}
	return nil
}

// relationshipRealtimePayload only adapts the typed relationship event to the
// existing generic user-event envelope at the process boundary.
func relationshipRealtimePayload(event relmodel.OutboxEvent) map[string]any {
	payload := event.Payload
	result := map[string]any{
		"eventId":         event.EventID,
		"pairId":          payload.PairID,
		"sourcePersonaId": payload.SourcePersonaID,
		"targetPersonaId": payload.TargetPersonaID,
		"following":       payload.Following,
		"version":         payload.Version,
		"occurredAt":      payload.OccurredAt.UTC().Format(time.RFC3339Nano),
	}
	if payload.ClearedFollowDirections > 0 {
		result["clearedFollowDirections"] = payload.ClearedFollowDirections
	}
	if payload.SourceFollowCleared {
		result["sourceFollowCleared"] = true
	}
	if payload.TargetFollowCleared {
		result["targetFollowCleared"] = true
	}
	return result
}
