package application

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	messageevent "quwoquan_service/services/chat-service/internal/domain/chat/message/event"
)

const inboxProjectionMessageConsumer = "chat-inbox-projection-message"

// InboxProjector 是 ChatInbox 未读/排序投影的唯一写入方：消费 Message
// outbox 的 MessageSent 推进接收方未读与排序时间；已读水位与设置由
// ConversationUserState 命令在聚合 state 内原子完成，无需二次投影。
// 每个 outbox 消费独立 checkpoint，崩溃后从水位重放（$max/$inc 与事件 ID
// 幂等保证重放安全）。
type InboxProjector struct {
	messageOutbox MessageOutboxReader
	checkpoints   ProjectionCheckpointStore
	members       MemberStore
	userStates    UserStateStore

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewInboxProjector(
	messageOutbox MessageOutboxReader,
	checkpoints ProjectionCheckpointStore,
	members MemberStore,
	userStates UserStateStore,
) *InboxProjector {
	return &InboxProjector{
		messageOutbox: messageOutbox,
		checkpoints:   checkpoints,
		members:       members,
		userStates:    userStates,
	}
}

func (p *InboxProjector) Drain(ctx context.Context, limit int) (processed int, err error) {
	defer func() {
		result := "succeeded"
		if err != nil {
			result = "failed"
		}
		chatInboxProjectionDrainTotal.WithLabelValues(result).Inc()
	}()
	if p == nil || p.messageOutbox == nil || p.checkpoints == nil ||
		p.members == nil || p.userStates == nil {
		return 0, errors.New("inbox projector is not fully configured")
	}
	checkpoint, err := p.checkpoints.LoadProjectionCheckpoint(ctx, inboxProjectionMessageConsumer)
	if err != nil {
		return 0, fmt.Errorf("load inbox projection checkpoint: %w", err)
	}
	events, err := p.messageOutbox.ReadMessageOutboxAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read message outbox for inbox projection: %w", err)
	}
	for index, event := range events {
		if strings.TrimSpace(event.Checkpoint) == "" {
			return index, fmt.Errorf("message outbox event %s has no checkpoint", event.EventID)
		}
		if event.EventType == string(messageevent.MessageSent) {
			if occurredAt, ok := event.Payload["timestamp"].(time.Time); ok {
				observeChatInboxProjectionEventLag(occurredAt.UTC())
			}
			if err := p.applyMessageSent(ctx, event); err != nil {
				return index, err
			}
		}
		if err := p.checkpoints.SaveProjectionCheckpoint(
			ctx, inboxProjectionMessageConsumer, event.Checkpoint,
		); err != nil {
			return index, fmt.Errorf("save inbox projection checkpoint: %w", err)
		}
	}
	return len(events), nil
}

func (p *InboxProjector) applyMessageSent(ctx context.Context, event MessageOutboxEvent) error {
	conversationID := strings.TrimSpace(event.ConversationID)
	senderID := strings.TrimSpace(event.ActorID)
	if senderID == "" {
		if raw, ok := event.Payload["senderId"].(string); ok {
			senderID = strings.TrimSpace(raw)
		}
	}
	occurredAt := time.Now().UTC()
	if raw, ok := event.Payload["timestamp"].(time.Time); ok {
		occurredAt = raw.UTC()
	}
	eventSeq := int64Payload(event.Payload["seq"])
	if eventSeq <= 0 {
		return fmt.Errorf("MessageSent event %s has invalid seq", event.EventID)
	}
	mentioned := map[string]struct{}{}
	mentionAll := false
	addMention := func(id string) {
		target := strings.TrimSpace(id)
		if target == "" {
			return
		}
		if target == "__all__" {
			mentionAll = true
			return
		}
		mentioned[target] = struct{}{}
	}
	if raw, ok := event.Payload["mentions"].([]any); ok {
		for _, item := range raw {
			if id, ok := item.(string); ok {
				addMention(id)
			}
		}
	}
	if raw, ok := event.Payload["mentions"].([]string); ok {
		for _, id := range raw {
			addMention(id)
		}
	}
	members, err := p.members.ListMembers(ctx, conversationID, ListMembersQuery{Limit: 1000})
	if err != nil {
		return fmt.Errorf("list members for inbox projection %s: %w", conversationID, err)
	}
	for _, member := range members {
		if member.MemberType != "user" {
			continue
		}
		unreadDelta := 1
		if member.UserId == senderID {
			unreadDelta = 0
		}
		mentionDelta := 0
		_, directlyMentioned := mentioned[member.UserId]
		if (mentionAll || directlyMentioned) && member.UserId != senderID {
			mentionDelta = 1
		}
		if err := p.userStates.AdvanceInboxUnread(
			ctx,
			member.UserId,
			conversationID,
			eventSeq,
			unreadDelta,
			mentionDelta,
			occurredAt,
		); err != nil {
			return fmt.Errorf(
				"advance inbox unread user=%s conversation=%s: %w",
				member.UserId, conversationID, err,
			)
		}
	}
	return nil
}

func int64Payload(value any) int64 {
	switch typed := value.(type) {
	case int:
		return int64(typed)
	case int32:
		return int64(typed)
	case int64:
		return typed
	case float64:
		return int64(typed)
	default:
		return 0
	}
}

func (p *InboxProjector) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = 200 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := p.Drain(ctx, 100); err != nil {
			p.recordFailure(err)
		} else {
			p.recordSuccess()
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func (p *InboxProjector) Healthy(maxStaleness time.Duration) error {
	if p == nil {
		return errors.New("inbox projector is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	p.mu.RLock()
	defer p.mu.RUnlock()
	if p.lastSuccess.IsZero() {
		return errors.New("inbox projector has not completed a scan")
	}
	if p.lastFailure != nil {
		return fmt.Errorf("inbox projector last failure: %w", p.lastFailure)
	}
	if time.Since(p.lastSuccess) > maxStaleness {
		return errors.New("inbox projector heartbeat is stale")
	}
	return nil
}

func (p *InboxProjector) recordSuccess() {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.lastSuccess = time.Now().UTC()
	p.lastFailure = nil
}

func (p *InboxProjector) recordFailure(err error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.lastFailure = err
}
