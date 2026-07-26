package application

import (
	"context"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/chat-service/generated/chat/conversation"
	conversationevent "quwoquan_service/services/chat-service/generated/chat/conversation/contract/event"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

// AnnouncementMessageSender 是公告触达端口：公告发布成功后写入一条
// type=system_announcement 的会话消息（公告即触达，对齐业界群公告语义）。
type AnnouncementMessageSender interface {
	SendAnnouncementSystemMessage(ctx context.Context, conversationID, senderID, content, clientMsgID string) error
}

// SetAnnouncementMessageSender 注入公告触达端口（composition root 必须注入；
// 生产路径缺失时公告命令 fail-fast，不做静默降级）。
func (s *ConversationService) SetAnnouncementMessageSender(sender AnnouncementMessageSender) {
	s.announcementSender = sender
}

const announcementMaxRunes = 2000

type UpdateAnnouncementRequest struct {
	ConversationId string
	OperatorId     string
	Announcement   string
}

// UpdateAnnouncement 更新群公告（owner/admin）。发布非空公告成功后写入
// system_announcement 消息触达全员；公告一致为 no-op 并重放原回执。
func (s *ConversationService) UpdateAnnouncement(ctx context.Context, req UpdateAnnouncementRequest) (*model.Conversation, error) {
	scopedKey, err := scopedChatIdempotencyKey(ctx, req.OperatorId)
	if err != nil {
		return nil, err
	}
	digest, err := chatCommandDigest("UpdateAnnouncement", req)
	if err != nil {
		return nil, err
	}
	var replayed model.Conversation
	if found, err := replayChatCommand(
		ctx, s.conversationCommands, scopedKey, "UpdateAnnouncement", digest, &replayed,
	); err != nil {
		return nil, err
	} else if found {
		return &replayed, nil
	}
	conv, err := s.conversations.FindConversationByID(ctx, req.ConversationId)
	if err != nil {
		return nil, err
	}
	if err := rejectCircleGroupManaged(conv, "UpdateAnnouncement"); err != nil {
		return nil, err
	}
	if conv.Type != "group" {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"仅群聊支持群公告",
			"announcement is only supported for group conversations",
		)
	}
	operator, err := s.members.FindMember(ctx, req.ConversationId, req.OperatorId)
	if err != nil {
		return nil, chatConversationNotFoundForNonMember(
			"operator is not a member of this conversation",
		)
	}
	if conv.Status != "" && conv.Status != model.ConversationStatusActive {
		return nil, chatConversationDissolved("conversation is not active")
	}
	if operator.Role != "owner" && operator.Role != "admin" {
		return nil, chatGroupGovernanceForbidden("only owner or admin can update the announcement")
	}
	announcement := strings.TrimSpace(req.Announcement)
	if len([]rune(announcement)) > announcementMaxRunes {
		return nil, generated.AppErrorFromMessageTooLong("announcement exceeds length limit")
	}
	if conv.Announcement == announcement {
		// no-op：公告一致，持久化回执但不产生事件、不重复触达。
		receipt, receiptErr := chatCommandReceipt(scopedKey, "UpdateAnnouncement", digest, conv.ID, conv)
		if receiptErr != nil {
			return nil, receiptErr
		}
		if err := s.conversationCommands.CommitAggregateCommand(ctx, receipt, nil); err != nil {
			return nil, mapChatIdempotencyError(err)
		}
		return conv, nil
	}
	if announcement != "" && s.announcementSender == nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, rterr.KindSystem, "internal_error"),
			"消息服务异常，请稍后重试",
			"announcement message sender is not wired",
		)
	}
	now := time.Now()
	conv.Announcement = announcement
	conv.AnnouncementUpdatedBy = req.OperatorId
	conv.AnnouncementUpdatedAt = &now
	conv.UpdatedAt = now
	if err := s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		if err := s.conversations.UpdateConversation(txCtx, conv.ID, conv); err != nil {
			return err
		}
		receipt, receiptErr := chatCommandReceipt(scopedKey, "UpdateAnnouncement", digest, conv.ID, conv)
		if receiptErr != nil {
			return receiptErr
		}
		return mapChatIdempotencyError(s.conversationCommands.CommitAggregateCommand(txCtx, receipt, nil))
	}); err != nil {
		return nil, err
	}
	_ = s.cache.InvalidateConversation(ctx, conv.ID)
	if announcement != "" {
		// 公告即触达：seq 分配、outbox、未读投影复用消息主线。
		// clientMsgId 绑定命令 digest，重试不会重复触达。
		if err := s.announcementSender.SendAnnouncementSystemMessage(
			ctx, conv.ID, req.OperatorId, announcement, "announcement:"+digest,
		); err != nil {
			return nil, err
		}
	}
	return conv, nil
}

