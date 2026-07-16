package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	userstateevent "quwoquan_service/services/chat-service/internal/domain/chat/conversation_user_state/event"
	messageevent "quwoquan_service/services/chat-service/internal/domain/chat/message/event"
	messagemodel "quwoquan_service/services/chat-service/internal/domain/chat/message/model"
	messageports "quwoquan_service/services/chat-service/internal/domain/chat/message/ports"
	conversationmodel "quwoquan_service/services/chat-service/internal/domain/conversation/model"
	"quwoquan_service/services/chat-service/internal/generated"
)

const recallTimeLimit = 2 * time.Minute

const (
	messageContentRuneLimit      = 5000
	messageCardTitleRuneLimit    = 120
	messageCardAttributeLimit    = 16
	messageCardAttributeKeyLimit = 64
	messageCardAttributeValLimit = 256
)

type MessageService struct {
	conversations ConversationStore
	messages      MessageStore
	members       MemberStore
	userStates    UserStateStore
	receipts      ReceiptStore
	projection    ConversationMessageProjector
	cache         ConversationCache
	publisher     EventPublisher
	relationships RelationshipGate
	mediaAssets   messageports.MediaAssetDeliveryReader
}

func NewMessageService(
	storage ChatStoragePorts,
	cache ConversationCache,
	publisher EventPublisher,
	relationships RelationshipGate,
	mediaAssets messageports.MediaAssetDeliveryReader,
) *MessageService {
	publisher = requireEventPublisher(publisher)
	if storage.Messages == nil || storage.MessageProjection == nil {
		panic("chat message application requires MessageStore and ConversationMessageProjector")
	}
	if relationships == nil {
		relationships = DenyRelationshipGate()
	}
	if mediaAssets == nil {
		panic("chat message application requires MediaAssetDeliveryReader")
	}
	return &MessageService{
		conversations: storage.Conversations,
		messages:      storage.Messages,
		members:       storage.Members,
		userStates:    storage.UserStates,
		receipts:      storage.Receipts,
		projection:    storage.MessageProjection,
		cache:         cache,
		publisher:     publisher,
		relationships: relationships,
		mediaAssets:   mediaAssets,
	}
}

type SendMessageRequest struct {
	ConversationId            string
	SenderId                  string
	PersonaContextVersion     int64
	SenderDisplayNameSnapshot string
	SenderAvatarUrlSnapshot   string
	Type                      string
	Content                   string
	MediaAssetID              string
	Card                      *MessageCardCommand
	ReplyToMessageId          string
	Mentions                  []string
	ClientMsgId               string
}

type MessageCardCommand struct {
	Kind         string                        `json:"kind"`
	Title        string                        `json:"title"`
	Subtitle     string                        `json:"subtitle"`
	ThumbnailURL string                        `json:"thumbnailUrl"`
	DeepLink     string                        `json:"deeplink"`
	LandingURL   string                        `json:"landingUrl"`
	ShareText    string                        `json:"shareText"`
	Message      string                        `json:"message"`
	Attributes   []MessageCardAttributeCommand `json:"attributes"`
}

