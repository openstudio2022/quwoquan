package circlegroup

import "context"

// ConversationBindingFailureStore is the object-owned port for durable retry
// state consumed by the CircleGroup conversation-binding projector.
type ConversationBindingFailureStore interface {
	RecordCircleGroupConversationBindingFailure(
		ctx context.Context,
		messageID string,
		eventID string,
		errorDigest string,
	) (int64, error)
	ClearCircleGroupConversationBindingFailure(ctx context.Context, messageID string) error
}
