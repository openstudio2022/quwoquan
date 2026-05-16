package application

import (
	"context"
	"errors"
	"log/slog"
	"strings"
	"sync"
	"time"

	rterr "quwoquan_service/runtime/errors"
	event "quwoquan_service/services/chat-service/internal/domain/conversation/event"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
	"quwoquan_service/services/chat-service/internal/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

type MemberService struct {
	repo           persistence.ChatRepository
	cache          *cache.ConversationCache
	publisher      EventPublisher
	profiles       ProfileSnapshotResolver
	media          GroupAvatarAssetizer
	syncPublisher  UserSyncPublisher
	scheduler      GroupAvatarTaskScheduler
	rosterMu       sync.Mutex
	rosterTimers   map[string]*time.Timer
	rosterDebounce time.Duration
}

func NewMemberService(
	repo persistence.ChatRepository,
	cache *cache.ConversationCache,
	publisher EventPublisher,
	profiles ProfileSnapshotResolver,
	media GroupAvatarAssetizer,
	syncPublisher UserSyncPublisher,
	scheduler GroupAvatarTaskScheduler,
) *MemberService {
	if publisher == nil {
		publisher = NoopEventPublisher()
	}
	if profiles == nil {
		profiles = noopProfileResolver{}
	}
	if scheduler == nil {
		scheduler = NoopGroupAvatarTaskScheduler()
	}
	return &MemberService{
		repo: repo, cache: cache, publisher: publisher, profiles: profiles, media: media, syncPublisher: syncPublisher, scheduler: scheduler,
		rosterTimers:   make(map[string]*time.Timer),
		rosterDebounce: 80 * time.Millisecond,
	}
}

type ListMembersRequest struct {
	ConversationId string
	Cursor         string
	Limit          int
	Role           string
	Sort           string
}

func (s *MemberService) ListMembers(ctx context.Context, req ListMembersRequest) ([]model.ConversationMember, error) {
	sort := persistence.NormalizeMemberListSort(req.Sort)
	return s.repo.ListMembers(ctx, req.ConversationId, req.Limit, req.Cursor, req.Role, sort)
}

func (s *MemberService) scheduleRosterUpdatedPublish(conversationId string) {
	if s.rosterDebounce <= 0 {
		s.flushRosterUpdated(context.Background(), conversationId)
		return
	}
	s.rosterMu.Lock()
	defer s.rosterMu.Unlock()
	if prev := s.rosterTimers[conversationId]; prev != nil {
		prev.Stop()
	}
	cid := conversationId
	s.rosterTimers[cid] = time.AfterFunc(s.rosterDebounce, func() {
		s.flushRosterUpdated(context.Background(), cid)
	})
}

func (s *MemberService) flushRosterUpdated(ctx context.Context, conversationId string) {
	s.rosterMu.Lock()
	delete(s.rosterTimers, conversationId)
	s.rosterMu.Unlock()

	conv, err := s.repo.FindConversationByID(ctx, conversationId)
	if err != nil {
		slog.Error("flushRosterUpdated", "err", err, "conversationId", conversationId)
		return
	}
	if err := s.publisher.PublishDomainEvent(ctx, event.ConversationRosterUpdated, conversationId, "", map[string]any{
		"membersRosterRevision": conv.MembersRosterRevision,
		"updatedAt":             conv.UpdatedAt,
		"aspects":               []string{"members"},
	}); err != nil {
		slog.Error("publish ConversationRosterUpdated", "err", err, "conversationId", conversationId)
	}
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
	if conv.Status != "active" {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "forbidden"),
			"当前群聊不可操作",
			"conversation is not active",
		)
	}
	userIDs := dedupeUserIDs(req.UserIds)

	currentCount, err := s.repo.CountMembers(ctx, req.ConversationId)
	if err != nil {
		return err
	}

	newUserIDs := make([]string, 0, len(userIDs))
	for _, userId := range userIDs {
		if _, err := s.repo.FindMember(ctx, req.ConversationId, userId); err == nil {
			continue
		}
		newUserIDs = append(newUserIDs, userId)
	}

	if currentCount+len(newUserIDs) > conv.MaxGroupSize {
		return rterr.NewInvalidArgument(rterr.ModuleChat, "群成员数量超过上限", "group size exceeded")
	}

	profMap, _ := s.profiles.ResolveMany(ctx, newUserIDs)
	lookup := func(uid string) (string, string, string, int) {
		if p, ok := profMap[uid]; ok {
			return p.DisplayName, p.AvatarURL, p.AvatarAssetID, p.AvatarVersion
		}
		return "", "", "", 0
	}

	now := time.Now()
	membersToCreate := make([]*model.ConversationMember, 0, len(newUserIDs))
	statesToCreate := make([]*model.ConversationUserState, 0, len(newUserIDs))
	for _, userId := range newUserIDs {
		dn, av, assetID, avatarVersion := lookup(userId)
		membersToCreate = append(membersToCreate, &model.ConversationMember{
			ID:             generateID(),
			ConversationId: req.ConversationId,
			UserId:         userId,
			DisplayName:    dn,
			AvatarUrl:      av,
			AvatarAssetId:  assetID,
			AvatarVersion:  int64(avatarVersion),
			MemberType:     "user",
			Role:           "member",
			InvitedBy:      req.InvitedBy,
			JoinedAt:       now.Add(time.Duration(len(membersToCreate)) * time.Millisecond),
		})
		statesToCreate = append(statesToCreate, &model.ConversationUserState{
			ID:             generateID(),
			UserId:         userId,
			ConversationId: req.ConversationId,
			UpdatedAt:      now,
		})
	}

	if len(membersToCreate) == 0 {
		return nil
	}

	newCount := currentCount + len(membersToCreate)
	if err := s.repo.RunInTransaction(ctx, func(txCtx context.Context) error {
		for _, member := range membersToCreate {
			if err := s.repo.CreateMember(txCtx, member); err != nil {
				return err
			}
		}
		for _, state := range statesToCreate {
			if err := s.repo.UpsertUserState(txCtx, state); err != nil {
				return err
			}
		}
		if err := s.repo.BumpMembersRosterRevision(txCtx, req.ConversationId, &newCount); err != nil {
			return err
		}
		return s.scheduler.EnqueueRecompute(txCtx, GroupAvatarRecomputeTask{
			ConversationID: req.ConversationId,
			ActorID:        req.InvitedBy,
			Trigger:        "members.added",
		})
	}); err != nil {
		return err
	}
	_ = s.cache.InvalidateConversation(ctx, req.ConversationId)

	s.scheduleRosterUpdatedPublish(req.ConversationId)

	return nil
}