type MessageCardAttributeCommand struct {
	Name  string `json:"name"`
	Value string `json:"value"`
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

	if err := s.ensureMessageAllowed(ctx, req); err != nil {
		return nil, err
	}
	card, err := validateMessageCommand(req)
	if err != nil {
		return nil, err
	}
	if _, err := s.resolveCommandMedia(ctx, req); err != nil {
		return nil, err
	}
	commandDigest, err := sendMessageCommandDigest(req)
	if err != nil {
		return nil, err
	}

	now := time.Now().UTC()
	msg := messagemodel.Message{
		ID:                        generateID(),
		ConversationID:            req.ConversationId,
		ClientMessageID:           req.ClientMsgId,
		SenderID:                  req.SenderId,
		SenderDisplayNameSnapshot: req.SenderDisplayNameSnapshot,
		SenderAvatarURLSnapshot:   req.SenderAvatarUrlSnapshot,
		PersonaContextVersion:     req.PersonaContextVersion,
		Type:                      req.Type,
		Content:                   req.Content,
		MediaAssetID:              strings.TrimSpace(req.MediaAssetID),
		Card:                      card,
		ReplyToMessageID:          req.ReplyToMessageId,
		Mentions:                  req.Mentions,
		Status:                    "sent",
		Timestamp:                 now,
		Version:                   1,
	}

	events := []MessageOutboxEvent{{
		EventID:        msg.ID + ":v1:" + messageevent.MessageSent,
		EventType:      messageevent.MessageSent,
		ConversationID: req.ConversationId,
		ActorID:        req.SenderId,
		Payload: map[string]any{
			"conversationId":            req.ConversationId,
			"type":                      msg.Type,
			"content":                   msg.Content,
			"mediaAssetId":              msg.MediaAssetID,
			"card":                      msg.Card,
			"replyToMessageId":          msg.ReplyToMessageID,
			"mentions":                  msg.Mentions,
			"clientMsgId":               req.ClientMsgId,
			"senderId":                  req.SenderId,
			"personaContextVersion":     req.PersonaContextVersion,
			"senderDisplayNameSnapshot": req.SenderDisplayNameSnapshot,
			"senderAvatarUrlSnapshot":   req.SenderAvatarUrlSnapshot,
		},
	}}
	if !isAssistantGeneratedMessage(req) {
		if assistantMember, ok := s.mentionedAssistantMember(ctx, req.ConversationId, msg.Mentions); ok {
			events = append(events, MessageOutboxEvent{
				EventID:        msg.ID + ":v1:" + messageevent.AssistantMentioned,
				EventType:      messageevent.AssistantMentioned,
				ConversationID: req.ConversationId,
				ActorID:        req.SenderId,
				Payload: map[string]any{
					"conversationId":     req.ConversationId,
					"senderId":           req.SenderId,
					"content":            msg.Content,
					"assistantMemberId":  assistantMember.UserId,
					"assistantSkillId":   assistantMember.AssistantSkillId,
					"triggerClientMsgId": req.ClientMsgId,
				},
			})
		}
	}

	committed, err := s.messages.CommitMessage(ctx, MessageCommit{
		Message:       msg,
		CommandDigest: commandDigest,
		Events:        events,
	})
	if err != nil {
		if errors.Is(err, messagemodel.ErrMessageIdempotencyConflict) {
			return nil, generated.AppErrorFromMessageIdempotencyConflict("clientMsgId was already used for a different SendMessage command")
		}
		return nil, err
	}

	if err := s.projection.ProjectCommittedMessage(ctx, committed.Message); err != nil {
		return nil, err
	}
	if err := s.cache.InvalidateConversation(ctx, req.ConversationId); err != nil {
		return nil, err
	}

	return &SendMessageResponse{
		MessageId: committed.Message.ID,
		Seq:       committed.Message.Seq,
		Timestamp: committed.Message.Timestamp.Format(time.RFC3339Nano),
	}, nil
}

func validateMessageCommand(req SendMessageRequest) (*messagemodel.MessageCard, error) {
	messageType := strings.TrimSpace(req.Type)
	if _, ok := map[string]struct{}{
		"text": {}, "audio": {}, "image": {}, "video": {}, "file": {}, "card": {},
	}[messageType]; !ok {
		return nil, generated.AppErrorFromMessageInvalid("unsupported message type")
	}
	if strings.TrimSpace(req.ClientMsgId) == "" {
		return nil, generated.AppErrorFromMessageInvalid("clientMsgId is required")
	}
	if len([]rune(req.Content)) > messageContentRuneLimit {
		return nil, generated.AppErrorFromMessageTooLong("content exceeds 5000 Unicode code points")
	}
	if messageType == "text" && strings.TrimSpace(req.Content) == "" {
		return nil, generated.AppErrorFromMessageInvalid("text message content is required")
	}
	if messageType != "card" {
		if req.Card != nil {
			return nil, generated.AppErrorFromMessageInvalid("non-card message must not contain card")
		}
		return nil, nil
	}
	if req.Card == nil {
		return nil, generated.AppErrorFromMessageInvalid("card message requires card")
	}
	kind := strings.TrimSpace(req.Card.Kind)
	title := strings.TrimSpace(req.Card.Title)
	if kind == "" || title == "" {
		return nil, generated.AppErrorFromMessageInvalid("card kind and title are required")
	}
	if len([]rune(title)) > messageCardTitleRuneLimit {
		return nil, generated.AppErrorFromMessageInvalid("card title exceeds 120 Unicode code points")
	}
	if len(req.Card.Attributes) > messageCardAttributeLimit {
		return nil, generated.AppErrorFromMessageInvalid("card has more than 16 attributes")
	}
	attributes := make([]messagemodel.MessageCardAttribute, 0, len(req.Card.Attributes))
	seen := make(map[string]struct{}, len(req.Card.Attributes))
	for _, attribute := range req.Card.Attributes {
		name, value := strings.TrimSpace(attribute.Name), strings.TrimSpace(attribute.Value)
		if name == "" || value == "" {
			return nil, generated.AppErrorFromMessageInvalid("card attribute name and value are required")
		}
		if len([]rune(name)) > messageCardAttributeKeyLimit || len([]rune(value)) > messageCardAttributeValLimit {
			return nil, generated.AppErrorFromMessageInvalid("card attribute exceeds size limit")
		}
		if _, duplicated := seen[name]; duplicated {
			return nil, generated.AppErrorFromMessageInvalid("card attribute names must be unique")
		}
		seen[name] = struct{}{}
		attributes = append(attributes, messagemodel.MessageCardAttribute{Name: name, Value: value})
	}
	return &messagemodel.MessageCard{
		Kind:         kind,
		Title:        title,
		Subtitle:     strings.TrimSpace(req.Card.Subtitle),
		ThumbnailURL: strings.TrimSpace(req.Card.ThumbnailURL),
		DeepLink:     strings.TrimSpace(req.Card.DeepLink),
		LandingURL:   strings.TrimSpace(req.Card.LandingURL),
		ShareText:    strings.TrimSpace(req.Card.ShareText),
		Message:      strings.TrimSpace(req.Card.Message),
		Attributes:   attributes,
	}, nil
}

