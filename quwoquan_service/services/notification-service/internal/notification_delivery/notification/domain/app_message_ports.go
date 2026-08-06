package notification

import (
	"context"
	"time"
)

// AppMessageAggregateStore owns Notification aggregate mutations. Query use
// cases are exposed through named Readers in the application layer.
type AppMessageAggregateStore interface {
	Create(ctx context.Context, message AppMessage) (AppMessage, bool, error)
	FindByIdempotencyKey(ctx context.Context, key string) (AppMessage, bool, error)
	Acknowledge(ctx context.Context, userID, messageID string, at time.Time) (AppMessage, error)
	MarkRead(ctx context.Context, userID, messageID string, at time.Time) (AppMessage, error)
}

// GatheringInvitationProjectionStore owns the idempotent, monotonic materialized
// view written from Circle's public Gathering invitation events.
type GatheringInvitationProjectionStore interface {
	UpsertGatheringInvitation(
		context.Context,
		AppMessage,
	) (AppMessage, bool, error)
	CancelGatheringInvitations(
		context.Context,
		string,
	) error
}
