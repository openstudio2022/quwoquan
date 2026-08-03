package application

import (
	"context"
	"errors"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/chat-service/generated/chat/conversation"
	userstateevent "quwoquan_service/services/chat-service/generated/chat/conversation_user_state/contract/event"
	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	userstateapp "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/application"
	messagemodel "quwoquan_service/services/chat-service/internal/chat/message/domain/model"
	receiptmodel "quwoquan_service/services/chat-service/internal/chat/message_receipt_fact/domain/model"
)

type MarkAsReadRequest = userstateapp.MarkAsReadRequest

// MarkAsRead 是 ConversationUserState 聚合的已读水位命令：readSeq 只单调
// 前进，旧水位重放为 no-op；state、命令回执、MessageReceiptFact 与
// WatermarkAdvanced 事件在同一事务提交。
func (s *MessageService) MarkAsRead(ctx context.Context, req MarkAsReadRequest) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "chat.MarkAsRead",
		attribute.String("conversation.id", req.ConversationId),
		attribute.String("message.id", req.MessageId))
	defer func() {
		recordChatReadWatermarkCommand(err)
		rtobs.EndSpan(span, err)
	}()
	if err := s.requireConversationMembership(ctx, req.ConversationId, req.UserId); err != nil {
		return err
	}

	scopedKey, err := scopedChatIdempotencyKey(ctx, req.UserId)
	if err != nil {
		return err
	}
	digest, err := chatCommandDigest("MarkAsRead", req)
	if err != nil {
		return err
	}
	if found, err := replayChatCommand(
		ctx, s.userStateCommands, scopedKey, "MarkAsRead", digest, nil,
	); err != nil || found {
		return err
	}

	msg, err := s.messages.FindMessageByID(ctx, req.MessageId)
	if err != nil {
		if errors.Is(err, messagemodel.ErrMessageNotFound) {
			return generated.AppErrorFromMessageNotFound("read target message not found")
		}
		return err
	}
	if msg.ConversationID != req.ConversationId {
		return generated.AppErrorFromMessageNotFound("read target does not belong to conversation")
	}

	conv, err := s.conversations.FindConversationByID(ctx, req.ConversationId)
	if err != nil {
		return err
	}
	return s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		state, stateErr := s.userStates.FindUserState(
			txCtx,
			req.UserId,
			req.ConversationId,
		)
		if stateErr != nil {
			if !errors.Is(stateErr, conversationmodel.ErrUserStateNotFound) {
				return stateErr
			}
			state = &conversationmodel.ConversationUserState{
				ID:             generateID(),
				UserId:         req.UserId,
				ConversationId: req.ConversationId,
			}
		}
		commandReceipt, receiptErr := chatCommandReceipt(
			scopedKey,
			"MarkAsRead",
			digest,
			state.ID,
			nil,
		)
		if receiptErr != nil {
			return receiptErr
		}
		if msg.Seq <= state.ReadSeq {
			// no-op：旧水位重放，持久化回执且不回退 readSeq、不产生事件。
			return mapChatIdempotencyError(
				s.userStateCommands.CommitAggregateCommand(
					txCtx,
					commandReceipt,
					nil,
				),
			)
		}

		recomputedThroughSeq := state.InboxProjectedSeq
		if conv.MaxSeq > recomputedThroughSeq {
			recomputedThroughSeq = conv.MaxSeq
		}
		if msg.Seq > recomputedThroughSeq {
			recomputedThroughSeq = msg.Seq
		}
		counts, countErr := s.messages.CountUnreadMessages(
			txCtx,
			req.ConversationId,
			req.UserId,
			msg.Seq,
			recomputedThroughSeq,
		)
		if countErr != nil {
			return countErr
		}
		now := time.Now().UTC()
		state.ReadSeq = msg.Seq
		state.UnreadCount = counts.Total
		state.MentionUnreadCount = counts.Mentioned
		state.InboxProjectedSeq = recomputedThroughSeq
		state.LastReadAt = now
		state.UpdatedAt = now
		if err := s.userStates.UpsertUserState(txCtx, state); err != nil {
			return err
		}
		if conv.ReceiptEnabled {
			// MessageReceiptFact：dedupe key (messageId,userId) 由唯一索引保证。
			_, _, receiptErr := s.receiptFacts.Append(
				txCtx,
				receiptmodel.Fact{
					ID:             generateID(),
					MessageID:      req.MessageId,
					ConversationID: req.ConversationId,
					UserID:         req.UserId,
					ReadAt:         now,
				},
			)
			if receiptErr != nil {
				return receiptErr
			}
		}
		return mapChatIdempotencyError(s.userStateCommands.CommitAggregateCommand(
			txCtx,
			commandReceipt,
			[]AggregateOutboxEvent{{
				EventID:        chatAggregateEventID(scopedKey, string(userstateevent.ConversationReadWatermarkAdvanced)),
				EventType:      string(userstateevent.ConversationReadWatermarkAdvanced),
				AggregateID:    state.ID,
				ConversationID: req.ConversationId,
				ActorID:        req.UserId,
				Payload: map[string]any{
					"conversationId":     req.ConversationId,
					"userId":             state.UserId,
					"messageId":          req.MessageId,
					"readSeq":            state.ReadSeq,
					"unreadCount":        state.UnreadCount,
					"mentionUnreadCount": state.MentionUnreadCount,
					"readAt":             state.LastReadAt,
					"updatedAt":          state.UpdatedAt,
				},
			}},
		))
	})
}

func (s *MessageService) GetReceipts(ctx context.Context, conversationId, messageId, viewerID string) (_ []receiptmodel.Fact, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "chat.GetReceipts",
		attribute.String("conversation.id", conversationId),
		attribute.String("message.id", messageId))
	defer func() { rtobs.EndSpan(span, err) }()
	if err := s.requireConversationMembership(ctx, conversationId, viewerID); err != nil {
		return nil, err
	}
	message, err := s.messages.FindMessageByID(ctx, messageId)
	if err != nil {
		if errors.Is(err, messagemodel.ErrMessageNotFound) {
			return nil, generated.AppErrorFromMessageNotFound("receipt target message not found")
		}
		return nil, err
	}
	if message.ConversationID != conversationId {
		return nil, generated.AppErrorFromMessageNotFound("receipt target does not belong to conversation")
	}

	return s.receiptFacts.ListByMessage(ctx, messageId)
}
