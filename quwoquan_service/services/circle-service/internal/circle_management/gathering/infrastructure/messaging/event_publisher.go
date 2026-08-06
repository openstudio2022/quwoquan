package messaging

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	gatheringevent "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/event"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

const (
	GatheringEventStream    = "events.circle.gatherings"
	GatheringEventRetention = 7 * 24 * time.Hour
)

type EventPublisher struct {
	transport runtimemessaging.DurableRecordAppender
}

func NewEventPublisher(transport runtimemessaging.DurableRecordAppender) (*EventPublisher, error) {
	if transport == nil {
		return nil, errors.New("Gathering durable transport is required")
	}
	return &EventPublisher{transport: transport}, nil
}

func (publisher *EventPublisher) PublishGathering(
	ctx context.Context,
	event ports.OutboxEvent,
) error {
	payload, err := canonicalGatheringPayload(event.EventType, event.Payload)
	if err != nil {
		return err
	}
	if err := runtimemessaging.AppendDurableRecord(ctx, publisher.transport,
		GatheringEventStream,
		map[string]string{
			"eventId": event.EventID, "eventName": event.EventType,
			"aggregateType": "Gathering", "aggregateId": event.AggregateID,
			"aggregateVersion": strconv.FormatInt(event.AggregateVersion, 10),
			"sequence":         strconv.FormatInt(event.Sequence, 10),
			"occurredAt":       event.OccurredAt.UTC().Format(time.RFC3339Nano),
			"payload":          string(payload),
		}, GatheringEventRetention,
	); err != nil {
		return fmt.Errorf("append Gathering event: %w", err)
	}
	return nil
}

func canonicalGatheringPayload(eventType string, payload []byte) ([]byte, error) {
	fieldsByEvent := map[string][]string{
		gatheringevent.GatheringDraftCreated: {
			"gatheringId", "aggregateVersion", "lifecycleStatus",
			"actorPersonaId", "revisionId", "revisionNumber",
			"revisionDigest", "roomBindingStatus", "occurredAt",
		},
		gatheringevent.GatheringRoomBindingChanged: {
			"gatheringId", "aggregateVersion", "lifecycleStatus",
			"roomBindingStatus", "conversationId", "occurredAt",
		},
		gatheringevent.GatheringPublished: {
			"gatheringId", "aggregateVersion", "lifecycleStatus",
			"actorPersonaId", "revisionId", "revisionNumber",
			"revisionDigest", "roomBindingStatus", "conversationId", "occurredAt",
		},
		gatheringevent.GatheringRevisionAppended: {
			"gatheringId", "aggregateVersion", "lifecycleStatus",
			"actorPersonaId", "revisionId", "revisionNumber",
			"revisionDigest", "occurredAt",
		},
		gatheringevent.GatheringParticipationChanged: {
			"gatheringId", "aggregateVersion", "lifecycleStatus",
			"actorPersonaId", "participantPersonaId", "participationState",
			"revisionId", "revisionNumber", "revisionDigest", "occurredAt",
		},
		gatheringevent.GatheringInvitationChanged: {
			"gatheringId", "inviterPersonaId", "recipientPersonaId",
			"purposeSummary", "schedule", "place", "participationVersion",
			"status", "actionIntents", "expiresAt", "occurredAt",
		},
		gatheringevent.GatheringAdmissionControlChanged: {
			"gatheringId", "aggregateVersion", "lifecycleStatus",
			"actorPersonaId", "admissionControlStatus", "occurredAt",
		},
		gatheringevent.GatheringCancelled: {
			"gatheringId", "aggregateVersion", "lifecycleStatus",
			"actorPersonaId", "roomBindingStatus", "conversationId", "occurredAt",
		},
		gatheringevent.GatheringEndedEarly: {
			"gatheringId", "aggregateVersion", "lifecycleStatus",
			"actorPersonaId", "outcomeStatus", "roomBindingStatus",
			"conversationId", "occurredAt",
		},
		gatheringevent.GatheringSafetyTerminated: {
			"gatheringId", "aggregateVersion", "lifecycleStatus",
			"actorPersonaId", "outcomeStatus", "roomBindingStatus",
			"conversationId", "occurredAt",
		},
		gatheringevent.GatheringCompleted: {
			"gatheringId", "aggregateVersion", "lifecycleStatus",
			"actorPersonaId", "outcomeStatus", "roomBindingStatus",
			"conversationId", "occurredAt",
		},
		gatheringevent.GatheringOutcomeCalculated: {
			"gatheringId", "aggregateVersion", "lifecycleStatus",
			"outcomeStatus", "occurredAt",
		},
		gatheringevent.GatheringAvailabilityWatchChanged: {
			"gatheringId", "aggregateVersion", "lifecycleStatus",
			"actorPersonaId", "watchStatus", "occurredAt",
		},
	}
	fields, supported := fieldsByEvent[eventType]
	if !supported {
		return nil, fmt.Errorf("Gathering event type %q is not canonical", eventType)
	}
	var source map[string]json.RawMessage
	if err := json.Unmarshal(payload, &source); err != nil {
		return nil, fmt.Errorf("decode Gathering event payload: %w", err)
	}
	canonical := make(map[string]json.RawMessage, len(fields))
	for _, field := range fields {
		value, exists := source[field]
		if !exists || len(value) == 0 {
			if optionalGatheringEventField(field) {
				continue
			}
			return nil, fmt.Errorf("Gathering %s payload is missing %s", eventType, field)
		}
		canonical[field] = value
	}
	encoded, err := json.Marshal(canonical)
	if err != nil {
		return nil, fmt.Errorf("encode Gathering canonical payload: %w", err)
	}
	return encoded, nil
}

func optionalGatheringEventField(field string) bool {
	switch field {
	case "actorPersonaId", "participantPersonaId", "participationState",
		"revisionId", "revisionNumber", "revisionDigest", "conversationId",
		"outcomeStatus", "watchStatus", "expiresAt":
		return true
	default:
		return false
	}
}
