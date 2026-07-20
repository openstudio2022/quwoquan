package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	messageevent "quwoquan_service/services/chat-service/internal/domain/chat/message/event"
	messagemodel "quwoquan_service/services/chat-service/internal/domain/chat/message/model"
)

// RtcCallEndedFact 是 rtc CallEnded 公共事件的 typed application 输入。
type RtcCallEndedFact struct {
	EventID        string
	CallID         string
	CallType       string
	InitiatorID    string
	ConversationID string
	EndReason      string
	DurationMs     int64
	StartedAt      time.Time
	EndedAt        time.Time
}

// AppendRtcCallLog 把关联聊天会话的 CallEnded 事实投影为不可编辑的
// system_call_log Message。相同 EventID 只生成一个 Message/outbox。
func (s *MessageService) AppendRtcCallLog(
	ctx context.Context,
	fact RtcCallEndedFact,
) error {
	eventID := strings.TrimSpace(fact.EventID)
	conversationID := strings.TrimSpace(fact.ConversationID)
	if eventID == "" {
		return errors.New("rtc call log event id is required")
	}
	// 没有关联聊天会话的独立通话不产生 chat Message。
	if conversationID == "" {
		return nil
	}
	now := fact.EndedAt.UTC()
	if now.IsZero() {
		now = time.Now().UTC()
	}
	messageID := stableRtcCallLogMessageID(eventID)
	msg := messagemodel.Message{
		ID:              messageID,
		ConversationID:  conversationID,
		ClientMessageID: "rtc:" + eventID,
		SenderID:        strings.TrimSpace(fact.InitiatorID),
		Type:            "system_call_log",
		Content:         "",
		Card: &messagemodel.MessageCard{
			Kind: "rtc_call_log",
			Attributes: []messagemodel.MessageCardAttribute{
				{Name: "callId", Value: strings.TrimSpace(fact.CallID)},
				{Name: "callType", Value: strings.TrimSpace(fact.CallType)},
				{Name: "endReason", Value: strings.TrimSpace(fact.EndReason)},
				{Name: "durationMs", Value: strconv.FormatInt(fact.DurationMs, 10)},
			},
		},
		Status:    "sent",
		Timestamp: now,
		Version:   1,
	}
	digest := sha256.Sum256([]byte(
		eventID + "\x00" + conversationID + "\x00" +
			fact.CallID + "\x00" + fact.EndReason + "\x00" +
			strconv.FormatInt(fact.DurationMs, 10),
	))
	committed, err := s.messages.CommitMessage(ctx, MessageCommit{
		Message:       msg,
		CommandDigest: hex.EncodeToString(digest[:]),
		Events: []MessageOutboxEvent{{
			EventID:        messageID + ":v1:" + messageevent.MessageSent,
			EventType:      messageevent.MessageSent,
			ConversationID: conversationID,
			ActorID:        fact.InitiatorID,
			Payload: map[string]any{
				"conversationId": conversationID,
				"type":           msg.Type,
				"content":        msg.Content,
				"card":           msg.Card,
				"clientMsgId":    msg.ClientMessageID,
				"senderId":       msg.SenderID,
			},
		}},
	})
	if err != nil {
		if errors.Is(err, messagemodel.ErrMessageIdempotencyConflict) {
			return fmt.Errorf("rtc call log idempotency conflict: %w", err)
		}
		return err
	}
	if err := s.projection.ProjectCommittedMessage(ctx, committed.Message); err != nil {
		return err
	}
	return s.cache.InvalidateConversation(ctx, conversationID)
}

func stableRtcCallLogMessageID(eventID string) string {
	sum := sha256.Sum256([]byte("rtc-call-log\x00" + eventID))
	return "rtc-call-log-" + hex.EncodeToString(sum[:16])
}
