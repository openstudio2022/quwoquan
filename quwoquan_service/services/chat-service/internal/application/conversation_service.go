package application

import (
	"context"
	"log/slog"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	event "quwoquan_service/services/chat-service/internal/domain/conversation/event"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
	"quwoquan_service/services/chat-service/internal/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

type ConversationService struct {
	repo          persistence.ChatRepository
	cache         *cache.ConversationCache
	publisher     EventPublisher
	profiles      ProfileSnapshotResolver
	media         GroupAvatarAssetizer
	syncPublisher UserSyncPublisher
	scheduler     GroupAvatarTaskScheduler
}

func NewConversationService(
	repo persistence.ChatRepository,
	cache *cache.ConversationCache,
	publisher EventPublisher,
	profiles ProfileSnapshotResolver,
	media GroupAvatarAssetizer,
	sync UserSyncPublisher,
	scheduler GroupAvatarTaskScheduler,
) *ConversationService {
	if publisher == nil {
		publisher = NoopEventPublisher()
	}
	if profiles == nil {
		profiles = noopProfileResolver{}
	}
	if scheduler == nil {
		scheduler = NoopGroupAvatarTaskScheduler()
	}
	return &ConversationService{
		repo:          repo,
		cache:         cache,
		publisher:     publisher,
		profiles:      profiles,
		media:         media,
		syncPublisher: sync,
		scheduler:     scheduler,
	}
}

type CreateConversationRequest struct {
	Type             string
	Title            string
	CircleId         string
	MaxGroupSize     int
	CreatorId        string
	InitialMemberIds []string
}

func (s *ConversationService) CreateConversation(ctx context.Context, req CreateConversationRequest) (*model.Conversation, error) {
	now := time.Now()
	maxGroupSize := req.MaxGroupSize
	if maxGroupSize <= 0 {
		switch req.Type {
		case "direct", "encrypted":
			maxGroupSize = 2
		default:
			maxGroupSize = 500
		}
	}
	initialMemberIds := dedupeUserIDs(req.InitialMemberIds, req.CreatorId)
	if req.Type == "group" && len(initialMemberIds)+1 > maxGroupSize {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"群成员数量超过上限",
			"initial members exceed max group size",
		)
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
	if conv.Type == "group" || conv.Type == "circle" {
		defaultAvatarURL := DefaultGroupAvatarURL()
		if strings.TrimSpace(defaultAvatarURL) == "" {
			return nil, rterr.NewAppError(
				rterr.NewCode(rterr.ModuleChat, rterr.KindSystem, "avatar_default_unavailable"),
				"群头像暂不可用，请稍后重试",
				"group default avatar url is not configured",
			)
		}
		conv.AvatarUrl = defaultAvatarURL
	}

	profileIDs := append([]string{req.CreatorId}, initialMemberIds...)
	profMap, _ := s.profiles.ResolveMany(ctx, profileIDs)
	lookup := func(uid string) (string, string, string, int) {
		if p, ok := profMap[uid]; ok {
			return p.DisplayName, p.AvatarURL, p.AvatarAssetID, p.AvatarVersion
		}
		return "", "", "", 0
	}

	creatorDN, creatorAV, creatorAssetID, creatorAvatarVersion := lookup(req.CreatorId)
	if (conv.Type == "group" || conv.Type == "circle") && strings.TrimSpace(creatorAV) != "" {
		conv.AvatarUrl = strings.TrimSpace(creatorAV)
	}
	creator := &model.ConversationMember{
		ID:             generateID(),
		ConversationId: conv.ID,
		UserId:         req.CreatorId,
		DisplayName:    creatorDN,
		AvatarUrl:      creatorAV,
		AvatarAssetId:  creatorAssetID,
		AvatarVersion:  int64(creatorAvatarVersion),
		MemberType:     "user",
		Role:           "owner",
		JoinedAt:       now,
	}
	initialMembers := make([]*model.ConversationMember, 0, len(initialMemberIds))
	for i, userID := range initialMemberIds {
		dn, av, assetID, avatarVersion := lookup(userID)
		initialMembers = append(initialMembers, &model.ConversationMember{
			ID:             generateID(),
			ConversationId: conv.ID,
			UserId:         userID,
			DisplayName:    dn,
			AvatarUrl:      av,
			AvatarAssetId:  assetID,
			AvatarVersion:  int64(avatarVersion),
			MemberType:     "user",
			Role:           "member",
			InvitedBy:      req.CreatorId,
			JoinedAt:       now.Add(time.Duration(i+1) * time.Millisecond),
		})
	}

	creatorState := &model.ConversationUserState{
		ID:             generateID(),
		UserId:         req.CreatorId,
		ConversationId: conv.ID,
		UpdatedAt:      now,
	}
	initialStates := make([]*model.ConversationUserState, 0, len(initialMemberIds))
	for _, userID := range initialMemberIds {
		initialStates = append(initialStates, &model.ConversationUserState{
			ID:             generateID(),
			UserId:         userID,
			ConversationId: conv.ID,
			UpdatedAt:      now,
		})
	}

	conv.MemberCount = len(initialMemberIds) + 1
	conv.MembersRosterRevision = 1
	conv.UpdatedAt = time.Now()
	if err := s.repo.RunInTransaction(ctx, func(txCtx context.Context) error {
		if err := s.repo.CreateConversation(txCtx, conv); err != nil {
			return err
		}
		if err := s.repo.CreateMember(txCtx, creator); err != nil {
			return err
		}
		for _, member := range initialMembers {
			if err := s.repo.CreateMember(txCtx, member); err != nil {
				return err
			}
		}
		if err := s.repo.UpdateConversation(txCtx, conv.ID, conv); err != nil {
			return err
		}
		if err := s.repo.UpsertUserState(txCtx, creatorState); err != nil {
			return err
		}
		for _, state := range initialStates {
			if err := s.repo.UpsertUserState(txCtx, state); err != nil {
				return err
			}
		}
		if conv.Type == "group" || conv.Type == "circle" {
			return s.scheduler.EnqueueRecompute(txCtx, GroupAvatarRecomputeTask{
				ConversationID: conv.ID,
				ActorID:        req.CreatorId,
				Trigger:        "conversation.created",
			})
		}
		return nil
	}); err != nil {
		return nil, err
	}

	if err := s.cache.InitSeq(ctx, conv.ID, 0); err != nil {
		return nil, err
	}

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

	go func() {
		convFresh, err := s.repo.FindConversationByID(context.Background(), conv.ID)
		if err != nil {
			slog.Error("publish ConversationRosterUpdated after create", "err", err, "conversationId", conv.ID)
			return
		}
		if err := s.publisher.PublishDomainEvent(context.Background(), event.ConversationRosterUpdated, conv.ID, req.CreatorId, map[string]any{
			"membersRosterRevision": convFresh.MembersRosterRevision,
			"updatedAt":             convFresh.UpdatedAt,
			"aspects":               []string{"members", "created"},
		}); err != nil {
			slog.Error("publish ConversationRosterUpdated failed", "err", err, "conversationId", conv.ID)
		}
	}()

	return conv, nil
}

type DissolveConversationRequest struct {
	ConversationId string
	OperatorId     string
}

func (s *ConversationService) DissolveConversation(ctx context.Context, req DissolveConversationRequest) error {
	conv, err := s.repo.FindConversationByID(ctx, req.ConversationId)
	if err != nil {
		return err
	}
	if conv.Type == "circle" {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "forbidden"),
			"圈子群不可解散",
			"circle conversation cannot be dissolved",
		)
	}
	owner, err := s.repo.FindMember(ctx, req.ConversationId, req.OperatorId)
	if err != nil || owner.Role != "owner" {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "forbidden"),
			"仅群主可解散群聊",
			"only owner can dissolve conversation",
		)
	}
	conv.Status = "deleted"
	if err := s.repo.UpdateConversation(ctx, conv.ID, conv); err != nil {
		return err
	}
	_ = s.cache.InvalidateConversation(ctx, req.ConversationId)
	return nil
}

