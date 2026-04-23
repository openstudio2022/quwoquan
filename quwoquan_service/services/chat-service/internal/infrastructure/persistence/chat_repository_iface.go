package persistence

import (
	"context"

	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
)

// ChatRepository defines the storage operations used by the application layer.
// Both MongoChatStore and in-memory test doubles implement this interface.
type ChatRepository interface {
	// Conversation CRUD
	CreateConversation(ctx context.Context, conv *model.Conversation) error
	FindConversationByID(ctx context.Context, id string) (*model.Conversation, error)
	UpdateConversation(ctx context.Context, id string, conv *model.Conversation) error
	ListConversationsByUser(ctx context.Context, userId string, limit int, cursor string) ([]model.Conversation, error)

	// Message CRUD
	CreateMessage(ctx context.Context, msg *model.Message) error
	FindMessageByID(ctx context.Context, id string) (*model.Message, error)
	FindMessageByClientMsgId(ctx context.Context, conversationId, clientMsgId string) (*model.Message, error)
	ListMessages(ctx context.Context, conversationId string, limit int, afterSeq, beforeSeq int64) ([]model.Message, error)
	UpdateMessageStatus(ctx context.Context, id, status string) error
	SetMessageRecalled(ctx context.Context, id string) error

	// Member CRUD
	CreateMember(ctx context.Context, member *model.ConversationMember) error
	DeleteMember(ctx context.Context, conversationId, userId string) error
	FindMember(ctx context.Context, conversationId, userId string) (*model.ConversationMember, error)
	UpdateMemberAvatarSnapshot(
		ctx context.Context,
		conversationId string,
		userId string,
		avatarURL string,
		avatarAssetID string,
		avatarVersion int64,
	) error
	UpdateMemberRole(ctx context.Context, conversationId, userId, role string) error
	ListMembers(ctx context.Context, conversationId string, limit int, cursor, role, sort string) ([]model.ConversationMember, error)
	BumpMembersRosterRevision(ctx context.Context, conversationId string, memberCount *int) error
	CountMembers(ctx context.Context, conversationId string) (int, error)
	FindAssistantMember(ctx context.Context, conversationId string) (*model.ConversationMember, error)

	// User State
	UpsertUserState(ctx context.Context, state *model.ConversationUserState) error
	FindUserState(ctx context.Context, userId, conversationId string) (*model.ConversationUserState, error)
	ListUserStates(ctx context.Context, userId string, limit int, cursor string) ([]model.ConversationUserState, error)

	// Receipts
	CreateReceipt(ctx context.Context, receipt *model.MessageReceipt) error
	ListReceiptsByMessage(ctx context.Context, messageId string) ([]model.MessageReceipt, error)
}
