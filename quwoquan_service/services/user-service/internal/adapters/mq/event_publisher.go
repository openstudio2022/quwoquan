package mq

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	relmodel "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/model"
)

const PersonaRelationshipEventStream = "events.user.persona_relationship"

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
	return result
}
