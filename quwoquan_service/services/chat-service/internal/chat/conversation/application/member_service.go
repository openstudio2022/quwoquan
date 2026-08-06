package application

import (
	"context"
	"errors"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	conversationevent "quwoquan_service/services/chat-service/generated/chat/conversation/contract/event"
	membershipevent "quwoquan_service/services/chat-service/generated/chat/conversation_membership/contract/event"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
)

type MemberService struct {
	transactions                      TransactionRunner
	conversations                     ConversationStore
	members                           MemberStore
	roster                            ConversationRosterProjector
	userStates                        UserStateStore
	circleGroupMembershipProjections  CircleGroupMembershipProjectionStore
	circleGroupChatBindingProjections CircleGroupChatBindingProjectionStore
	membershipCommands                AggregateCommandStore
	cache                             ConversationCache
	publisher                         EventPublisher
	profiles                          ProfileSnapshotResolver
	relationships                     RelationshipGate
	socialContacts                    SocialContactResolver
	circles                           CircleListResolver
	media                             GroupAvatarAssetizer
	syncPublisher                     UserSyncPublisher
	scheduler                         GroupAvatarTaskScheduler
	contactIntersections              ContactIntersectionResolver
}

type MemberServiceOption func(*MemberService)

func WithSocialContactResolver(resolver SocialContactResolver) MemberServiceOption {
	return func(s *MemberService) {
		if resolver != nil {
			s.socialContacts = resolver
		}
	}
}

