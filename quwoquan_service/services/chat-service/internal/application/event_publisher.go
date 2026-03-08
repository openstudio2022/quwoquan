package application

import "context"

// EventPublisher abstracts domain event publishing so that the application
// layer does not depend on adapters/mq.  The mq.EventPublisher satisfies
// this interface via its PublishDomainEvent method.
type EventPublisher interface {
	PublishDomainEvent(ctx context.Context, eventType, conversationId, actorId string, payload map[string]any) error
}

// noopPublisher is used when no publisher is configured (e.g. graceful degradation).
type noopPublisher struct{}

func (noopPublisher) PublishDomainEvent(context.Context, string, string, string, map[string]any) error {
	return nil
}

// NoopEventPublisher returns a publisher that silently discards all events.
func NoopEventPublisher() EventPublisher { return noopPublisher{} }
