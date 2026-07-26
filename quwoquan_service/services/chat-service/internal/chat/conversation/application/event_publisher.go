package application

import "context"

// EventPublisher abstracts domain event publishing so that the application
// layer does not depend on adapters/mq.  The mq.EventPublisher satisfies
// this interface via its PublishDomainEvent method.
type EventPublisher interface {
	PublishDomainEvent(ctx context.Context, eventType, conversationId, actorId string, payload map[string]any) error
	PublishRecordedDomainEvent(ctx context.Context, eventID, eventType, conversationID, actorID string, payload map[string]any) error
}

func requireEventPublisher(publisher EventPublisher) EventPublisher {
	if publisher == nil {
		panic("chat application requires EventPublisher")
	}
	return publisher
}
