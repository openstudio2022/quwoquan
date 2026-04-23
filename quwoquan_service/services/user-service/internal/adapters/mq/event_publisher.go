package mq

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

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
