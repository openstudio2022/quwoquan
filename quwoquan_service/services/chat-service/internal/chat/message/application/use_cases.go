package application

import (
	"context"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	conversationapp "quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

type Backend interface {
	SendMessage(context.Context, conversationapp.SendMessageRequest) (*conversationapp.SendMessageResponse, error)
	SendAssistantDeliveryMessage(
		context.Context,
		conversationapp.AssistantDeliveryMessageRequest,
	) (*conversationapp.SendMessageResponse, error)
	RecallMessage(context.Context, string, string, string) error
	ListMessages(context.Context, conversationapp.ListMessagesRequest) ([]conversationapp.MessageSlice, error)
	ListAssistantGroundingMessages(
		context.Context,
		string,
		string,
		string,
		int64,
		int,
	) ([]conversationapp.MessageSlice, error)
	SyncMessages(context.Context, conversationapp.SyncMessagesRequest) (*conversationapp.SyncMessagesResponse, error)
}

type UseCases struct{ backend Backend }

func NewUseCases(backend Backend) *UseCases {
	if backend == nil {
		panic("message backend is required")
	}
	return &UseCases{backend: backend}
}

func (s *UseCases) Send(ctx context.Context, req conversationapp.SendMessageRequest) (*conversationapp.SendMessageResponse, error) {
	if strings.TrimSpace(req.ConversationId) == "" || strings.TrimSpace(req.SenderId) == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleChat, "conversationId 和 senderId 不能为空", "missing message owner")
	}
	return s.backend.SendMessage(ctx, req)
}
func (s *UseCases) SendAssistantDelivery(
	ctx context.Context,
	req conversationapp.AssistantDeliveryMessageRequest,
) (*conversationapp.SendMessageResponse, error) {
	return s.backend.SendAssistantDeliveryMessage(ctx, req)
}
func (s *UseCases) Recall(ctx context.Context, conversationID, messageID, senderID string) error {
	return s.backend.RecallMessage(ctx, conversationID, messageID, senderID)
}
func (s *UseCases) List(ctx context.Context, req conversationapp.ListMessagesRequest) ([]conversationapp.MessageSlice, error) {
	return s.backend.ListMessages(ctx, req)
}
func (s *UseCases) ListAssistantGrounding(
	ctx context.Context,
	conversationID string,
	creatorPersonaID string,
	assistantSkillID string,
	beforeSeq int64,
	limit int,
) ([]conversationapp.MessageSlice, error) {
	return s.backend.ListAssistantGroundingMessages(
		ctx,
		conversationID,
		creatorPersonaID,
		assistantSkillID,
		beforeSeq,
		limit,
	)
}
func (s *UseCases) Sync(ctx context.Context, req conversationapp.SyncMessagesRequest) (*conversationapp.SyncMessagesResponse, error) {
	return s.backend.SyncMessages(ctx, req)
}
