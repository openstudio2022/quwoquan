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
	relationships  RelationshipGate
	socialContacts SocialContactResolver
	media          GroupAvatarAssetizer
	syncPublisher  UserSyncPublisher
	scheduler      GroupAvatarTaskScheduler
	rosterMu       sync.Mutex
	rosterTimers   map[string]*time.Timer
	rosterDebounce time.Duration
}

type MemberServiceOption func(*MemberService)

func WithSocialContactResolver(resolver SocialContactResolver) MemberServiceOption {
	return func(s *MemberService) {
		if resolver != nil {
			s.socialContacts = resolver
		}
	}
}

func WithRelationshipGate(gate RelationshipGate) MemberServiceOption {
	return func(s *MemberService) {
		if gate != nil {
			s.relationships = gate
		}
	}
}

func NewMemberService(
	repo persistence.ChatRepository,
	cache *cache.ConversationCache,
	publisher EventPublisher,
	profiles ProfileSnapshotResolver,
	media GroupAvatarAssetizer,
	syncPublisher UserSyncPublisher,
	scheduler GroupAvatarTaskScheduler,
	opts ...MemberServiceOption,
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
	svc := &MemberService{
		repo: repo, cache: cache, publisher: publisher, profiles: profiles, media: media, syncPublisher: syncPublisher, scheduler: scheduler,
		socialContacts: noopSocialContactResolver{},
		relationships:  nil,
		rosterTimers:   make(map[string]*time.Timer),
		rosterDebounce: 80 * time.Millisecond,
	}
	for _, opt := range opts {
		if opt != nil {
			opt(svc)
		}
	}
	return svc
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

func (s *MemberService) ListContacts(
	ctx context.Context,
	userID string,
	limit int,
	_ string,
) ([]map[string]any, error) {
	hits, err := s.combinedContactHits(ctx, userID, "", limit)
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
	return s.combinedContactHits(ctx, userID, query, limit)
}

func contactHitsToMaps(hits []ContactSearchHit) []map[string]any {
	items := make([]map[string]any, 0, len(hits))
	for _, hit := range hits {
		items = append(items, map[string]any{
			"contactId":        hit.ContactID,
			"displayName":      hit.DisplayName,
			"avatarUrl":        hit.AvatarURL,
			"bio":              hit.Bio,
			"metFrom":          hit.MetFrom,
			"lastInteraction":  hit.LastInteraction,
			"relationState":    hit.RelationState,
			"conversationId":   hit.ConversationID,
			"conversationType": hit.ConversationType,
			"subtitle":         hit.Subtitle,
			"highlightText":    hit.HighlightText,
			"matchedField":     hit.MatchedField,
			"source":           hit.Source,
			"isStarred":        hit.IsStarred,
		})
	}
	return items
}

func (s *MemberService) combinedContactHits(
	ctx context.Context,
	userID string,
	query string,
	limit int,
) ([]ContactSearchHit, error) {
	limit = clampSearchLimit(limit, 20)
	normalizedQuery := normalizeSearchQuery(query)
	results := make([]ContactSearchHit, 0, limit)
	indexByID := make(map[string]int, limit)

	conversationHits, err := s.conversationContactHits(ctx, userID, normalizedQuery, limit)
	if err != nil {
		return nil, err
	}
	for _, hit := range conversationHits {
		if !matchesContactQuery(hit, normalizedQuery) {
			continue
		}
		if !s.canExposeContact(ctx, userID, hit) {
			continue
		}
		indexByID[hit.ContactID] = len(results)
		results = append(results, hit)
		if len(results) >= limit {
			return results, nil
		}
	}

	socialHits, err := s.socialContactHits(ctx, userID, normalizedQuery, limit)
	if err != nil {
		slog.Warn("social contact resolution failed", "err", err, "userID", userID)
		socialHits = nil
	}
	for _, hit := range socialHits {
		if !matchesContactQuery(hit, normalizedQuery) {
			continue
		}
		if !s.canExposeContact(ctx, userID, hit) {
			continue
		}
		if idx, ok := indexByID[hit.ContactID]; ok {
			results[idx] = mergeContactSearchHit(results[idx], hit)
			continue
		}
		indexByID[hit.ContactID] = len(results)
		results = append(results, hit)
		if len(results) >= limit {
			break
		}
	}

	if len(results) > limit {
		results = results[:limit]
	}
	return results, nil
}

func (s *MemberService) canExposeContact(
	ctx context.Context,
	viewerID string,
	hit ContactSearchHit,
) bool {
	if s.relationships == nil {
		return true
	}
	contactID := strings.TrimSpace(hit.ContactID)
	if contactID == "" {
		return true
	}
	capability, err := s.relationships.GetCapability(ctx, viewerID, contactID)
	if err != nil {
		slog.Warn(
			"relationship gate check failed for contacts",
			"err",
			err,
			"viewerID",
			viewerID,
			"contactID",
			contactID,
		)
		return true
	}
	return !capability.IsBlocked && !capability.IsBlockedBy
}

func (s *MemberService) conversationContactHits(
	ctx context.Context,
	userID string,
	query string,
	limit int,
) ([]ContactSearchHit, error) {
	conversations, err := listUserConversations(ctx, s.repo, userID)
	if err != nil {
		return nil, err
	}
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
			Bio:              strings.TrimSpace(conversation.LastMessagePreview),
			MetFrom:          "会话",
			LastInteraction:  conversation.LastMessageTime.UTC().Format(time.RFC3339),
			RelationState:    "not_following",
			ConversationID:   conversation.ID,
			ConversationType: PublicConversationType(conversation.Type, conversation.CircleId),
			Source:           "conversation",
			Subtitle:         conversation.LastMessagePreview,
			HighlightText:    displayName,
			MatchedField:     "displayName",
		}
		if query != "" && !matchesContactQuery(hit, query) {
			continue
		}
		if query != "" {
			hit.HighlightText = highlightContactHit(hit, query)
		}
		results = append(results, hit)
		seen[contactID] = struct{}{}
		if len(results) >= limit {
			break
		}
	}
	return results, nil
}

