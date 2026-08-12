package searchindex

import (
	"context"

	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

// composedPublisher fans a user event out to several publishers. Every
// projection error is returned to the caller; callers that need retry must use
// their object-owned durable outbox rather than swallowing a derived-store
// failure.
type composedPublisher struct {
	publishers []application.UserEventPublisher
}

// ComposePublisher fans events out to all non-nil publishers in order, returning
// the first error encountered while allowing later projections to observe the
// same event.
func ComposePublisher(publishers ...application.UserEventPublisher) application.UserEventPublisher {
	live := make([]application.UserEventPublisher, 0, len(publishers))
	for _, p := range publishers {
		if p != nil {
			live = append(live, p)
		}
	}
	return composedPublisher{publishers: live}
}

func (c composedPublisher) PublishUserEvent(ctx context.Context, eventType, userID, actorID string, payload map[string]any) error {
	var firstErr error
	for _, p := range c.publishers {
		if err := p.PublishUserEvent(ctx, eventType, userID, actorID, payload); err != nil && firstErr == nil {
			firstErr = err
		}
	}
	return firstErr
}
