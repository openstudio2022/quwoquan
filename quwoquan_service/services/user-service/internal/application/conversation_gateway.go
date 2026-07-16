package application

import "context"

// ConversationGateway creates or resolves formal 1v1 conversations for greeting promotion.
type ConversationGateway interface {
	CreateOrReuseDirect(ctx context.Context, creatorID, peerID string) (conversationID string, err error)
	HasDirectBetween(ctx context.Context, subAccountA, subAccountB string) (bool, error)
}

func requireConversationGateway(gateway ConversationGateway) ConversationGateway {
	if gateway == nil {
		panic("user application requires ConversationGateway")
	}
	return gateway
}
