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
