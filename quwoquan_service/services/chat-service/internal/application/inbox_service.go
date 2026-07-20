package application

import (
	"context"

	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
)

// InboxService manages the per-user conversation inbox (ChatInbox projection).
// It provides sorted conversation lists and unread count maintenance.
type InboxService struct {
	conversations ConversationStore
	userStates    UserStateStore
}

func NewInboxService(storage ChatStoragePorts) *InboxService {
	return &InboxService{
		conversations: storage.Conversations,
		userStates:    storage.UserStates,
	}
}

// InboxItem combines a conversation with the user's state for inbox display.
type InboxItem struct {
	Conversation model.Conversation          `json:"conversation"`
	UserState    model.ConversationUserState `json:"userState"`
}

type ListInboxRequest struct {
	UserId string
	Limit  int
	Cursor string
}

// ListInbox returns the user's conversation inbox sorted by pinned first,
// then by lastMessageTime descending (via ConversationUserState.UpdatedAt).
func (s *InboxService) ListInbox(ctx context.Context, req ListInboxRequest) ([]InboxItem, error) {
	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}

	states, err := s.userStates.ListUserStates(ctx, req.UserId, limit, req.Cursor)
	if err != nil {
		return nil, err
	}

	items := make([]InboxItem, 0, len(states))
	for _, state := range states {
		conv, err := s.conversations.FindConversationByID(ctx, state.ConversationId)
		if err != nil {
			continue
		}
		if conv.Status != "active" {
			continue
		}
		items = append(items, InboxItem{
			Conversation: *conv,
			UserState:    state,
		})
	}

	return items, nil
}

// 未读推进的唯一写入口是 InboxProjector（消费 MessageSent 事件），已读
// 水位的唯一写入口是 MessageService.MarkAsRead 命令；本查询服务不再提供
// 任何直接改写未读数的方法。
