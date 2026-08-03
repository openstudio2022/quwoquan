package application

import (
	"context"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	membershipevent "quwoquan_service/services/chat-service/generated/chat/conversation_membership/contract/event"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
)

type InviteAssistantRequest = membershipapp.InviteAssistantRequest

func (s *MemberService) InviteAssistant(ctx context.Context, req InviteAssistantRequest) error {
	if strings.TrimSpace(req.InvitedByAccountID) == "" {
		return rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"邀请者身份无效",
			"InviteAssistant requires a trusted inviter account",
		)
	}
	conv, _, err := s.requireActiveConversationMember(ctx, req.ConversationId, req.InvitedBy)
	if err != nil {
		return err
	}
	if err := rejectSourceManagedConversation(conv, "InviteAssistant"); err != nil {
		return err
	}
	scopedKey, err := scopedChatIdempotencyKey(ctx, req.InvitedBy)
	if err != nil {
		return err
	}
	digest, err := chatCommandDigest("InviteAssistant", req)
	if err != nil {
		return err
	}
	if found, err := replayChatCommand(
		ctx, s.membershipCommands, scopedKey, "InviteAssistant", digest, nil,
	); err != nil || found {
		return err
	}
	receipt, err := chatCommandReceipt(scopedKey, "InviteAssistant", digest, req.ConversationId, nil)
	if err != nil {
		return err
	}
	existing, _ := s.members.FindAssistantMember(ctx, req.ConversationId)
	if existing != nil {
		// no-op：助手已在会话，持久化回执且不产生事件。
		return mapChatIdempotencyError(
			s.membershipCommands.CommitAggregateCommand(ctx, receipt, nil),
		)
	}

	now := time.Now()
	member := &model.ConversationMember{
		ID:             generateID(),
		ConversationId: req.ConversationId,
		UserId:         "assistant",
		MemberType:     "assistant",
		Role:           "member",
		InvitedBy:      req.InvitedBy,
		JoinedAt:       now,
	}
	if err := s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		if err := s.members.CreateMember(txCtx, member); err != nil {
			return err
		}
		newCount, err := s.members.CountMembers(txCtx, req.ConversationId)
		if err != nil {
			return err
		}
		if err := s.roster.BumpMembersRosterRevision(txCtx, req.ConversationId, &newCount); err != nil {
			return err
		}
		events := []AggregateOutboxEvent{{
			EventID: chatAggregateEventID(
				scopedKey,
				string(membershipevent.ConversationMemberAdded)+"\x00assistant",
			),
			EventType:      string(membershipevent.ConversationMemberAdded),
			AggregateID:    member.ID,
			ConversationID: req.ConversationId,
			ActorID:        req.InvitedBy,
			Payload: map[string]any{
				"memberId":           member.ID,
				"userId":             member.UserId,
				"memberType":         member.MemberType,
				"role":               member.Role,
				"invitedBy":          member.InvitedBy,
				"invitedByAccountId": req.InvitedByAccountID,
				"memberCount":        newCount,
				"joinedAt":           member.JoinedAt,
			},
		}}
		rosterEvent, rosterErr := s.rosterUpdatedEvent(
			txCtx, scopedKey, req.ConversationId, req.InvitedBy, []string{"members"},
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

type RemoveAssistantRequest = membershipapp.RemoveAssistantRequest

func (s *MemberService) RemoveAssistant(ctx context.Context, req RemoveAssistantRequest) error {
	if strings.TrimSpace(req.RemovedByAccountID) == "" {
		return rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"移除操作者身份无效",
			"RemoveAssistant requires a trusted operator account",
		)
	}
	conv, _, err := s.requireActiveConversationMember(ctx, req.ConversationId, req.RemovedBy)
	if err != nil {
		return err
	}
	if err := rejectSourceManagedConversation(conv, "RemoveAssistant"); err != nil {
		return err
	}
	scopedKey, err := scopedChatIdempotencyKey(ctx, req.RemovedBy)
	if err != nil {
		return err
	}
	digest, err := chatCommandDigest("RemoveAssistant", req)
	if err != nil {
		return err
	}
	if found, err := replayChatCommand(
		ctx, s.membershipCommands, scopedKey, "RemoveAssistant", digest, nil,
	); err != nil || found {
		return err
	}
	receipt, err := chatCommandReceipt(scopedKey, "RemoveAssistant", digest, req.ConversationId, nil)
	if err != nil {
		return err
	}
	assistant, err := s.members.FindAssistantMember(ctx, req.ConversationId)
	if err != nil {
		// no-op：会话内无助手，持久化回执且不产生事件。
		return mapChatIdempotencyError(
			s.membershipCommands.CommitAggregateCommand(ctx, receipt, nil),
		)
	}

	if err := s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		if err := s.members.DeleteMember(txCtx, req.ConversationId, assistant.UserId); err != nil {
			return err
		}
		newCount, err := s.members.CountMembers(txCtx, req.ConversationId)
		if err != nil {
			return err
		}
		if err := s.roster.BumpMembersRosterRevision(txCtx, req.ConversationId, &newCount); err != nil {
			return err
		}
		events := []AggregateOutboxEvent{{
			EventID: chatAggregateEventID(
				scopedKey,
				string(membershipevent.ConversationMemberRemoved)+"\x00assistant",
			),
			EventType:      string(membershipevent.ConversationMemberRemoved),
			AggregateID:    assistant.ID,
			ConversationID: req.ConversationId,
			ActorID:        req.RemovedBy,
			Payload: map[string]any{
				"memberId":           assistant.ID,
				"userId":             assistant.UserId,
				"memberType":         assistant.MemberType,
				"removedBy":          req.RemovedBy,
				"removedByAccountId": req.RemovedByAccountID,
				"memberCount":        newCount,
			},
		}}
		rosterEvent, rosterErr := s.rosterUpdatedEvent(
			txCtx, scopedKey, req.ConversationId, req.RemovedBy, []string{"members"},
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