func (s *MemberService) socialContactHits(
	ctx context.Context,
	userID string,
	query string,
	limit int,
) ([]ContactSearchHit, error) {
	if s.socialContacts == nil {
		return nil, nil
	}
	seeds, err := s.socialContacts.ListContacts(ctx, userID, limit)
	if err != nil {
		return nil, err
	}
	if len(seeds) == 0 {
		return nil, nil
	}
	profiles, err := s.profiles.ResolveMany(ctx, socialSeedIDs(seeds))
	if err != nil {
		profiles = map[string]ProfileSnapshot{}
	}
	hits := make([]ContactSearchHit, 0, len(seeds))
	for _, seed := range seeds {
		hit := socialSeedToHit(seed, profiles[seed.UserID])
		if query != "" && !matchesContactQuery(hit, query) {
			continue
		}
		if query != "" {
			hit.HighlightText = highlightContactHit(hit, query)
		}
		hits = append(hits, hit)
		if len(hits) >= limit {
			break
		}
	}
	return hits, nil
}

func socialSeedIDs(seeds []SocialContactSeed) []string {
	ids := make([]string, 0, len(seeds))
	seen := make(map[string]struct{}, len(seeds))
	for _, seed := range seeds {
		id := strings.TrimSpace(seed.UserID)
		if id == "" {
			continue
		}
		if _, ok := seen[id]; ok {
			continue
		}
		seen[id] = struct{}{}
		ids = append(ids, id)
	}
	return ids
}