func WithCircleListResolver(resolver CircleListResolver) MemberServiceOption {
	return func(s *MemberService) {
		if resolver != nil {
			s.circles = resolver
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

func WithContactIntersectionResolver(
	resolver ContactIntersectionResolver,
) MemberServiceOption {
	return func(s *MemberService) {
		if resolver != nil {
			s.contactIntersections = resolver
		}
	}
}

func NewMemberService(
	storage ChatStoragePorts,
	cache ConversationCache,
	publisher EventPublisher,
	profiles ProfileSnapshotResolver,
	media GroupAvatarAssetizer,
	syncPublisher UserSyncPublisher,
	scheduler GroupAvatarTaskScheduler,
	opts ...MemberServiceOption,
) *MemberService {
	publisher = requireEventPublisher(publisher)
	if profiles == nil {
		profiles = noopProfileResolver{}
	}
	scheduler = requireGroupAvatarTaskScheduler(scheduler)
	svc := &MemberService{
		transactions:                      storage.Transactions,
		conversations:                     storage.Conversations,
		members:                           storage.Members,
		roster:                            storage.RosterProjection,
		userStates:                        storage.UserStates,
		circleGroupMembershipProjections:  storage.CircleGroupMembershipProjections,
		circleGroupChatBindingProjections: storage.CircleGroupChatBindingProjections,
		membershipCommands:                storage.MembershipCommands,
		cache:                             cache,
		publisher:                         publisher,
		profiles:                          profiles,
		media:                             media,
		syncPublisher:                     syncPublisher,
		scheduler:                         scheduler,
		socialContacts:                    noopSocialContactResolver{},
		circles:                           noopCircleListResolver{},
		relationships:                     nil,
		contactIntersections:              emptyContactIntersectionResolver{},
	}
	for _, opt := range opts {
		if opt != nil {
			opt(svc)
		}
	}
	return svc
}

func (s *MemberService) ListContactIntersectionSummaries(
	ctx context.Context,
	viewerPersonaID string,
	contactPersonaID string,
) ([]ContactIntersectionSummary, error) {
	return s.contactIntersections.ListContactIntersections(
		ctx,
		strings.TrimSpace(viewerPersonaID),
		strings.TrimSpace(contactPersonaID),
		2,
	)
}

type ListMembersRequest = membershipapp.ListMembersRequest

func (s *MemberService) ListMembers(ctx context.Context, req ListMembersRequest) ([]model.ConversationMember, error) {
	if viewerID := strings.TrimSpace(req.ViewerId); viewerID != "" {
		if _, _, err := s.requireActiveConversationMember(
			ctx,
			req.ConversationId,
			viewerID,
		); err != nil {
			return nil, err
		}
	}
	return s.members.ListMembers(ctx, req.ConversationId, ListMembersQuery{
		Limit:  req.Limit,
		Cursor: req.Cursor,
		Role:   req.Role,
		Query:  req.Query,
		Sort:   NormalizeMemberListSort(req.Sort),
	})
}

func (s *MemberService) GetMember(ctx context.Context, conversationId, userId string) (*model.ConversationMember, error) {
	return s.members.FindMember(ctx, conversationId, userId)
}

type AssistantDeliveryMembershipView = membershipapp.AssistantDeliveryMembershipView

func (s *MemberService) ResolveAssistantDeliveryMembership(
	ctx context.Context,
	conversationID string,
	creatorPersonaID string,
	assistantMemberID string,
) (AssistantDeliveryMembershipView, error) {
	return resolveAssistantDeliveryMembership(
		ctx,
		s.members,
		conversationID,
		creatorPersonaID,
		assistantMemberID,
	)
}

func resolveAssistantDeliveryMembership(
	ctx context.Context,
	members MemberStore,
	conversationID string,
	creatorPersonaID string,
	assistantMemberID string,
) (AssistantDeliveryMembershipView, error) {
	conversationID = strings.TrimSpace(conversationID)
	creatorPersonaID = strings.TrimSpace(creatorPersonaID)
	assistantMemberID = strings.TrimSpace(assistantMemberID)
	if conversationID == "" || creatorPersonaID == "" {
		return AssistantDeliveryMembershipView{}, rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"会话与创建者 Persona 均不能为空",
			"conversation and creator persona are required",
		)
	}

	view := AssistantDeliveryMembershipView{}
	if _, err := members.FindMember(
		ctx,
		conversationID,
		creatorPersonaID,
	); err == nil {
		view.CreatorMember = true
	} else if !errors.Is(err, model.ErrMemberNotFound) {
		return AssistantDeliveryMembershipView{}, err
	}

	assistantMember, err := members.FindAssistantMember(
		ctx,
		conversationID,
	)
	if err == nil {
		view.AssistantMember = assistantMemberID == "" ||
			strings.TrimSpace(assistantMember.UserId) == assistantMemberID
	} else if !errors.Is(err, model.ErrMemberNotFound) {
		return AssistantDeliveryMembershipView{}, err
	}
	return view, nil
}

// rosterUpdatedEvent 在命令事务内读回最新 roster revision，构造与 state
// 同事务提交的 ConversationRosterUpdated 事件。
func (s *MemberService) rosterUpdatedEvent(
	ctx context.Context,
	scopedKey string,
	conversationID string,
	actorID string,
	aspects []string,
) (AggregateOutboxEvent, error) {
	conv, err := s.conversations.FindConversationByID(ctx, conversationID)
	if err != nil {
		return AggregateOutboxEvent{}, err
	}
	return AggregateOutboxEvent{
		EventID:        chatAggregateEventID(scopedKey, string(conversationevent.ConversationRosterUpdated)),
		EventType:      string(conversationevent.ConversationRosterUpdated),
		AggregateID:    conversationID,
		ConversationID: conversationID,
		ActorID:        actorID,
		Payload: map[string]any{
			"membersRosterRevision": conv.MembersRosterRevision,
			"updatedAt":             conv.UpdatedAt,
			"aspects":               aspects,
		},
	}, nil
}

// requireActiveConversationMember 是成员命令的共享授权门：
// 会话必须存在且 active（dissolved 返回 conversation_dissolved），
// 操作者必须是活跃成员（非成员统一 not_found，不泄漏会话存在性）。
func (s *MemberService) requireActiveConversationMember(
	ctx context.Context,
	conversationID string,
	operatorID string,
) (*model.Conversation, *model.ConversationMember, error) {
	return requireActiveConversationMember(
		ctx,
		s.conversations,
		s.members,
		conversationID,
		operatorID,
	)
}

// validateAddedMembers 与建群 validateGroupInitialMembers 同源：
// 每个新成员必须与操作者互关且无屏蔽关系；圈子绑定群由圈子加入语义治理，跳过互关。
func (s *MemberService) validateAddedMembers(
	ctx context.Context,
	conv model.Conversation,
	operatorID string,
	memberIDs []string,
) error {
	if IsManagedConversation(conv) {
		return nil
	}
	if s.relationships == nil {
		return chatBlocked("relationship gate unavailable; adding members is fail-closed")
	}
	for _, memberID := range memberIDs {
		capability, err := s.relationships.GetCapability(ctx, operatorID, memberID)
		if err != nil {
			return err
		}
		if capability.IsBlocked || capability.IsBlockedBy {
			return chatGroupMemberBlocked("added member blocked by relationship gate")
		}
		if !capability.IsMutual {
			return chatGroupMemberNotMutual("adding members requires mutual follow with each invitee")
		}
	}
	return nil
}

type AddMembersRequest = membershipapp.AddMembersRequest

func (s *MemberService) AddMembers(ctx context.Context, req AddMembersRequest) error {
	conv, _, err := s.requireActiveConversationMember(ctx, req.ConversationId, req.InvitedBy)
	if err != nil {
		return err
	}
	if err := rejectSourceManagedConversation(conv, "AddMembers"); err != nil {
		return err
	}
	userIDs := dedupeUserIDs(req.UserIds)

	currentCount, err := s.members.CountUserMembers(ctx, req.ConversationId)
	if err != nil {
		return err
	}

	newUserIDs := make([]string, 0, len(userIDs))
	for _, userId := range userIDs {
		if _, err := s.members.FindMember(ctx, req.ConversationId, userId); err == nil {
			continue
		}
		newUserIDs = append(newUserIDs, userId)
	}

	if currentCount+len(newUserIDs) > conv.MaxGroupSize {
		return chatGroupFull("group size exceeded")
	}
	if err := s.validateAddedMembers(ctx, *conv, req.InvitedBy, newUserIDs); err != nil {
		return err
	}

	profMap, _ := s.profiles.ResolveMany(ctx, newUserIDs)
	lookup := func(uid string) (string, string, string, string, int) {
		if p, ok := profMap[uid]; ok {
			return p.UserHandle, p.DisplayName, p.AvatarURL, p.AvatarAssetID, p.AvatarVersion
		}
		return "", "", "", "", 0
	}

	now := time.Now()
	membersToCreate := make([]*model.ConversationMember, 0, len(newUserIDs))
	statesToCreate := make([]*model.ConversationUserState, 0, len(newUserIDs))
	for _, userId := range newUserIDs {
		userHandle, dn, av, assetID, avatarVersion := lookup(userId)
		membersToCreate = append(membersToCreate, &model.ConversationMember{
			ID:             generateID(),
			ConversationId: req.ConversationId,
			UserId:         userId,
			UserHandle:     userHandle,
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

	scopedKey, err := scopedChatIdempotencyKey(ctx, req.InvitedBy)
	if err != nil {
		return err
	}
	digest, err := chatCommandDigest("AddMembers", req)
	if err != nil {
		return err
	}
	if found, err := replayChatCommand(
		ctx, s.membershipCommands, scopedKey, "AddMembers", digest, nil,
	); err != nil || found {
		return err
	}

	if len(membersToCreate) == 0 {
		// no-op：全部目标成员已在群，持久化回执且不产生事件。
		receipt, receiptErr := chatCommandReceipt(scopedKey, "AddMembers", digest, req.ConversationId, nil)
		if receiptErr != nil {
			return receiptErr
		}
		return mapChatIdempotencyError(
			s.membershipCommands.CommitAggregateCommand(ctx, receipt, nil),
		)
	}

	newCount := currentCount + len(membersToCreate)
	if err := s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		for _, member := range membersToCreate {
			if err := s.members.CreateMember(txCtx, member); err != nil {
				return err
			}
		}
		for _, state := range statesToCreate {
			if err := s.userStates.UpsertUserState(txCtx, state); err != nil {
				return err
			}
		}
		if err := s.roster.BumpMembersRosterRevision(txCtx, req.ConversationId, &newCount); err != nil {
			return err
		}
		events := make([]AggregateOutboxEvent, 0, len(membersToCreate)+1)
		for _, member := range membersToCreate {
			events = append(events, AggregateOutboxEvent{
				EventID: chatAggregateEventID(
					scopedKey,
					string(membershipevent.ConversationMemberAdded)+"\x00"+member.UserId,
				),
				EventType:      string(membershipevent.ConversationMemberAdded),
				AggregateID:    member.ID,
				ConversationID: req.ConversationId,
				ActorID:        req.InvitedBy,
				Payload: map[string]any{
					"memberId":    member.ID,
					"userId":      member.UserId,
					"displayName": member.DisplayName,
					"memberType":  member.MemberType,
					"role":        member.Role,
					"invitedBy":   member.InvitedBy,
					"memberCount": newCount,
					"joinedAt":    member.JoinedAt,
				},
			})
		}
		rosterEvent, rosterErr := s.rosterUpdatedEvent(
			txCtx, scopedKey, req.ConversationId, req.InvitedBy, []string{"members"},
		)
		if rosterErr != nil {
			return rosterErr
		}
		events = append(events, rosterEvent)
		receipt, receiptErr := chatCommandReceipt(scopedKey, "AddMembers", digest, req.ConversationId, nil)
		if receiptErr != nil {
			return receiptErr
		}
		if commitErr := s.membershipCommands.CommitAggregateCommand(txCtx, receipt, events); commitErr != nil {
			return mapChatIdempotencyError(commitErr)
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
	return nil
}

type TransferOwnershipRequest = membershipapp.TransferOwnershipRequest

func (s *MemberService) TransferOwnership(ctx context.Context, req TransferOwnershipRequest) error {
	conv, currentOwner, err := s.requireActiveConversationMember(ctx, req.ConversationId, req.OperatorId)
	if err != nil {
		return err
	}
	if err := rejectSourceManagedConversation(conv, "TransferOwnership"); err != nil {
		return err
	}
	if currentOwner.Role != "owner" {
		return chatGroupGovernanceForbidden("only owner can transfer ownership")
	}
	scopedKey, err := scopedChatIdempotencyKey(ctx, req.OperatorId)
	if err != nil {
		return err
	}
	digest, err := chatCommandDigest("TransferOwnership", req)
	if err != nil {
		return err
	}
	if found, err := replayChatCommand(
		ctx, s.membershipCommands, scopedKey, "TransferOwnership", digest, nil,
	); err != nil || found {
		return err
	}
	if strings.TrimSpace(req.NewOwnerId) == "" {
		return rterr.NewInvalidArgument(rterr.ModuleChat, "新群主不能为空", "missing new owner id")
	}
	nextOwner, err := s.members.FindMember(ctx, req.ConversationId, req.NewOwnerId)
	if err != nil {
		return rterr.NewInvalidArgument(rterr.ModuleChat, "目标成员不存在", "new owner is not a member")
	}
	receipt, err := chatCommandReceipt(scopedKey, "TransferOwnership", digest, req.ConversationId, nil)
	if err != nil {
		return err
	}
	if nextOwner.Role == "owner" {
		// no-op：目标已是群主，持久化回执且不产生事件。
		return mapChatIdempotencyError(
			s.membershipCommands.CommitAggregateCommand(ctx, receipt, nil),
		)
	}
	if err := s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		if err := s.members.UpdateMemberRole(txCtx, req.ConversationId, req.OperatorId, "member"); err != nil {
			return err
		}
		if err := s.members.UpdateMemberRole(txCtx, req.ConversationId, req.NewOwnerId, "owner"); err != nil {
			return err
		}
		if err := s.roster.BumpMembersRosterRevision(txCtx, req.ConversationId, nil); err != nil {
			return err
		}
		events := []AggregateOutboxEvent{{
			EventID: chatAggregateEventID(
				scopedKey,
				string(membershipevent.ConversationMemberRoleChanged)+"\x00"+req.NewOwnerId,
			),
			EventType:      string(membershipevent.ConversationMemberRoleChanged),
			AggregateID:    nextOwner.ID,
			ConversationID: req.ConversationId,
			ActorID:        req.OperatorId,
			Payload: map[string]any{
				"memberId":  nextOwner.ID,
				"userId":    req.NewOwnerId,
				"role":      "owner",
				"changedBy": req.OperatorId,
			},
		}}
		rosterEvent, rosterErr := s.rosterUpdatedEvent(
			txCtx, scopedKey, req.ConversationId, req.OperatorId, []string{"members"},
		)
		if rosterErr != nil {
			return rosterErr
		}
		events = append(events, rosterEvent)
		return mapChatIdempotencyError(
			s.membershipCommands.CommitAggregateCommand(txCtx, receipt, events),
		)
	}); err != nil {
		return err
	}
	_ = s.cache.InvalidateConversation(ctx, req.ConversationId)
	return nil
}

type UpdateGroupAdminsRequest = membershipapp.UpdateGroupAdminsRequest

func (s *MemberService) UpdateGroupAdmins(ctx context.Context, req UpdateGroupAdminsRequest) error {
	conv, operator, err := s.requireActiveConversationMember(ctx, req.ConversationId, req.OperatorId)
	if err != nil {
		return err
	}
	if err := rejectSourceManagedConversation(conv, "UpdateGroupAdmins"); err != nil {
		return err
	}
	if operator.Role != "owner" {
		return chatGroupGovernanceForbidden("only owner can update group admins")
	}
	scopedKey, err := scopedChatIdempotencyKey(ctx, req.OperatorId)
	if err != nil {
		return err
	}
	digest, err := chatCommandDigest("UpdateGroupAdmins", req)
	if err != nil {
		return err
	}
	if found, err := replayChatCommand(
		ctx, s.membershipCommands, scopedKey, "UpdateGroupAdmins", digest, nil,
	); err != nil || found {
		return err
	}
	adminIDs := dedupeUserIDs(req.AdminIds, req.OperatorId)
	if len(adminIDs) > 3 {
		return rterr.NewInvalidArgument(rterr.ModuleChat, "管理员数量超过上限", "too many admins")
	}
	members, err := s.members.ListMembers(ctx, req.ConversationId, ListMembersQuery{
		Limit: 1000,
		Sort:  MemberListSortJoinedAsc,
	})
	if err != nil {
		return err
	}
	adminSet := make(map[string]struct{}, len(adminIDs))
	for _, id := range adminIDs {
		adminSet[id] = struct{}{}
	}
	type roleChange struct {
		member model.ConversationMember
		role   string
	}
	changes := make([]roleChange, 0, len(members))
	for _, member := range members {
		if member.MemberType != "user" || member.Role == "owner" {
			continue
		}
		role := "member"
		if _, ok := adminSet[member.UserId]; ok {
			role = "admin"
		}
		if member.Role != role {
			changes = append(changes, roleChange{member: member, role: role})
		}
	}
	receipt, err := chatCommandReceipt(scopedKey, "UpdateGroupAdmins", digest, req.ConversationId, nil)
	if err != nil {
		return err
	}
	if len(changes) == 0 {
		// no-op：管理员集合已一致，持久化回执且不产生事件。
		return mapChatIdempotencyError(
			s.membershipCommands.CommitAggregateCommand(ctx, receipt, nil),
		)
	}
	if err := s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		events := make([]AggregateOutboxEvent, 0, len(changes)+1)
		for _, change := range changes {
			if err := s.members.UpdateMemberRole(txCtx, req.ConversationId, change.member.UserId, change.role); err != nil {
				return err
			}
			events = append(events, AggregateOutboxEvent{
				EventID: chatAggregateEventID(
					scopedKey,
					string(membershipevent.ConversationMemberRoleChanged)+"\x00"+change.member.UserId,
				),
				EventType:      string(membershipevent.ConversationMemberRoleChanged),
				AggregateID:    change.member.ID,
				ConversationID: req.ConversationId,
				ActorID:        req.OperatorId,
				Payload: map[string]any{
					"memberId":  change.member.ID,
					"userId":    change.member.UserId,
					"role":      change.role,
					"changedBy": req.OperatorId,
				},
			})
		}
		if err := s.roster.BumpMembersRosterRevision(txCtx, req.ConversationId, nil); err != nil {
			return err
		}
		rosterEvent, rosterErr := s.rosterUpdatedEvent(
			txCtx, scopedKey, req.ConversationId, req.OperatorId, []string{"members"},
		)
		if rosterErr != nil {
			return rosterErr
		}
		events = append(events, rosterEvent)
		return mapChatIdempotencyError(
			s.membershipCommands.CommitAggregateCommand(txCtx, receipt, events),
		)
	}); err != nil {
		return err
	}
	_ = s.cache.InvalidateConversation(ctx, req.ConversationId)
	return nil
}

type RemoveMemberRequest = membershipapp.RemoveMemberRequest

func (s *MemberService) RemoveMember(ctx context.Context, req RemoveMemberRequest) error {
	operatorID := strings.TrimSpace(req.OperatorId)
	conv, operator, err := s.requireActiveConversationMember(ctx, req.ConversationId, operatorID)
	if err != nil {
		return err
	}
	if err := rejectSourceManagedConversation(conv, "RemoveMember"); err != nil {
		return err
	}
	targetID := strings.TrimSpace(req.UserId)
	if targetID == operatorID {
		return rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"退出群聊请使用退群操作",
			"self removal must use LeaveConversation",
		)
	}
	if operator.Role != "owner" && operator.Role != "admin" {
		return chatGroupGovernanceForbidden("only owner or admin can remove members")
	}
	scopedKey, err := scopedChatIdempotencyKey(ctx, operatorID)
	if err != nil {
		return err
	}
	digest, err := chatCommandDigest("RemoveMember", req)
	if err != nil {
		return err
	}
	if found, err := replayChatCommand(
		ctx, s.membershipCommands, scopedKey, "RemoveMember", digest, nil,
	); err != nil || found {
		return err
	}
	receipt, err := chatCommandReceipt(scopedKey, "RemoveMember", digest, req.ConversationId, nil)
	if err != nil {
		return err
	}
	member, err := s.members.FindMember(ctx, req.ConversationId, targetID)
	if err != nil {
		// no-op：成员已不在群，持久化回执且不产生事件。
		return mapChatIdempotencyError(
			s.membershipCommands.CommitAggregateCommand(ctx, receipt, nil),
		)
	}
	// 角色矩阵（对齐企业微信语义）：owner 可移出任何非 owner 成员；
	// admin 只能移出普通成员，不可移出 owner 或其他 admin。
	if member.Role == "owner" {
		return chatGroupGovernanceForbidden("the group owner cannot be removed")
	}
	if operator.Role == "admin" && member.Role != "member" {
		return chatGroupGovernanceForbidden("an admin can only remove regular members")
	}
	var newCount int
	if err := s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		if err := s.members.DeleteMember(txCtx, req.ConversationId, targetID); err != nil {
			return err
		}
		if err := s.userStates.DeleteUserState(txCtx, targetID, req.ConversationId); err != nil {
			return err
		}
		count, err := s.members.CountMembers(txCtx, req.ConversationId)
		if err != nil {
			return err
		}
		newCount = count
		if err := s.roster.BumpMembersRosterRevision(txCtx, req.ConversationId, &newCount); err != nil {
			return err
		}
		events := []AggregateOutboxEvent{{
			EventID: chatAggregateEventID(
				scopedKey,
				string(membershipevent.ConversationMemberRemoved)+"\x00"+targetID,
			),
			EventType:      string(membershipevent.ConversationMemberRemoved),
			AggregateID:    member.ID,
			ConversationID: req.ConversationId,
			ActorID:        operatorID,
			Payload: map[string]any{
				"conversationId": req.ConversationId,
				"memberId":       member.ID,
				"userId":         targetID,
				"memberType":     member.MemberType,
				"removedBy":      operatorID,
				"memberCount":    newCount,
			},
		}}
		rosterEvent, rosterErr := s.rosterUpdatedEvent(
			txCtx, scopedKey, req.ConversationId, operatorID, []string{"members"},
		)
		if rosterErr != nil {
			return rosterErr
		}
		events = append(events, rosterEvent)
		if commitErr := s.membershipCommands.CommitAggregateCommand(txCtx, receipt, events); commitErr != nil {
			return mapChatIdempotencyError(commitErr)
		}
		return s.scheduler.EnqueueRecompute(txCtx, GroupAvatarRecomputeTask{
			ConversationID: req.ConversationId,
			ActorID:        operatorID,
			Trigger:        "member.removed",
		})
	}); err != nil {
		return err
	}

	_ = s.cache.InvalidateConversation(ctx, req.ConversationId)
	return nil
}

