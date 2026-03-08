package application

import (
	"context"
	"errors"
	"log/slog"
	"time"

	event "quwoquan_service/services/chat-service/internal/domain/conversation/event"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
	"quwoquan_service/services/chat-service/internal/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

type MemberService struct {
	repo      persistence.ChatRepository
	cache     *cache.ConversationCache
	publisher EventPublisher
}

func NewMemberService(repo persistence.ChatRepository, cache *cache.ConversationCache, publisher EventPublisher) *MemberService {
	if publisher == nil {
		publisher = NoopEventPublisher()
	}
	return &MemberService{repo: repo, cache: cache, publisher: publisher}
}

type ListMembersRequest struct {
	ConversationId string
	Cursor         string
	Limit          int
	Role           string
}

func (s *MemberService) ListMembers(ctx context.Context, req ListMembersRequest) ([]model.ConversationMember, error) {
	return s.repo.ListMembers(ctx, req.ConversationId, req.Limit, req.Cursor, req.Role)
}

type AddMembersRequest struct {
	ConversationId string
	UserIds        []string
	InvitedBy      string
}

func (s *MemberService) AddMembers(ctx context.Context, req AddMembersRequest) error {
	conv, err := s.repo.FindConversationByID(ctx, req.ConversationId)
	if err != nil {
		return err
	}

	currentCount, err := s.repo.CountMembers(ctx, req.ConversationId)
	if err != nil {
		return err
	}

	if currentCount+len(req.UserIds) > conv.MaxGroupSize {
		return errors.New("group size exceeded")
	}

	now := time.Now()
	for _, userId := range req.UserIds {
		member := &model.ConversationMember{
			ID:             generateID(),
			ConversationId: req.ConversationId,
			UserId:         userId,
			MemberType:     "user",
			Role:           "member",
			InvitedBy:      req.InvitedBy,
			JoinedAt:       now,
		}
		if err := s.repo.CreateMember(ctx, member); err != nil {
			return err
		}

		initState := &model.ConversationUserState{
			ID:             generateID(),
			UserId:         userId,
			ConversationId: req.ConversationId,
			UpdatedAt:      now,
		}
		_ = s.repo.UpsertUserState(ctx, initState)
	}

	newCount, _ := s.repo.CountMembers(ctx, req.ConversationId)
	conv.MemberCount = newCount
	_ = s.repo.UpdateConversation(ctx, conv.ID, conv)
	_ = s.cache.InvalidateConversation(ctx, req.ConversationId)

	go func() {
		for _, userId := range req.UserIds {
			if err := s.publisher.PublishDomainEvent(context.Background(), event.MemberJoined, req.ConversationId, userId, map[string]any{
				"role":        "member",
				"invitedBy":   req.InvitedBy,
				"memberCount": newCount,
			}); err != nil {
				slog.Error("publish MemberJoined failed", "err", err, "conversationId", req.ConversationId, "userId", userId)
			}
		}
	}()

	return nil
}

func (s *MemberService) RemoveMember(ctx context.Context, conversationId, userId string) error {
	if err := s.repo.DeleteMember(ctx, conversationId, userId); err != nil {
		return err
	}

	conv, err := s.repo.FindConversationByID(ctx, conversationId)
	var newCount int
	if err == nil {
		newCount, _ = s.repo.CountMembers(ctx, conversationId)
		conv.MemberCount = newCount
		_ = s.repo.UpdateConversation(ctx, conv.ID, conv)
	}

	_ = s.cache.InvalidateConversation(ctx, conversationId)

	go func() {
		if err := s.publisher.PublishDomainEvent(context.Background(), event.MemberLeft, conversationId, userId, map[string]any{
			"memberCount": newCount,
		}); err != nil {
			slog.Error("publish MemberLeft failed", "err", err, "conversationId", conversationId, "userId", userId)
		}
	}()

	return nil
}

type InviteAssistantRequest struct {
	ConversationId string
	SkillId        string
	InvitedBy      string
}

func (s *MemberService) InviteAssistant(ctx context.Context, req InviteAssistantRequest) error {
	existing, _ := s.repo.FindAssistantMember(ctx, req.ConversationId)
	if existing != nil {
		return errors.New("assistant already in conversation")
	}

	now := time.Now()
	member := &model.ConversationMember{
		ID:               generateID(),
		ConversationId:   req.ConversationId,
		UserId:           "assistant",
		MemberType:       "assistant",
		Role:             "member",
		AssistantSkillId: req.SkillId,
		InvitedBy:        req.InvitedBy,
		JoinedAt:         now,
	}
	if err := s.repo.CreateMember(ctx, member); err != nil {
		return err
	}

	conv, err := s.repo.FindConversationByID(ctx, req.ConversationId)
	if err == nil {
		newCount, _ := s.repo.CountMembers(ctx, req.ConversationId)
		conv.MemberCount = newCount
		_ = s.repo.UpdateConversation(ctx, conv.ID, conv)
	}

	_ = s.cache.InvalidateConversation(ctx, req.ConversationId)

	go func() {
		if err := s.publisher.PublishDomainEvent(context.Background(), event.AssistantInvited, req.ConversationId, req.InvitedBy, map[string]any{
			"assistantMemberId": member.ID,
			"assistantSkillId":  req.SkillId,
			"invitedBy":         req.InvitedBy,
		}); err != nil {
			slog.Error("publish AssistantInvited failed", "err", err, "conversationId", req.ConversationId)
		}
	}()

	return nil
}

func (s *MemberService) RemoveAssistant(ctx context.Context, conversationId string) error {
	assistant, err := s.repo.FindAssistantMember(ctx, conversationId)
	if err != nil {
		return errors.New("no assistant in conversation")
	}

	if err := s.repo.DeleteMember(ctx, conversationId, assistant.UserId); err != nil {
		return err
	}

	conv, err := s.repo.FindConversationByID(ctx, conversationId)
	if err == nil {
		newCount, _ := s.repo.CountMembers(ctx, conversationId)
		conv.MemberCount = newCount
		_ = s.repo.UpdateConversation(ctx, conv.ID, conv)
	}

	_ = s.cache.InvalidateConversation(ctx, conversationId)
	return nil
}

// ListContacts and SearchContacts are placeholders —
// in production these would query a separate user/social graph service.

func (s *MemberService) ListContacts(_ context.Context, _ string, _ int, _ string) ([]map[string]any, error) {
	return []map[string]any{}, nil
}

func (s *MemberService) SearchContacts(_ context.Context, _ string) ([]map[string]any, error) {
	return []map[string]any{}, nil
}
