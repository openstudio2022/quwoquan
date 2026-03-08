package application

import (
	"context"
	"log/slog"
	"time"

	event "quwoquan_service/services/chat-service/internal/domain/conversation/event"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
	"quwoquan_service/services/chat-service/internal/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

type ConversationService struct {
	repo      persistence.ChatRepository
	cache     *cache.ConversationCache
	publisher EventPublisher
}

func NewConversationService(repo persistence.ChatRepository, cache *cache.ConversationCache, publisher EventPublisher) *ConversationService {
	if publisher == nil {
		publisher = NoopEventPublisher()
	}
	return &ConversationService{repo: repo, cache: cache, publisher: publisher}
}

type CreateConversationRequest struct {
	Type         string
	Title        string
	CircleId     string
	MaxGroupSize int
	CreatorId    string
}

func (s *ConversationService) CreateConversation(ctx context.Context, req CreateConversationRequest) (*model.Conversation, error) {
	now := time.Now()
	maxGroupSize := req.MaxGroupSize
	if maxGroupSize <= 0 {
		maxGroupSize = 1000
	}
	receiptEnabled := maxGroupSize <= 50

	conv := &model.Conversation{
		ID:             generateID(),
		Type:           req.Type,
		Title:          req.Title,
		CreatorId:      req.CreatorId,
		CircleId:       req.CircleId,
		MaxGroupSize:   maxGroupSize,
		ReceiptEnabled: receiptEnabled,
		Status:         "active",
		CreatedAt:      now,
		UpdatedAt:      now,
	}

	if err := s.repo.CreateConversation(ctx, conv); err != nil {
		return nil, err
	}

	if err := s.cache.InitSeq(ctx, conv.ID, 0); err != nil {
		return nil, err
	}

	creator := &model.ConversationMember{
		ID:             generateID(),
		ConversationId: conv.ID,
		UserId:         req.CreatorId,
		MemberType:     "user",
		Role:           "owner",
		JoinedAt:       now,
	}
	if err := s.repo.CreateMember(ctx, creator); err != nil {
		return nil, err
	}

	conv.MemberCount = 1
	if err := s.repo.UpdateConversation(ctx, conv.ID, conv); err != nil {
		return nil, err
	}

	initState := &model.ConversationUserState{
		ID:             generateID(),
		UserId:         req.CreatorId,
		ConversationId: conv.ID,
		UpdatedAt:      now,
	}
	_ = s.repo.UpsertUserState(ctx, initState)

	go func() {
		if err := s.publisher.PublishDomainEvent(context.Background(), event.ConversationCreated, conv.ID, req.CreatorId, map[string]any{
			"type":           conv.Type,
			"creatorId":      req.CreatorId,
			"circleId":       conv.CircleId,
			"maxGroupSize":   conv.MaxGroupSize,
			"receiptEnabled": conv.ReceiptEnabled,
			"createdAt":      conv.CreatedAt,
		}); err != nil {
			slog.Error("publish ConversationCreated failed", "err", err, "conversationId", conv.ID)
		}
	}()

	return conv, nil
}

func (s *ConversationService) GetConversation(ctx context.Context, conversationId string) (*model.Conversation, error) {
	return s.repo.FindConversationByID(ctx, conversationId)
}

type ListConversationsRequest struct {
	UserId string
	Cursor string
	Limit  int
}

func (s *ConversationService) ListConversations(ctx context.Context, req ListConversationsRequest) ([]model.Conversation, error) {
	return s.repo.ListConversationsByUser(ctx, req.UserId, req.Limit, req.Cursor)
}

type UpdateSettingsRequest struct {
	UserId         string
	ConversationId string
	Muted          *bool
	Pinned         *bool
}

func (s *ConversationService) UpdateSettings(ctx context.Context, req UpdateSettingsRequest) error {
	state, err := s.repo.FindUserState(ctx, req.UserId, req.ConversationId)
	if err != nil {
		now := time.Now()
		state = &model.ConversationUserState{
			ID:             generateID(),
			UserId:         req.UserId,
			ConversationId: req.ConversationId,
			UpdatedAt:      now,
		}
	}

	if req.Muted != nil {
		state.Muted = *req.Muted
	}
	if req.Pinned != nil {
		state.Pinned = *req.Pinned
	}
	state.UpdatedAt = time.Now()

	if err := s.repo.UpsertUserState(ctx, state); err != nil {
		return err
	}

	_ = s.cache.InvalidateConversation(ctx, req.ConversationId)

	go func() {
		if err := s.publisher.PublishDomainEvent(context.Background(), event.ConversationSettingsUpdated, req.ConversationId, req.UserId, map[string]any{
			"muted":  req.Muted,
			"pinned": req.Pinned,
		}); err != nil {
			slog.Error("publish ConversationSettingsUpdated failed", "err", err, "conversationId", req.ConversationId)
		}
	}()

	return nil
}
