package mq

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
	greetingapp "quwoquan_service/services/user-service/internal/relationship/greeting_request/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	sfmodel "quwoquan_service/services/user-service/internal/relationship/subject_follow/domain/model"
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
	transport runtimemessaging.MessageTransport
}

// NewEventPublisher accepts the preflighted provider-neutral transport. Object
// topic and stream coordinates remain owned by this adapter.
func NewEventPublisher(transport runtimemessaging.MessageTransport) *EventPublisher {
	if transport == nil {
		panic("user event publisher requires message transport")
	}
	return &EventPublisher{transport: transport}
}

func (p *EventPublisher) PublishUserEvent(
	ctx context.Context,
	eventType, userID, actorID string,
	payload map[string]any,
) error {
	if p == nil || p.transport == nil {
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
	if err := p.transport.PublishEphemeral(ctx, runtimemessaging.EphemeralMessage{
		Channel: "event:user-profile",
		Payload: body,
	}); err != nil {
		return fmt.Errorf("publish user event: %w", err)
	}
	return nil
}

// AppendUserAccountEvent 写 UserAccount 生命周期 durable stream。消费者必须按 eventId
// 去重；UserAccountClosed 走不可逆清理，而 UserSuspended/UserRestored 只能维护可逆
// restriction projection，发布确认丢失时 relay 会安全重放。
func (p *EventPublisher) AppendUserAccountEvent(
	ctx context.Context,
	event accountports.UserAccountOutboxEvent,
	payload map[string]any,
) error {
	if p == nil || p.transport == nil {
		return fmt.Errorf("UserAccount event publisher is unavailable")
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.AccountID) == "" ||
		event.AccountVersion <= 0 || strings.TrimSpace(event.EventType) == "" || event.OccurredAt.IsZero() {
		return fmt.Errorf("UserAccount event identity is invalid")
	}
	body, err := canonicalUserAccountPayload(event, payload)
	if err != nil {
		return fmt.Errorf("marshal UserAccount event payload: %w", err)
	}
	if _, err := p.transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: UserAccountEventStream,
		Fields: []runtimemessaging.DurableField{
			{Name: "eventId", Value: event.EventID},
			{Name: "eventName", Value: event.EventType},
			{Name: "accountId", Value: event.AccountID},
			{Name: "accountVersion", Value: strconv.FormatInt(event.AccountVersion, 10)},
			{Name: "payload", Value: string(body)},
			{Name: "occurredAt", Value: event.OccurredAt.UTC().Format(time.RFC3339Nano)},
		},
	}); err != nil {
		return fmt.Errorf("append UserAccount event stream: %w", err)
	}
	return nil
}

func canonicalUserAccountPayload(
	event accountports.UserAccountOutboxEvent,
	payload map[string]any,
) ([]byte, error) {
	fieldsByEvent := map[string][]string{
		"UserAccountClosed":      {"userId", "personaIds", "accountState", "updatedAt"},
		"UserSuspended":          {"userId", "personaIds", "accountState", "authEpoch", "decisionRef", "occurredAt"},
		"UserRestored":           {"userId", "personaIds", "accountState", "authEpoch", "decisionRef", "occurredAt"},
		"UserProfileTagsChanged": {"userId", "tagRefs", "taxonomyReleaseId", "profileVersion", "occurredAt"},
	}
	fields, supported := fieldsByEvent[event.EventType]
	if !supported {
		return nil, fmt.Errorf("UserAccount event type %q is not canonical", event.EventType)
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("marshal UserAccount event payload: %w", err)
	}
	var source map[string]json.RawMessage
	if err := json.Unmarshal(encoded, &source); err != nil {
		return nil, fmt.Errorf("decode UserAccount event payload: %w", err)
	}
	canonical := make(map[string]json.RawMessage, len(fields))
	for _, field := range fields {
		value, found := source[field]
		if !found || len(value) == 0 || string(value) == "null" {
			return nil, fmt.Errorf("UserAccount %s payload is missing %s", event.EventType, field)
		}
		canonical[field] = value
	}
	var payloadUserID string
	if err := json.Unmarshal(canonical["userId"], &payloadUserID); err != nil || payloadUserID != event.AccountID {
		return nil, fmt.Errorf("UserAccount payload identity does not match aggregate")
	}
	body, err := json.Marshal(canonical)
	if err != nil {
		return nil, fmt.Errorf("marshal UserAccount canonical payload: %w", err)
	}
	return body, nil
}