type TransferOwnershipRequest struct {
	ConversationId string
	OperatorId     string
	NewOwnerId     string
}

func (s *MemberService) TransferOwnership(ctx context.Context, req TransferOwnershipRequest) error {
	currentOwner, err := s.repo.FindMember(ctx, req.ConversationId, req.OperatorId)
	if err != nil || currentOwner.Role != "owner" {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "forbidden"),
			"仅群主可转让群主",
			"only owner can transfer ownership",
		)
	}
	if strings.TrimSpace(req.NewOwnerId) == "" {
		return rterr.NewInvalidArgument(rterr.ModuleChat, "新群主不能为空", "missing new owner id")
	}
	nextOwner, err := s.repo.FindMember(ctx, req.ConversationId, req.NewOwnerId)
	if err != nil {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "not_found"),
			"目标成员不存在",
			"new owner is not a member",
		)
	}
	if nextOwner.Role == "owner" {
		return nil
	}
	if err := s.repo.UpdateMemberRole(ctx, req.ConversationId, req.OperatorId, "member"); err != nil {
		return err
	}
	if err := s.repo.UpdateMemberRole(ctx, req.ConversationId, req.NewOwnerId, "owner"); err != nil {
		return err
	}
	if err := s.repo.BumpMembersRosterRevision(ctx, req.ConversationId, nil); err != nil {
		return err
	}
	_ = s.cache.InvalidateConversation(ctx, req.ConversationId)
	s.scheduleRosterUpdatedPublish(req.ConversationId)
	return nil
}

type UpdateGroupAdminsRequest struct {
	ConversationId string
	OperatorId     string
	AdminIds       []string
}

func (s *MemberService) UpdateGroupAdmins(ctx context.Context, req UpdateGroupAdminsRequest) error {
	operator, err := s.repo.FindMember(ctx, req.ConversationId, req.OperatorId)
	if err != nil || operator.Role != "owner" {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "forbidden"),
			"仅群主可设置管理员",
			"only owner can update group admins",
		)
	}
	adminIDs := dedupeUserIDs(req.AdminIds, req.OperatorId)
	if len(adminIDs) > 3 {
		return rterr.NewInvalidArgument(rterr.ModuleChat, "管理员数量超过上限", "too many admins")
	}
	members, err := s.repo.ListMembers(ctx, req.ConversationId, 1000, "", "", persistence.SortMembersJoinedAsc)
	if err != nil {
		return err
	}
	adminSet := make(map[string]struct{}, len(adminIDs))
	for _, id := range adminIDs {
		adminSet[id] = struct{}{}
	}
	for _, member := range members {
		if member.MemberType != "user" || member.Role == "owner" {
			continue
		}
		role := "member"
		if _, ok := adminSet[member.UserId]; ok {
			role = "admin"
		}
		if err := s.repo.UpdateMemberRole(ctx, req.ConversationId, member.UserId, role); err != nil {
			return err
		}
	}
	if err := s.repo.BumpMembersRosterRevision(ctx, req.ConversationId, nil); err != nil {
		return err
	}
	_ = s.cache.InvalidateConversation(ctx, req.ConversationId)
	s.scheduleRosterUpdatedPublish(req.ConversationId)
	return nil
}