func dedupeUserIDs(ids []string, exclude ...string) []string {
	excluded := make(map[string]struct{}, len(exclude))
	for _, id := range exclude {
		trimmed := strings.TrimSpace(id)
		if trimmed != "" {
			excluded[trimmed] = struct{}{}
		}
	}
	seen := make(map[string]struct{}, len(ids))
	out := make([]string, 0, len(ids))
	for _, id := range ids {
		trimmed := strings.TrimSpace(id)
		if trimmed == "" {
			continue
		}
		if _, ok := excluded[trimmed]; ok {
			continue
		}
		if _, ok := seen[trimmed]; ok {
			continue
		}
		seen[trimmed] = struct{}{}
		out = append(out, trimmed)
	}
	return out
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

type SearchConversationsRequest struct {
	UserId string
	Query  string
	Cursor string
	Limit  int
}

func (s *ConversationService) SearchConversations(
	ctx context.Context,
	req SearchConversationsRequest,
) ([]model.Conversation, error) {
	query := normalizeSearchQuery(req.Query)
	if query == "" {
		return []model.Conversation{}, nil
	}
	limit := clampSearchLimit(req.Limit, 20)
	conversations, err := listUserConversations(ctx, s.repo, req.UserId)
	if err != nil {
		return nil, err
	}
	results := make([]model.Conversation, 0, limit)
	for _, conversation := range conversations {
		matched, highlight := containsQuery(
			[]string{
				conversation.Title,
				conversation.LastMessagePreview,
				conversation.CircleId,
			},
			query,
		)
		if !matched {
			continue
		}
		if highlight != "" {
			conversation.LastMessagePreview = highlight
		}
		results = append(results, conversation)
		if len(results) >= limit {
			break
		}
	}
	return results, nil
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
