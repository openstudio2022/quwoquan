package messaging

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	personaapp "quwoquan_service/services/user-service/internal/persona_management/persona/application/persona"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

const (
	PersonaEventStream          = "events.user.personas"
	PersonaEventStreamRetention = 7 * 24 * time.Hour
)

type EventPublisher struct {
	transport runtimemessaging.DurableRecordAppender
}

func NewEventPublisher(transport runtimemessaging.DurableRecordAppender) (*EventPublisher, error) {
	if transport == nil {
		return nil, errors.New("Persona durable transport is required")
	}
	return &EventPublisher{transport: transport}, nil
}

func (publisher *EventPublisher) PublishPersona(
	ctx context.Context,
	event personaports.PersonaOutboxEvent,
) error {
	if publisher == nil || publisher.transport == nil {
		return errors.New("Persona event publisher is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.OwnerID) == "" || strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 ||
		event.OccurredAt.IsZero() || !json.Valid(event.PayloadJSON) {
		return errors.New("Persona event identity or payload is invalid")
	}
	eventName, payload, err := canonicalPersonaPublication(event)
	if err != nil {
		return err
	}
	if err := runtimemessaging.AppendDurableRecord(
		ctx,
		publisher.transport,
		PersonaEventStream,
		map[string]string{
			"eventId": event.EventID, "eventName": eventName,
			"aggregateType": "Persona", "personaId": event.AggregateID,
			"personaVersion": strconv.FormatInt(event.AggregateVersion, 10),
			"payload":        string(payload),
			"occurredAt":     event.OccurredAt.UTC().Format(time.RFC3339Nano),
		},
		PersonaEventStreamRetention,
	); err != nil {
		return fmt.Errorf("append Persona event stream: %w", err)
	}
	return nil
}

func canonicalPersonaPublication(event personaports.PersonaOutboxEvent) (string, []byte, error) {
	eventName := event.EventType
	switch event.EventType {
	case personaports.PersonaCreatedEvent,
		personaports.PersonaUpdatedEvent,
		personaports.PersonaRetiredEvent,
		personaports.PersonaActivatedEvent:
	default:
		return "", nil, fmt.Errorf("Persona event type %q is not canonical", event.EventType)
	}
	payload, err := json.Marshal(map[string]string{
		"userId": event.OwnerID, "personaId": event.AggregateID,
	})
	if err != nil {
		return "", nil, fmt.Errorf("encode Persona canonical payload: %w", err)
	}
	return eventName, payload, nil
}

var _ personaapp.PersonaEventPublisher = (*EventPublisher)(nil)