func socialSeedToHit(seed SocialContactSeed, profile ProfileSnapshot) ContactSearchHit {
	displayName := strings.TrimSpace(seed.DisplayName)
	avatarURL := strings.TrimSpace(seed.AvatarURL)
	bio := strings.TrimSpace(seed.Bio)
	if displayName == "" {
		displayName = strings.TrimSpace(profile.DisplayName)
	}
	if avatarURL == "" {
		avatarURL = strings.TrimSpace(profile.AvatarURL)
	}
	if bio == "" {
		bio = strings.TrimSpace(profile.Bio)
	}
	relationState := normalizeRelationState(seed.RelationState)
	source := normalizeContactSource(seed.Source)
	if source == "" {
		source = normalizeContactSource(seed.MetFrom)
	}
	if source == "" {
		source = "contact_discovery"
	}
	subtitle := firstNonEmpty(bio, seed.MetFrom, seed.LastInteraction)
	if subtitle == "" {
		subtitle = displayName
	}
	return ContactSearchHit{
		ContactID:       strings.TrimSpace(seed.UserID),
		DisplayName:     displayName,
		AvatarURL:       avatarURL,
		Bio:             bio,
		MetFrom:         strings.TrimSpace(seed.MetFrom),
		LastInteraction: strings.TrimSpace(seed.LastInteraction),
		RelationState:   relationState,
		Source:          source,
		Subtitle:        subtitle,
		HighlightText:   displayName,
		MatchedField:    "displayName",
		IsStarred:       seed.IsStarred,
	}
}

func mergeContactSearchHit(base, next ContactSearchHit) ContactSearchHit {
	if base.ContactID != next.ContactID {
		return base
	}
	if base.DisplayName == "" {
		base.DisplayName = next.DisplayName
	}
	if base.AvatarURL == "" {
		base.AvatarURL = next.AvatarURL
	}
	if base.Bio == "" {
		base.Bio = next.Bio
	}
	if base.MetFrom == "" {
		base.MetFrom = next.MetFrom
	}
	if base.LastInteraction == "" {
		base.LastInteraction = next.LastInteraction
	}
	base.RelationState = mergeRelationState(base.RelationState, next.RelationState)
	if base.Source == "" || contactSourcePriority(next.Source) < contactSourcePriority(base.Source) {
		base.Source = next.Source
	}
	if base.Subtitle == "" {
		base.Subtitle = next.Subtitle
	}
	if base.HighlightText == "" {
		base.HighlightText = next.HighlightText
	}
	if base.MatchedField == "" {
		base.MatchedField = next.MatchedField
	}
	base.IsStarred = base.IsStarred || next.IsStarred
	return base
}

func matchesContactQuery(hit ContactSearchHit, query string) bool {
	if query == "" {
		return true
	}
	matched, _ := containsQuery(
		[]string{
			hit.DisplayName,
			hit.ContactID,
			hit.Bio,
			hit.MetFrom,
			hit.LastInteraction,
			hit.Subtitle,
			hit.Source,
			hit.RelationState,
		},
		query,
	)
	return matched
}

func highlightContactHit(hit ContactSearchHit, query string) string {
	if query == "" {
		return hit.DisplayName
	}
	_, highlight := containsQuery(
		[]string{
			hit.DisplayName,
			hit.Bio,
			hit.MetFrom,
			hit.LastInteraction,
			hit.Subtitle,
			hit.Source,
			hit.RelationState,
		},
		query,
	)
	if highlight == "" {
		highlight = hit.DisplayName
	}
	return highlight
}

func mergeRelationState(existing, next string) string {
	existing = normalizeRelationState(existing)
	next = normalizeRelationState(next)
	if existing == "mutual" || next == "mutual" {
		return "mutual"
	}
	if (existing == "following" && next == "followed_by") || (existing == "followed_by" && next == "following") {
		return "mutual"
	}
	if existing == "following" || next == "following" {
		return "following"
	}
	if existing == "followed_by" || next == "followed_by" {
		return "followed_by"
	}
	return "not_following"
}

func normalizeRelationState(raw string) string {
	switch strings.TrimSpace(raw) {
	case "self", "mutual", "following", "followed_by", "not_following":
		return strings.TrimSpace(raw)
	default:
		return "not_following"
	}
}

func normalizeContactSource(raw string) string {
	switch strings.TrimSpace(raw) {
	case "mutual", "following", "conversation", "contact_discovery", "circle", "group":
		return strings.TrimSpace(raw)
	default:
		return ""
	}
}

func contactSourcePriority(source string) int {
	switch normalizeContactSource(source) {
	case "conversation":
		return 0
	case "mutual":
		return 1
	case "following":
		return 2
	case "contact_discovery":
		return 3
	case "circle":
		return 4
	case "group":
		return 5
	default:
		return 6
	}
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}