func (s *MemberService) RemoveMember(ctx context.Context, conversationId, userId string) error {
	var newCount int
	if err := s.repo.RunInTransaction(ctx, func(txCtx context.Context) error {
		if err := s.repo.DeleteMember(txCtx, conversationId, userId); err != nil {
			return err
		}
		count, err := s.repo.CountMembers(txCtx, conversationId)
		if err != nil {
			return err
		}
		newCount = count
		if err := s.repo.BumpMembersRosterRevision(txCtx, conversationId, &newCount); err != nil {
			return err
		}
		return s.scheduler.EnqueueRecompute(txCtx, GroupAvatarRecomputeTask{
			ConversationID: conversationId,
			ActorID:        userId,
			Trigger:        "member.removed",
		})
	}); err != nil {
		return err
	}

	_ = s.cache.InvalidateConversation(ctx, conversationId)

	go func() {
		if err := s.publisher.PublishDomainEvent(context.Background(), event.MemberLeft, conversationId, userId, map[string]any{
			"memberCount": newCount,
		}); err != nil {
			slog.Error("publish MemberLeft failed", "err", err, "conversationId", conversationId, "userId", userId)
		}
	}()

	s.scheduleRosterUpdatedPublish(conversationId)

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

	newCount, err := s.repo.CountMembers(ctx, req.ConversationId)
	if err != nil {
		return err
	}
	if err := s.repo.BumpMembersRosterRevision(ctx, req.ConversationId, &newCount); err != nil {
		return err
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

	s.scheduleRosterUpdatedPublish(req.ConversationId)

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

	newCount, err := s.repo.CountMembers(ctx, conversationId)
	if err != nil {
		return err
	}
	if err := s.repo.BumpMembersRosterRevision(ctx, conversationId, &newCount); err != nil {
		return err
	}

	_ = s.cache.InvalidateConversation(ctx, conversationId)
	s.scheduleRosterUpdatedPublish(conversationId)
	return nil
}

// ListContacts and SearchContacts currently derive direct-contact style results
// from conversations the viewer can already access. This keeps the chat search
// contract usable until a dedicated social/contact graph is wired in.

func (s *MemberService) ListContacts(
	ctx context.Context,
	userID string,
	limit int,
	_ string,
) ([]map[string]any, error) {
	hits, err := s.SearchContacts(ctx, userID, "", limit)
	if err != nil {
		return nil, err
	}
	return contactHitsToMaps(hits), nil
}

func (s *MemberService) SearchContacts(
	ctx context.Context,
	userID string,
	query string,
	limit int,
) ([]ContactSearchHit, error) {
	conversations, err := listUserConversations(ctx, s.repo, userID)
	if err != nil {
		return nil, err
	}
	normalizedQuery := normalizeSearchQuery(query)
	limit = clampSearchLimit(limit, 20)
	results := make([]ContactSearchHit, 0, limit)
	seen := make(map[string]struct{}, limit)
	for _, conversation := range conversations {
		if conversation.Type != "direct" {
			continue
		}
		members, err := s.repo.ListMembers(ctx, conversation.ID, 10, "", "", persistence.SortMembersJoinedAsc)
		if err != nil {
			continue
		}
		contactID := ""
		displayName := strings.TrimSpace(conversation.Title)
		avatarURL := strings.TrimSpace(conversation.AvatarUrl)
		for _, member := range members {
			if strings.TrimSpace(member.UserId) == strings.TrimSpace(userID) {
				continue
			}
			contactID = strings.TrimSpace(member.UserId)
			if name := strings.TrimSpace(member.DisplayName); name != "" {
				displayName = name
			}
			if avatar := strings.TrimSpace(member.AvatarUrl); avatar != "" {
				avatarURL = avatar
			}
			break
		}
		if contactID == "" {
			contactID = strings.TrimSpace(conversation.ID)
		}
		if displayName == "" {
			displayName = contactID
		}
		if _, ok := seen[contactID]; ok {
			continue
		}
		hit := ContactSearchHit{
			ContactID:        contactID,
			DisplayName:      displayName,
			AvatarURL:        avatarURL,
			ConversationID:   conversation.ID,
			ConversationType: PublicConversationType(conversation.Type, conversation.CircleId),
			Subtitle:         conversation.LastMessagePreview,
			HighlightText:    displayName,
			MatchedField:     "displayName",
		}
		if normalizedQuery != "" {
			matched, highlight := containsQuery(
				[]string{
					displayName,
					contactID,
					conversation.LastMessagePreview,
				},
				normalizedQuery,
			)
			if !matched {
				continue
			}
			if highlight == "" {
				highlight = displayName
			}
			hit.HighlightText = highlight
		}
		results = append(results, hit)
		seen[contactID] = struct{}{}
		if len(results) >= limit {
			break
		}
	}
	if len(results) > limit {
		results = results[:limit]
	}
	return results, nil
}

func contactHitsToMaps(hits []ContactSearchHit) []map[string]any {
	items := make([]map[string]any, 0, len(hits))
	for _, hit := range hits {
		items = append(items, map[string]any{
			"contactId":        hit.ContactID,
			"displayName":      hit.DisplayName,
			"avatarUrl":        hit.AvatarURL,
			"conversationId":   hit.ConversationID,
			"conversationType": hit.ConversationType,
			"subtitle":         hit.Subtitle,
			"highlightText":    hit.HighlightText,
			"matchedField":     hit.MatchedField,
		})
	}
	return items
}
