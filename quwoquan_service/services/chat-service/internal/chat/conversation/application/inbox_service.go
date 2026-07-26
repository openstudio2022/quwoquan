package application

import (
	"context"

	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
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

// InboxPage preserves the keyset cursor emitted by the UserState reader while
// joining each state with its active Conversation aggregate.
type InboxPage struct {
	Items      []InboxItem
	NextCursor string
}

// ListInbox returns the user's conversation inbox sorted by pinned first,
// then by lastMessageTime descending (via ConversationUserState.UpdatedAt).
func (s *InboxService) ListInbox(ctx context.Context, req ListInboxRequest) ([]InboxItem, error) {
	page, err := s.ListInboxPage(ctx, req)
	if err != nil {
		return nil, err
	}
	return page.Items, nil
}

// ListInboxPage is the HTTP-facing typed Slice. It is deliberately separate
// from ListInbox so existing internal one-shot readers retain their narrow
// list contract while remote clients receive the actual keyset continuation.
func (s *InboxService) ListInboxPage(ctx context.Context, req ListInboxRequest) (InboxPage, error) {
	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}

	statePage, err := s.userStates.ListUserStatePage(ctx, req.UserId, limit, req.Cursor)
	if err != nil {
		return InboxPage{}, err
	}

	items := make([]InboxItem, 0, len(statePage.Items))
	for _, state := range statePage.Items {
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

	return InboxPage{
		Items:      items,
		NextCursor: statePage.NextCursor,
	}, nil
}

// 未读推进的唯一写入口是 InboxProjector（消费 MessageSent 事件），已读
// 水位的唯一写入口是 MessageService.MarkAsRead 命令；本查询服务不再提供
// 任何直接改写未读数的方法。