type UpdateGroupGovernanceSettingsRequest struct {
	ConversationId          string
	OperatorId              string
	NameEditableByAdminOnly *bool
}

// UpdateGroupGovernanceSettings 更新群治理开关（owner/admin）。
// 变更递增 roster revision 并发布 RosterUpdated(aspects=[governance]) 供端侧定点刷新。
func (s *ConversationService) UpdateGroupGovernanceSettings(
	ctx context.Context,
	req UpdateGroupGovernanceSettingsRequest,
) (*model.Conversation, error) {
	scopedKey, err := scopedChatIdempotencyKey(ctx, req.OperatorId)
	if err != nil {
		return nil, err
	}
	digest, err := chatCommandDigest("UpdateGroupGovernanceSettings", req)
	if err != nil {
		return nil, err
	}
	var replayed model.Conversation
	if found, err := replayChatCommand(
		ctx, s.conversationCommands, scopedKey, "UpdateGroupGovernanceSettings", digest, &replayed,
	); err != nil {
		return nil, err
	} else if found {
		return &replayed, nil
	}
	conv, err := s.conversations.FindConversationByID(ctx, req.ConversationId)
	if err != nil {
		return nil, err
	}
	if err := rejectCircleGroupManaged(conv, "UpdateGroupGovernanceSettings"); err != nil {
		return nil, err
	}
	if conv.Type != "group" {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"仅群聊支持群治理设置",
			"governance settings are only supported for group conversations",
		)
	}
	operator, err := s.members.FindMember(ctx, req.ConversationId, req.OperatorId)
	if err != nil {
		return nil, chatConversationNotFoundForNonMember(
			"operator is not a member of this conversation",
		)
	}
	if conv.Status != "" && conv.Status != model.ConversationStatusActive {
		return nil, chatConversationDissolved("conversation is not active")
	}
	if operator.Role != "owner" && operator.Role != "admin" {
		return nil, chatGroupGovernanceForbidden("only owner or admin can update governance settings")
	}
	changed := false
	if req.NameEditableByAdminOnly != nil && conv.NameEditableByAdminOnly != *req.NameEditableByAdminOnly {
		conv.NameEditableByAdminOnly = *req.NameEditableByAdminOnly
		changed = true
	}
	receipt, err := chatCommandReceipt(scopedKey, "UpdateGroupGovernanceSettings", digest, conv.ID, conv)
	if err != nil {
		return nil, err
	}
	if !changed {
		// no-op：设置一致，持久化回执但不递增 roster revision、不产生事件。
		if err := s.conversationCommands.CommitAggregateCommand(ctx, receipt, nil); err != nil {
			return nil, mapChatIdempotencyError(err)
		}
		return conv, nil
	}
	conv.MembersRosterRevision++
	conv.UpdatedAt = time.Now()
	if err := s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		if err := s.conversations.UpdateConversation(txCtx, conv.ID, conv); err != nil {
			return err
		}
		return mapChatIdempotencyError(s.conversationCommands.CommitAggregateCommand(
			txCtx,
			receipt,
			[]AggregateOutboxEvent{{
				EventID:        chatAggregateEventID(scopedKey, string(conversationevent.ConversationRosterUpdated)),
				EventType:      string(conversationevent.ConversationRosterUpdated),
				AggregateID:    conv.ID,
				ConversationID: conv.ID,
				ActorID:        req.OperatorId,
				Payload: map[string]any{
					"membersRosterRevision": conv.MembersRosterRevision,
					"updatedAt":             conv.UpdatedAt,
					"aspects":               []string{"governance"},
				},
			}},
		))
	}); err != nil {
		return nil, err
	}
	_ = s.cache.InvalidateConversation(ctx, conv.ID)
	return conv, nil
}
