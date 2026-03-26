package application

import (
	"context"
	"time"

	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

// InboxService manages the per-user conversation inbox (ChatInbox projection).
// It provides sorted conversation lists and unread count maintenance.
type InboxService struct {
	repo persistence.ChatRepository
}

func NewInboxService(repo persistence.ChatRepository) *InboxService {
	return &InboxService{repo: repo}
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

	states, err := s.repo.ListUserStates(ctx, req.UserId, limit, req.Cursor)
	if err != nil {
		return nil, err
	}

	items := make([]InboxItem, 0, len(states))
	for _, state := range states {
		conv, err := s.repo.FindConversationByID(ctx, state.ConversationId)
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

// IncrementUnread increases the unread count for a user in a conversation.
// Called when a new message is sent by another user.
func (s *InboxService) IncrementUnread(ctx context.Context, userId, conversationId string) error {
	state, err := s.repo.FindUserState(ctx, userId, conversationId)
	if err != nil {
		now := time.Now()
		state = &model.ConversationUserState{
			ID:             generateID(),
			UserId:         userId,
			ConversationId: conversationId,
			UpdatedAt:      now,
		}
	}

	state.UnreadCount++
	state.UpdatedAt = time.Now()
	return s.repo.UpsertUserState(ctx, state)
}

// MarkAsRead resets the unread count and updates the read sequence for a user.
func (s *InboxService) MarkAsRead(ctx context.Context, userId, conversationId string, readSeq int64) error {
	state, err := s.repo.FindUserState(ctx, userId, conversationId)
	if err != nil {
		now := time.Now()
		state = &model.ConversationUserState{
			ID:             generateID(),
			UserId:         userId,
			ConversationId: conversationId,
			UpdatedAt:      now,
		}
	}

	if readSeq > state.ReadSeq {
		state.ReadSeq = readSeq
	}
	state.UnreadCount = 0
	state.LastReadAt = time.Now()
	state.UpdatedAt = time.Now()
	return s.repo.UpsertUserState(ctx, state)
}