// PublishPersonaRelationship writes the replayable relationship stream before
// emitting the existing realtime user event. The relationship outbox is marked
// delivered only after this method returns, so recommendation projections never
// rely on lossy Pub/Sub delivery.
func (p *EventPublisher) PublishPersonaRelationship(ctx context.Context, event relmodel.OutboxEvent) error {
	if p == nil || p.transport == nil {
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
	if _, err := p.transport.AppendDurable(
		ctx,
		durableMessage(PersonaRelationshipEventStream, values),
	); err != nil {
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
	event greetingapp.GreetingStreamEvent,
) error {
	if p == nil || p.transport == nil {
		return fmt.Errorf("greeting event publisher is unavailable")
	}
	if event.EventID == "" || event.EventName == "" || event.GreetingID == "" ||
		event.RequesterPersonaID == "" || event.TargetPersonaID == "" ||
		event.OccurredAt.IsZero() {
		return fmt.Errorf("invalid greeting event")
	}
	values := map[string]string{
		"eventId":            event.EventID,
		"eventName":          event.EventName,
		"id":                 event.GreetingID,
		"requesterPersonaId": event.RequesterPersonaID,
		"targetPersonaId":    event.TargetPersonaID,
		"occurredAt":         event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}
	switch event.EventName {
	case "GreetingRequestSent":
		if event.Source == "" || event.ExpireAt == "" ||
			strings.TrimSpace(event.RecipientAccountID) == "" {
			return fmt.Errorf("invalid GreetingRequestSent payload")
		}
		values["recipientAccountId"] = strings.TrimSpace(event.RecipientAccountID)
		values["source"] = event.Source
		values["expireAt"] = event.ExpireAt
		values["targetAllowsStrangerGreeting"] = strconv.FormatBool(event.TargetAllowsStrangerGreeting)
	case "GreetingRequestReplied":
		if event.PromotedConversationID == "" {
			return fmt.Errorf("invalid GreetingRequestReplied payload")
		}
		values["promotedConversationId"] = event.PromotedConversationID
	case "GreetingRequestIgnored":
		if event.DecisionAt == "" {
			return fmt.Errorf("invalid GreetingRequestIgnored payload")
		}
		values["decisionAt"] = event.DecisionAt
	case "GreetingRequestCancelled":
	default:
		return fmt.Errorf("invalid greeting event type %q", event.EventName)
	}
	if _, err := p.transport.AppendDurable(
		ctx,
		durableMessage(GreetingEventStream, values),
	); err != nil {
		return fmt.Errorf("append greeting stream: %w", err)
	}
	return nil
}

// PublishSubjectFollow appends the replayable subject follow stream consumed
// by entity-service (homepage follower projection), circle-service and the
// recommendation engine. The subject follow outbox is marked delivered only
// after this method returns.
func (p *EventPublisher) PublishSubjectFollow(ctx context.Context, event sfmodel.OutboxEvent) error {
	if p == nil || p.transport == nil {
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
	if _, err := p.transport.AppendDurable(
		ctx,
		durableMessage(SubjectFollowEventStream, values),
	); err != nil {
		return fmt.Errorf("append subject follow stream: %w", err)
	}
	return nil
}

func durableMessage(
	stream string,
	values map[string]string,
) runtimemessaging.DurableMessage {
	fields := make([]runtimemessaging.DurableField, 0, len(values))
	for name, value := range values {
		fields = append(fields, runtimemessaging.DurableField{
			Name:  name,
			Value: value,
		})
	}
	return runtimemessaging.DurableMessage{
		Stream: stream,
		Fields: fields,
	}
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
