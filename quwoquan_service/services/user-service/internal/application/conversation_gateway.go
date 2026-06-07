package application

import "context"

// ConversationGateway creates or resolves formal 1v1 conversations for greeting promotion.
type ConversationGateway interface {
	CreateOrReuseDirect(ctx context.Context, creatorID, peerID string) (conversationID string, err error)
	HasDirectBetween(ctx context.Context, subAccountA, subAccountB string) (bool, error)
}

type noopConversationGateway struct{}

func (noopConversationGateway) CreateOrReuseDirect(context.Context, string, string) (string, error) {
	return "", nil
}

func (noopConversationGateway) HasDirectBetween(context.Context, string, string) (bool, error) {
	return false, nil
}

func NoopConversationGateway() ConversationGateway { return noopConversationGateway{} }
