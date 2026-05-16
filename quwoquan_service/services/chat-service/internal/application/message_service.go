package application

import (
	"context"
	"errors"
	"log/slog"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	event "quwoquan_service/services/chat-service/internal/domain/conversation/event"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
	"quwoquan_service/services/chat-service/internal/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

const recallTimeLimit = 2 * time.Minute

type MessageService struct {
	repo      persistence.ChatRepository
	cache     *cache.ConversationCache
	publisher EventPublisher
}

func NewMessageService(repo persistence.ChatRepository, cache *cache.ConversationCache, publisher EventPublisher) *MessageService {
	if publisher == nil {
		publisher = NoopEventPublisher()
	}
	return &MessageService{repo: repo, cache: cache, publisher: publisher}
}

type SendMessageRequest struct {
	ConversationId            string
	SenderId                  string
	PersonaContextVersion     int64
	SenderDisplayNameSnapshot string
	SenderAvatarUrlSnapshot   string
	Type                      string
	Content                   string
	MediaUrl                  string
	Media                     map[string]any
	CardPayload               map[string]any
	ReplyToMessageId          string
	Mentions                  []string
	ClientMsgId               string
}

type SendMessageResponse struct {
	MessageId string `json:"messageId"`
	Seq       int64  `json:"seq"`
	Timestamp string `json:"timestamp"`
}

func (s *MessageService) SendMessage(ctx context.Context, req SendMessageRequest) (resp *SendMessageResponse, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "chat.SendMessage",
		attribute.String("conversation.id", req.ConversationId),
		attribute.String("message.type", req.Type))
	defer func() { rtobs.EndSpan(span, err) }()

	isNew, err := s.cache.TryDedup(ctx, req.ConversationId, req.ClientMsgId)
	if err != nil {
		return nil, err
	}
	if !isNew {
		existing, err := s.repo.FindMessageByClientMsgId(ctx, req.ConversationId, req.ClientMsgId)
		if err != nil {
			return nil, err
		}
		return &SendMessageResponse{
			MessageId: existing.ID,
			Seq:       existing.Seq,
			Timestamp: existing.Timestamp.Format(time.RFC3339Nano),
		}, nil
	}

	seq, err := s.cache.NextSeq(ctx, req.ConversationId)
	if err != nil {
		return nil, err
	}

	now := time.Now()
	msg := &model.Message{
		ID:               generateID(),
		ConversationId:   req.ConversationId,
		Seq:              seq,
		ClientMsgId:      req.ClientMsgId,
		SenderId:         req.SenderId,
		Type:             req.Type,
		Content:          req.Content,
		MediaUrl:         req.MediaUrl,
		Media:            req.Media,
		CardPayload:      req.CardPayload,
		ReplyToMessageId: req.ReplyToMessageId,
		Mentions:         req.Mentions,
		Status:           "sent",
		Metadata: map[string]any{
			"senderDisplayNameSnapshot": req.SenderDisplayNameSnapshot,
			"senderAvatarUrlSnapshot":   req.SenderAvatarUrlSnapshot,
			"personaContextVersion":     req.PersonaContextVersion,
		},
		Timestamp: now,
	}

	if err := s.repo.CreateMessage(ctx, msg); err != nil {
		return nil, err
	}

	conv, err := s.repo.FindConversationByID(ctx, req.ConversationId)
	if err == nil {
		preview := messagePreview(req.Type, req.Content)
		conv.MaxSeq = seq
		conv.LastMessageId = msg.ID
		conv.LastMessagePreview = preview
		conv.LastMessageTime = now
		conv.MessageCount++
		_ = s.repo.UpdateConversation(ctx, conv.ID, conv)
	}

	_ = s.cache.InvalidateConversation(ctx, req.ConversationId)

	go func() {
		if err := s.publisher.PublishDomainEvent(context.Background(), event.MessageSent, req.ConversationId, req.SenderId, map[string]any{
			"messageId":             msg.ID,
			"seq":                   seq,
			"type":                  msg.Type,
			"content":               msg.Content,
			"mediaUrl":              msg.MediaUrl,
			"media":                 msg.Media,
			"mentions":              msg.Mentions,
			"clientMsgId":           req.ClientMsgId,
			"timestamp":             msg.Timestamp,
			"senderSubAccountId":    req.SenderId,
			"personaContextVersion": req.PersonaContextVersion,
		}); err != nil {
			slog.Error("publish MessageSent failed", "err", err, "conversationId", req.ConversationId)
		}
	}()

	return &SendMessageResponse{
		MessageId: msg.ID,
		Seq:       seq,
		Timestamp: now.Format(time.RFC3339Nano),
	}, nil
}

func (s *MessageService) RecallMessage(ctx context.Context, conversationId, messageId, senderId string) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "chat.RecallMessage",
		attribute.String("conversation.id", conversationId),
		attribute.String("message.id", messageId))
	defer func() { rtobs.EndSpan(span, err) }()

	msg, err := s.repo.FindMessageByID(ctx, messageId)
	if err != nil {
		return errors.New("message not found")
	}

	if msg.SenderId != senderId {
		return errors.New("unauthorized: only sender can recall")
	}

	if time.Since(msg.Timestamp) > recallTimeLimit {
		return errors.New("recall time exceeded")
	}

	if err := s.repo.SetMessageRecalled(ctx, messageId); err != nil {
		return err
	}

	_ = s.cache.InvalidateConversation(ctx, conversationId)

	go func() {
		if err := s.publisher.PublishDomainEvent(context.Background(), event.MessageRecalled, conversationId, senderId, map[string]any{
			"messageId":  messageId,
			"seq":        msg.Seq,
			"recalledAt": time.Now(),
		}); err != nil {
			slog.Error("publish MessageRecalled failed", "err", err, "conversationId", conversationId)
		}
	}()

	return nil
}

