package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	proposalevent "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/event"
	proposalports "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/ports"
)

const EventStream = "events.user.profile_update_proposal"

type DurablePublisher interface {
	AppendDurable(context.Context, runtimemessaging.DurableMessage) (string, error)
}

type EventPublisher struct {
	transport DurablePublisher
}

func NewEventPublisher(transport DurablePublisher) *EventPublisher {
	return &EventPublisher{transport: transport}
}

// PublishProfileUpdateProposal appends the exact transactional outbox payload
// to the object-owned durable stream. eventId is the stable at-least-once
// deduplication key if a process stops after append but before checkpoint.
func (p *EventPublisher) PublishProfileUpdateProposal(
	ctx context.Context,
	event proposalports.OutboxEvent,
) error {
	if p == nil || p.transport == nil {
		return fmt.Errorf("ProfileUpdateProposal event publisher is unavailable")
	}
	if event.EventID == "" || event.AggregateID == "" ||
		event.AggregateVersion <= 0 || event.OccurredAt.IsZero() ||
		!json.Valid(event.PayloadJSON) ||
		!isPublicEvent(event.EventType) {
		return fmt.Errorf("invalid ProfileUpdateProposal event")
	}
	if _, err := p.transport.AppendDurable(
		ctx,
		runtimemessaging.DurableMessage{
			Stream: EventStream,
			Fields: []runtimemessaging.DurableField{
				{Name: "eventId", Value: event.EventID},
				{Name: "eventName", Value: event.EventType},
				{Name: "proposalId", Value: event.AggregateID},
				{
					Name:  "proposalVersion",
					Value: strconv.FormatInt(event.AggregateVersion, 10),
				},
				{Name: "payload", Value: string(event.PayloadJSON)},
				{
					Name:  "occurredAt",
					Value: event.OccurredAt.UTC().Format(time.RFC3339Nano),
				},
			},
		},
	); err != nil {
		return fmt.Errorf("append ProfileUpdateProposal event stream: %w", err)
	}
	return nil
}

func isPublicEvent(eventType string) bool {
	switch eventType {
	case proposalevent.ProfileUpdateProposalCreated,
		proposalevent.ProfileUpdateProposalConfirmed,
		proposalevent.ProfileUpdateProposalApplyStarted,
		proposalevent.ProfileUpdateProposalApplied,
		proposalevent.ProfileUpdateProposalRollbackStarted,
		proposalevent.ProfileUpdateProposalRollbackAborted,
		proposalevent.ProfileUpdateProposalRolledBack,
		proposalevent.ProfileUpdateProposalRejected,
		proposalevent.ProfileUpdateProposalExpired:
		return true
	default:
		return false
	}
}