func sendMessageCommandDigest(req SendMessageRequest) (string, error) {
	payload, err := json.Marshal(req)
	if err != nil {
		return "", fmt.Errorf("encode SendMessage command digest: %w", err)
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), nil
}

func (s *MessageService) mentionedAssistantMember(ctx context.Context, conversationID string, mentions []string) (*conversationmodel.ConversationMember, bool) {
	if len(mentions) == 0 {
		return nil, false
	}
	assistantMember, err := s.members.FindAssistantMember(ctx, conversationID)
	if err != nil || assistantMember == nil {
		return nil, false
	}
	for _, mention := range mentions {
		if mention == assistantMember.UserId || mention == "assistant" {
			return assistantMember, true
		}
	}
	return nil, false
}

func isAssistantGeneratedMessage(req SendMessageRequest) bool {
	return req.SenderId == "assistant" || strings.HasPrefix(strings.TrimSpace(req.ClientMsgId), "assistant-")
}

func (s *MessageService) ensureMessageAllowed(ctx context.Context, req SendMessageRequest) error {
	if err := s.requireConversationMembership(ctx, req.ConversationId, req.SenderId); err != nil {
		return err
	}
	conv, err := s.conversations.FindConversationByID(ctx, req.ConversationId)
	if err != nil {
		return err
	}
	if conv.Status != "" && conv.Status != "active" {
		return chatBlocked("conversation is not active")
	}
	if conv.Type != conversationTypeDirect && conv.Type != conversationTypeEncrypted {
		return nil
	}
	members, err := s.members.ListMembers(ctx, req.ConversationId, ListMembersQuery{
		Limit: 10,
		Sort:  MemberListSortJoinedAsc,
	})
	if err != nil {
		return err
	}
	peerID := ""
	for _, member := range members {
		if member.UserId != req.SenderId && member.MemberType == "user" {
			peerID = member.UserId
			break
		}
	}
	if peerID == "" {
		return chatBlocked("direct conversation peer missing")
	}
	capability, err := s.relationships.GetCapability(ctx, req.SenderId, peerID)
	if err != nil {
		return err
	}
	if capability.IsBlocked || capability.IsBlockedBy {
		return chatBlocked("send message blocked by relationship gate")
	}
	if !capability.CanSendMessage {
		return chatNotMutual("send message requires mutual follow")
	}
	return nil
}

func (s *MessageService) requireConversationMembership(ctx context.Context, conversationID, personaID string) error {
	conversationID, personaID = strings.TrimSpace(conversationID), strings.TrimSpace(personaID)
	if conversationID == "" || personaID == "" {
		return generated.AppErrorFromUnauthorized("conversation and trusted persona are required")
	}
	if _, err := s.members.FindMember(ctx, conversationID, personaID); err != nil {
		if errors.Is(err, conversationmodel.ErrMemberNotFound) {
			return generated.AppErrorFromBlocked("persona is not an active conversation member")
		}
		return err
	}
	return nil
}