type LeaveConversationRequest = membershipapp.LeaveConversationRequest

// LeaveConversation 是成员自愿退出群聊（left 语义，区别于被移出 removed）。
// 群主必须先 TransferOwnership；已不在群为 no-op 并重放原回执。
func (s *MemberService) LeaveConversation(ctx context.Context, req LeaveConversationRequest) error {
	userID := strings.TrimSpace(req.UserId)
	if userID == "" {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "unauthorized"),
			"请先登录",
			"leave conversation requires an authenticated user",
		)
	}
	conv, err := s.conversations.FindConversationByID(ctx, req.ConversationId)
	if err != nil {
		return err
	}
	if conv.Type != "group" {
		return rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"仅群聊支持退出",
			"only group conversations support leaving",
		)
	}
	if conv.Status != "" && conv.Status != model.ConversationStatusActive {
		return chatConversationDissolved("conversation is not active")
	}
	if err := rejectSourceManagedConversation(conv, "LeaveConversation"); err != nil {
		return err
	}
	scopedKey, err := scopedChatIdempotencyKey(ctx, userID)
	if err != nil {
		return err
	}
	digest, err := chatCommandDigest("LeaveConversation", req)
	if err != nil {
		return err
	}
	if found, err := replayChatCommand(
		ctx, s.membershipCommands, scopedKey, "LeaveConversation", digest, nil,
	); err != nil || found {
		return err
	}
	receipt, err := chatCommandReceipt(scopedKey, "LeaveConversation", digest, req.ConversationId, nil)
	if err != nil {
		return err
	}
	member, err := s.members.FindMember(ctx, req.ConversationId, userID)
	if err != nil {
		// no-op：已不在群，持久化回执且不产生事件。
		return mapChatIdempotencyError(
			s.membershipCommands.CommitAggregateCommand(ctx, receipt, nil),
		)
	}
	if member.Role == "owner" {
		return chatOwnerMustTransferBeforeLeave("owner must transfer ownership before leaving")
	}
	now := time.Now()
	var newCount int
	if err := s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		if err := s.members.DeleteMember(txCtx, req.ConversationId, userID); err != nil {
			return err
		}
		if err := s.userStates.DeleteUserState(txCtx, userID, req.ConversationId); err != nil {
			return err
		}
		count, err := s.members.CountMembers(txCtx, req.ConversationId)
		if err != nil {
			return err
		}
		newCount = count
		if err := s.roster.BumpMembersRosterRevision(txCtx, req.ConversationId, &newCount); err != nil {
			return err
		}
		events := []AggregateOutboxEvent{{
			EventID: chatAggregateEventID(
				scopedKey,
				string(membershipevent.ConversationMemberLeft)+"\x00"+userID,
			),
			EventType:      string(membershipevent.ConversationMemberLeft),
			AggregateID:    member.ID,
			ConversationID: req.ConversationId,
			ActorID:        userID,
			Payload: map[string]any{
				"conversationId": req.ConversationId,
				"memberId":       member.ID,
				"userId":         userID,
				"memberType":     member.MemberType,
				"memberCount":    newCount,
				"leftAt":         now,
			},
		}}
		rosterEvent, rosterErr := s.rosterUpdatedEvent(
			txCtx, scopedKey, req.ConversationId, userID, []string{"members"},
		)
		if rosterErr != nil {
			return rosterErr
		}
		events = append(events, rosterEvent)
		if commitErr := s.membershipCommands.CommitAggregateCommand(txCtx, receipt, events); commitErr != nil {
			return mapChatIdempotencyError(commitErr)
		}
		return s.scheduler.EnqueueRecompute(txCtx, GroupAvatarRecomputeTask{
			ConversationID: req.ConversationId,
			ActorID:        userID,
			Trigger:        "member.left",
		})
	}); err != nil {
		return err
	}

	_ = s.cache.InvalidateConversation(ctx, req.ConversationId)
	return nil
}