type ListMessagesRequest struct {
	ConversationId string
	Limit          int
	AfterSeq       int64
	BeforeSeq      int64
	Cursor         string
}

func (s *MessageService) ListMessages(ctx context.Context, req ListMessagesRequest) (_ []model.Message, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "chat.ListMessages",
		attribute.String("conversation.id", req.ConversationId),
		attribute.Int("list.limit", req.Limit))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.repo.ListMessages(ctx, req.ConversationId, req.Limit, req.AfterSeq, req.BeforeSeq)
}

type SearchMessagesRequest struct {
	UserId string
	Query  string
	Cursor string
	Limit  int
}

func (s *MessageService) SearchMessages(
	ctx context.Context,
	req SearchMessagesRequest,
) (_ []MessageSearchHit, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "chat.SearchMessages",
		attribute.String("user.id", req.UserId),
		attribute.String("search.query", req.Query))
	defer func() { rtobs.EndSpan(span, err) }()

	query := normalizeSearchQuery(req.Query)
	if query == "" {
		return []MessageSearchHit{}, nil
	}
	limit := clampSearchLimit(req.Limit, 20)
	conversations, err := listUserConversations(ctx, s.repo, req.UserId)
	if err != nil {
		return nil, err
	}
	results := make([]MessageSearchHit, 0, limit)
	for _, conversation := range conversations {
		messages, err := s.repo.ListMessages(ctx, conversation.ID, limit*4, 0, 0)
		if err != nil {
			continue
		}
		for _, message := range messages {
			matched, _ := containsQuery(
				[]string{
					message.Content,
					message.SenderId,
				},
				query,
			)
			if !matched {
				continue
			}
			results = append(results, MessageSearchHit{
				Conversation: conversation,
				Message:      message,
			})
			if len(results) >= limit {
				return results, nil
			}
		}
	}
	return results, nil
}

type SyncMessagesRequest struct {
	ConversationId string
	LastSeq        int64
	Limit          int
}

type SyncMessagesResponse struct {
	Messages []model.Message `json:"messages"`
	HasMore  bool            `json:"hasMore"`
}

func (s *MessageService) SyncMessages(ctx context.Context, req SyncMessagesRequest) (_ *SyncMessagesResponse, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "chat.SyncMessages",
		attribute.String("conversation.id", req.ConversationId),
		attribute.Int64("sync.last_seq", req.LastSeq))
	defer func() { rtobs.EndSpan(span, err) }()

	limit := req.Limit
	if limit <= 0 || limit > 500 {
		limit = 500
	}

	msgs, err := s.repo.ListMessages(ctx, req.ConversationId, limit+1, req.LastSeq, 0)
	if err != nil {
		return nil, err
	}

	hasMore := len(msgs) > limit
	if hasMore {
		msgs = msgs[:limit]
	}

	return &SyncMessagesResponse{
		Messages: msgs,
		HasMore:  hasMore,
	}, nil
}

type MarkAsReadRequest struct {
	ConversationId string
	MessageId      string
	UserId         string
}

func (s *MessageService) MarkAsRead(ctx context.Context, req MarkAsReadRequest) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "chat.MarkAsRead",
		attribute.String("conversation.id", req.ConversationId),
		attribute.String("message.id", req.MessageId))
	defer func() { rtobs.EndSpan(span, err) }()

	msg, err := s.repo.FindMessageByID(ctx, req.MessageId)
	if err != nil {
		return err
	}

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

	if msg.Seq > state.ReadSeq {
		conv, _ := s.repo.FindConversationByID(ctx, req.ConversationId)
		state.ReadSeq = msg.Seq
		state.LastReadAt = time.Now()
		if conv != nil {
			state.UnreadCount = int(conv.MaxSeq - msg.Seq)
		} else {
			state.UnreadCount = 0
		}
		if state.UnreadCount < 0 {
			state.UnreadCount = 0
		}
		state.UpdatedAt = time.Now()
		if err := s.repo.UpsertUserState(ctx, state); err != nil {
			return err
		}
	}

	convForReceipt, _ := s.repo.FindConversationByID(ctx, req.ConversationId)
	if convForReceipt != nil && convForReceipt.ReceiptEnabled {
		receipt := &model.MessageReceipt{
			ID:             generateID(),
			MessageId:      req.MessageId,
			ConversationId: req.ConversationId,
			UserId:         req.UserId,
			ReadAt:         time.Now(),
		}
		_ = s.repo.CreateReceipt(ctx, receipt)

		go func() {
			if err := s.publisher.PublishDomainEvent(context.Background(), event.ReadReceiptSent, req.ConversationId, req.UserId, map[string]any{
				"messageId": req.MessageId,
				"readAt":    receipt.ReadAt,
			}); err != nil {
				slog.Error("publish ReadReceiptSent failed", "err", err, "conversationId", req.ConversationId)
			}
		}()
	}

	return nil
}

func (s *MessageService) GetReceipts(ctx context.Context, conversationId, messageId string) (_ []model.MessageReceipt, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "chat.GetReceipts",
		attribute.String("conversation.id", conversationId),
		attribute.String("message.id", messageId))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.repo.ListReceiptsByMessage(ctx, messageId)
}

func messagePreview(msgType, content string) string {
	switch msgType {
	case "audio":
		return "[语音消息]"
	case "image":
		return "[图片]"
	case "video":
		return "[视频]"
	case "file":
		return "[文件]"
	default:
		if len(content) > 100 {
			return content[:100]
		}
		return content
	}
}