func (s *MessageService) resolveCommandMedia(
	ctx context.Context,
	req SendMessageRequest,
) (messageports.MediaAssetDeliverySlice, error) {
	assetID := strings.TrimSpace(req.MediaAssetID)
	expectedType, mediaMessage := expectedMessageMediaType(req.Type)
	if !mediaMessage {
		if assetID != "" {
			return messageports.MediaAssetDeliverySlice{}, generated.AppErrorFromMessageMediaInvalid(
				"non-media message must not bind MediaAsset",
			)
		}
		return messageports.MediaAssetDeliverySlice{}, nil
	}
	if assetID == "" {
		return messageports.MediaAssetDeliverySlice{}, generated.AppErrorFromMessageMediaInvalid(
			"media message requires mediaAssetId",
		)
	}
	asset, found, err := s.mediaAssets.ReadOwnedReadyAsset(ctx, assetID, strings.TrimSpace(req.SenderId))
	if err != nil {
		return messageports.MediaAssetDeliverySlice{}, generated.AppErrorFromMessageMediaUnavailable(err.Error())
	}
	if !found || asset.AssetID != assetID || asset.OwnerPersonaID != strings.TrimSpace(req.SenderId) ||
		asset.ProcessingStatus != "ready" || asset.MediaType != expectedType ||
		strings.TrimSpace(asset.ContentType) == "" || asset.FileSize <= 0 || strings.TrimSpace(asset.DeliveryURL) == "" {
		return messageports.MediaAssetDeliverySlice{}, generated.AppErrorFromMessageMediaInvalid(
			"owner-scoped ready MediaAsset of the expected type is required",
		)
	}
	return asset, nil
}

func expectedMessageMediaType(messageType string) (string, bool) {
	switch strings.TrimSpace(messageType) {
	case "audio":
		return "audio", true
	case "image":
		return "image", true
	case "video":
		return "video", true
	case "file":
		return "file", true
	default:
		return "", false
	}
}

