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
	relationships RelationshipGate
	media         GroupAvatarAssetizer
	syncPublisher UserSyncPublisher
	scheduler     GroupAvatarTaskScheduler
}

func NewConversationService(
	repo persistence.ChatRepository,
	cache *cache.ConversationCache,
	publisher EventPublisher,
	profiles ProfileSnapshotResolver,
	relationships RelationshipGate,
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
	if relationships == nil {
		relationships = DenyRelationshipGate()
	}
	if scheduler == nil {
		scheduler = NoopGroupAvatarTaskScheduler()
	}
	return &ConversationService{
		repo:          repo,
		cache:         cache,
		publisher:     publisher,
		profiles:      profiles,
		relationships: relationships,
		media:         media,
		syncPublisher: sync,
		scheduler:     scheduler,
	}
}

type CreateConversationRequest struct {
	Type             string
	Title            string
	CircleId         string
	CircleGroupId    string
	EntityId         string
	OriginType       string
	BindingType      string
	LifecyclePolicy  string
	MaxGroupSize     int
	CreatorId        string
	InitialMemberIds []string
}

func (s *ConversationService) CreateConversation(ctx context.Context, req CreateConversationRequest) (*model.Conversation, error) {
	return s.createDirectConversation(ctx, req, false)
}

func (s *ConversationService) createDirectConversation(
	ctx context.Context,
	req CreateConversationRequest,
	bypassRelationshipGate bool,
) (*model.Conversation, error) {
	now := time.Now()
	req.Type = NormalizeConversationType(req.Type, req.CircleId)
	if req.Type != conversationTypeDirect && req.Type != conversationTypeGroup && req.Type != conversationTypeEncrypted {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"不支持的会话类型",
			"unsupported conversation type",
		)
	}
	originType := defaultString(req.OriginType, "direct_init")
	bindingType := defaultString(req.BindingType, "none")
	lifecyclePolicy := defaultString(req.LifecyclePolicy, "persistent")
	if req.Type == conversationTypeGroup {
		originType, bindingType, lifecyclePolicy = inferGroupConversationSemantics(req, originType, bindingType, lifecyclePolicy)
	}
	maxGroupSize := req.MaxGroupSize
	if maxGroupSize <= 0 {
		switch req.Type {
		case conversationTypeDirect, conversationTypeEncrypted:
			maxGroupSize = 2
		default:
			maxGroupSize = 500
		}
	}
	initialMemberIds := dedupeUserIDs(req.InitialMemberIds, req.CreatorId)
	if req.Type == conversationTypeDirect || req.Type == conversationTypeEncrypted {
		if len(initialMemberIds) != 1 {
			return nil, rterr.NewInvalidArgument(
				rterr.ModuleChat,
				"1 对 1 会话必须只有一个对方成员",
				"direct conversation requires exactly one invitee",
			)
		}
		peerID := initialMemberIds[0]
		if existing, findErr := s.repo.FindDirectConversationBetween(ctx, req.CreatorId, peerID); findErr == nil && existing != nil {
			return existing, nil
		}
		if !bypassRelationshipGate {
			capability, err := s.relationships.GetCapability(ctx, req.CreatorId, peerID)
			if err != nil {
				return nil, err
			}
			if capability.IsBlocked || capability.IsBlockedBy {
				return nil, chatBlocked("direct conversation blocked by relationship gate")
			}
			if !capability.CanCreateDirectConversation && !capability.HasFormalConversation {
				return nil, chatGreetingRequired("direct conversation requires mutual follow or replied greeting")
			}
		}
	}
	if req.Type == conversationTypeGroup && len(initialMemberIds)+1 > maxGroupSize {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"群成员数量超过上限",
			"initial members exceed max group size",
		)
	}
	if req.Type == conversationTypeGroup && !bypassRelationshipGate && !isCircleBoundCreateRequest(req) {
		if err := s.validateGroupInitialMembers(ctx, req.CreatorId, initialMemberIds); err != nil {
			return nil, err
		}
	}
	receiptEnabled := maxGroupSize <= 50

	conv := &model.Conversation{
		ID:              generateID(),
		Type:            req.Type,
		Title:           req.Title,
		CreatorId:       req.CreatorId,
		CircleId:        req.CircleId,
		CircleGroupId:   req.CircleGroupId,
		EntityId:        req.EntityId,
		OriginType:      originType,
		BindingType:     bindingType,
		LifecyclePolicy: lifecyclePolicy,
		MaxGroupSize:    maxGroupSize,
		ReceiptEnabled:  receiptEnabled,
		Status:          "active",
		CreatedAt:       now,
		UpdatedAt:       now,
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
	if IsGroupConversation(*conv) {
		conv.AvatarUrl = strings.TrimSpace(creatorAV)
		if conv.AvatarUrl == "" {
			conv.AvatarUrl = DefaultGroupAvatarURL()
		}
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
		if IsGroupConversation(*conv) {
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
			"type":            conv.Type,
			"creatorId":       req.CreatorId,
			"circleId":        conv.CircleId,
			"circleGroupId":   conv.CircleGroupId,
			"entityId":        conv.EntityId,
			"originType":      conv.OriginType,
			"bindingType":     conv.BindingType,
			"lifecyclePolicy": conv.LifecyclePolicy,
			"maxGroupSize":    conv.MaxGroupSize,
			"receiptEnabled":  conv.ReceiptEnabled,
			"createdAt":       conv.CreatedAt,
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
	if IsCircleBoundConversation(*conv) {
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

// isCircleBoundCreateRequest reports whether the create request targets a
// circle-derived group (circle default group or circle self-built group),
// whose membership is governed by circle join rather than hand-picked mutual
// contacts. The 发起群聊 hand-pick flow never sets these fields.
func isCircleBoundCreateRequest(req CreateConversationRequest) bool {
	return strings.TrimSpace(req.CircleId) != "" || strings.TrimSpace(req.CircleGroupId) != ""
}

// validateGroupInitialMembers enforces, server-side, that every hand-picked
// initial member of an ad-hoc group is mutually followed by the creator and is
// not in a block relationship. This mirrors the client candidate surfaces
// (which only expose mutual contacts) so a forged request cannot inject
// non-mutual or blocked members into a new group.
func (s *ConversationService) validateGroupInitialMembers(ctx context.Context, creatorID string, memberIDs []string) error {
	for _, memberID := range memberIDs {
		capability, err := s.relationships.GetCapability(ctx, creatorID, memberID)
		if err != nil {
			return err
		}
		if capability.IsBlocked || capability.IsBlockedBy {
			return chatGroupMemberBlocked("group conversation member blocked by relationship gate")
		}
		if !capability.IsMutual {
			return chatGroupMemberNotMutual("group conversation requires mutual follow with each invited member")
		}
	}
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

func defaultString(value string, fallback string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return fallback
	}
	return trimmed
}

func inferGroupConversationSemantics(
	req CreateConversationRequest,
	originType string,
	bindingType string,
	lifecyclePolicy string,
) (string, string, string) {
	hasCircleGroup := strings.TrimSpace(req.CircleGroupId) != ""
	hasCircle := strings.TrimSpace(req.CircleId) != ""
	if hasCircleGroup {
		if originType == "direct_init" {
			originType = "circle_self_built_group"
		}
		if bindingType == "none" {
			bindingType = "circle_group"
		}
		if lifecyclePolicy == "persistent" {
			lifecyclePolicy = "bound_to_circle"
		}
		return originType, bindingType, lifecyclePolicy
	}
	if hasCircle {
		if originType == "direct_init" {
			originType = "circle_default_group"
		}
		if bindingType == "none" {
			bindingType = "circle"
		}
		if lifecyclePolicy == "persistent" {
			lifecyclePolicy = "bound_to_circle"
		}
		return originType, bindingType, lifecyclePolicy
	}
	if originType == "direct_init" {
		originType = "ad_hoc_group"
	}
	return originType, bindingType, lifecyclePolicy
}

func (s *ConversationService) GetConversation(ctx context.Context, conversationId string) (*model.Conversation, error) {
	return s.repo.FindConversationByID(ctx, conversationId)
}

type UpdateConversationTitleRequest struct {
	ConversationId string
	OperatorId     string
	Title          string
}

func (s *ConversationService) UpdateConversationTitle(ctx context.Context, req UpdateConversationTitleRequest) (*model.Conversation, error) {
	conv, err := s.repo.FindConversationByID(ctx, req.ConversationId)
	if err != nil {
		return nil, err
	}
	title := strings.TrimSpace(req.Title)
	if title == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleChat, "群名称不能为空", "conversation title is empty")
	}
	conv.Title = title
	conv.MembersRosterRevision++
	conv.UpdatedAt = time.Now()
	if err := s.repo.UpdateConversation(ctx, conv.ID, conv); err != nil {
		return nil, err
	}
	_ = s.cache.InvalidateConversation(ctx, conv.ID)
	go func() {
		if err := s.publisher.PublishDomainEvent(context.Background(), event.ConversationRosterUpdated, conv.ID, req.OperatorId, map[string]any{
			"membersRosterRevision": conv.MembersRosterRevision,
			"updatedAt":             conv.UpdatedAt,
			"aspects":               []string{"title"},
		}); err != nil {
			slog.Error("publish ConversationRosterUpdated after title update", "err", err, "conversationId", conv.ID)
		}
	}()
	return conv, nil
}

func (s *ConversationService) CreateOrReuseDirect(ctx context.Context, creatorID, peerID string) (*model.Conversation, error) {
	if strings.TrimSpace(creatorID) == "" || strings.TrimSpace(peerID) == "" {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"创建 1v1 会话需要双方成员",
			"creatorId and peerId required",
		)
	}
	if existing, err := s.repo.FindDirectConversationBetween(ctx, creatorID, peerID); err != nil {
		return nil, err
	} else if existing != nil {
		return existing, nil
	}
	return s.createDirectConversation(ctx, CreateConversationRequest{
		Type:             conversationTypeDirect,
		CreatorId:        creatorID,
		InitialMemberIds: []string{peerID},
	}, true)
}

func (s *ConversationService) HasDirectBetween(ctx context.Context, memberA, memberB string) (bool, error) {
	conv, err := s.repo.FindDirectConversationBetween(ctx, memberA, memberB)
	if err != nil {
		return false, err
	}
	return conv != nil, nil
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