func (s *MessageService) RecallMessage(ctx context.Context, conversationId, messageId, senderId string) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "chat.RecallMessage",
		attribute.String("conversation.id", conversationId),
		attribute.String("message.id", messageId))
	defer func() { rtobs.EndSpan(span, err) }()
	if err := s.requireConversationMembership(ctx, conversationId, senderId); err != nil {
		return err
	}

	msg, err := s.messages.FindMessageByID(ctx, messageId)
	if err != nil {
		if errors.Is(err, messagemodel.ErrMessageNotFound) {
			return generated.AppErrorFromMessageNotFound("recall target message not found")
		}
		return err
	}
	if msg.ConversationID != conversationId {
		return generated.AppErrorFromMessageNotFound("recall target does not belong to conversation")
	}

	if msg.SenderID != senderId {
		return generated.AppErrorFromMessageRecallForbidden("recall actor does not own message")
	}

	if time.Since(msg.Timestamp) > recallTimeLimit {
		return generated.AppErrorFromMessageRecallExpired("recall window exceeded")
	}

	if err := s.messages.SetMessageRecalled(ctx, messageId); err != nil {
		return err
	}

	_ = s.cache.InvalidateConversation(ctx, conversationId)

	go func() {
		if err := s.publisher.PublishDomainEvent(context.Background(), messageevent.MessageRecalled, conversationId, senderId, map[string]any{
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
	ViewerID       string
	Limit          int
	AfterSeq       int64
	BeforeSeq      int64
	Cursor         string
}

type MessageSlice struct {
	Message messagemodel.Message
	Media   *messageports.MediaAssetDeliverySlice
}

func (s *MessageService) ListMessages(ctx context.Context, req ListMessagesRequest) (_ []MessageSlice, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "chat.ListMessages",
		attribute.String("conversation.id", req.ConversationId),
		attribute.Int("list.limit", req.Limit))
	defer func() { rtobs.EndSpan(span, err) }()

	if err := s.requireConversationMembership(ctx, req.ConversationId, req.ViewerID); err != nil {
		return nil, err
	}
	messages, err := s.messages.ListMessages(ctx, req.ConversationId, req.Limit, req.AfterSeq, req.BeforeSeq)
	if err != nil {
		return nil, err
	}
	return s.hydrateMessageSlices(ctx, messages)
}

func (s *MessageService) hydrateMessageSlices(
	ctx context.Context,
	messages []messagemodel.Message,
) ([]MessageSlice, error) {
	slices := make([]MessageSlice, 0, len(messages))
	resolved := make(map[string]*messageports.MediaAssetDeliverySlice)
	for _, message := range messages {
		item := MessageSlice{Message: message}
		assetID := strings.TrimSpace(message.MediaAssetID)
		if assetID == "" {
			slices = append(slices, item)
			continue
		}
		cacheKey := message.SenderID + "\x00" + assetID
		if cached, ok := resolved[cacheKey]; ok {
			item.Media = cached
			slices = append(slices, item)
			continue
		}
		asset, found, err := s.mediaAssets.ReadOwnedReadyAsset(ctx, assetID, message.SenderID)
		if err != nil {
			return nil, generated.AppErrorFromMessageMediaUnavailable(err.Error())
		}
		if found && asset.AssetID == assetID && asset.OwnerPersonaID == message.SenderID &&
			asset.ProcessingStatus == "ready" && strings.TrimSpace(asset.DeliveryURL) != "" {
			copy := asset
			item.Media = &copy
			resolved[cacheKey] = &copy
		} else {
			resolved[cacheKey] = nil
		}
		slices = append(slices, item)
	}
	return slices, nil
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
	conversations, err := listUserConversations(ctx, s.conversations, s.userStates, req.UserId)
	if err != nil {
		return nil, err
	}
	results := make([]MessageSearchHit, 0, limit)
	for _, conversation := range conversations {
		messages, err := s.messages.ListMessages(ctx, conversation.ID, limit*4, 0, 0)
		if err != nil {
			continue
		}
		for _, message := range messages {
			matched, _ := containsQuery(
				[]string{
					message.Content,
					message.SenderID,
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
	ViewerID       string
	LastSeq        int64
	Limit          int
}

type SyncMessagesResponse struct {
	Messages []MessageSlice `json:"-"`
	HasMore  bool           `json:"hasMore"`
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

	if err := s.requireConversationMembership(ctx, req.ConversationId, req.ViewerID); err != nil {
		return nil, err
	}
	msgs, err := s.messages.ListMessages(ctx, req.ConversationId, limit+1, req.LastSeq, 0)
	if err != nil {
		return nil, err
	}

	hasMore := len(msgs) > limit
	if hasMore {
		msgs = msgs[:limit]
	}
	slices, err := s.hydrateMessageSlices(ctx, msgs)
	if err != nil {
		return nil, err
	}

	return &SyncMessagesResponse{
		Messages: slices,
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
	if err := s.requireConversationMembership(ctx, req.ConversationId, req.UserId); err != nil {
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

	state, err := s.userStates.FindUserState(ctx, req.UserId, req.ConversationId)
	if err != nil {
		now := time.Now()
		state = &conversationmodel.ConversationUserState{
			ID:             generateID(),
			UserId:         req.UserId,
			ConversationId: req.ConversationId,
			UpdatedAt:      now,
		}
	}

	readAdvanced := false
	if msg.Seq > state.ReadSeq {
		conv, _ := s.conversations.FindConversationByID(ctx, req.ConversationId)
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
		state.MentionUnreadCount = 0
		state.UpdatedAt = time.Now()
		if err := s.userStates.UpsertUserState(ctx, state); err != nil {
			return err
		}
		readAdvanced = true
	}

	if readAdvanced {
		stateSnapshot := *state
		go func() {
			if err := s.publisher.PublishDomainEvent(context.Background(), userstateevent.ConversationReadWatermarkAdvanced, req.ConversationId, req.UserId, map[string]any{
				"userId":             stateSnapshot.UserId,
				"messageId":          req.MessageId,
				"readSeq":            stateSnapshot.ReadSeq,
				"unreadCount":        stateSnapshot.UnreadCount,
				"mentionUnreadCount": stateSnapshot.MentionUnreadCount,
				"readAt":             stateSnapshot.LastReadAt,
				"updatedAt":          stateSnapshot.UpdatedAt,
			}); err != nil {
				slog.Error("publish ConversationReadWatermarkAdvanced failed", "err", err, "conversationId", req.ConversationId)
			}
		}()
	}

	convForReceipt, _ := s.conversations.FindConversationByID(ctx, req.ConversationId)
	if convForReceipt != nil && convForReceipt.ReceiptEnabled {
		receipt := &messagemodel.MessageReceipt{
			ID:             generateID(),
			MessageID:      req.MessageId,
			ConversationID: req.ConversationId,
			UserID:         req.UserId,
			ReadAt:         time.Now(),
		}
		_ = s.receipts.CreateReceipt(ctx, receipt)
	}

	return nil
}

func (s *MessageService) GetReceipts(ctx context.Context, conversationId, messageId, viewerID string) (_ []messagemodel.MessageReceipt, err error) {
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

	return s.receipts.ListReceiptsByMessage(ctx, messageId)
}
