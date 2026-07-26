package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/chat-service/generated/chat/conversation"
	userstateevent "quwoquan_service/services/chat-service/generated/chat/conversation_user_state/contract/event"
	messageevent "quwoquan_service/services/chat-service/generated/chat/message/contract/event"
	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	messagemodel "quwoquan_service/services/chat-service/internal/chat/message/domain/model"
	messageports "quwoquan_service/services/chat-service/internal/chat/message/domain/ports"
)

const recallTimeLimit = 2 * time.Minute

const (
	messageContentRuneLimit      = 5000
	messageCardTitleRuneLimit    = 120
	messageCardAttributeLimit    = 16
	messageCardAttributeKeyLimit = 64
	messageCardAttributeValLimit = 256
	messageMentionLimit          = 50
)

type MessageService struct {
	transactions      TransactionRunner
	conversations     ConversationStore
	messages          MessageStore
	members           MemberStore
	userStates        UserStateStore
	userStateCommands AggregateCommandStore
	receipts          ReceiptStore
	projection        ConversationMessageProjector
	cache             ConversationCache
	publisher         EventPublisher
	relationships     RelationshipGate
	mediaAssets       messageports.MediaAssetDeliveryReader
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
		transactions:      storage.Transactions,
		conversations:     storage.Conversations,
		messages:          storage.Messages,
		members:           storage.Members,
		userStates:        storage.UserStates,
		userStateCommands: storage.UserStateCommands,
		receipts:          storage.Receipts,
		projection:        storage.MessageProjection,
		cache:             cache,
		publisher:         publisher,
		relationships:     relationships,
		mediaAssets:       mediaAssets,
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

type AssistantDeliveryMessageRequest struct {
	ConversationID   string
	CreatorPersonaID string
	AssistantSkillID string
	Type             string
	Content          string
	ClientMsgID      string
}

func (s *MessageService) SendMessage(ctx context.Context, req SendMessageRequest) (resp *SendMessageResponse, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "chat.SendMessage",
		attribute.String("conversation.id", req.ConversationId),
		attribute.String("message.type", req.Type))
	defer func() {
		recordChatMentionCommand(req.Mentions, err)
		rtobs.EndSpan(span, err)
	}()

	if err := s.ensureMessageAllowed(ctx, req); err != nil {
		return nil, err
	}
	req.Mentions, err = s.canonicalMentions(ctx, req)
	if err != nil {
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

func (s *MessageService) ListAssistantGroundingMessages(
	ctx context.Context,
	conversationID string,
	creatorPersonaID string,
	assistantSkillID string,
	beforeSeq int64,
	limit int,
) ([]MessageSlice, error) {
	if err := s.requireAssistantDeliveryMembership(
		ctx,
		conversationID,
		creatorPersonaID,
		assistantSkillID,
	); err != nil {
		return nil, err
	}
	return s.ListMessages(ctx, ListMessagesRequest{
		ConversationId: conversationID,
		ViewerID:       "assistant",
		BeforeSeq:      beforeSeq,
		Limit:          limit,
	})
}

func (s *MessageService) SendAssistantDeliveryMessage(
	ctx context.Context,
	req AssistantDeliveryMessageRequest,
) (*SendMessageResponse, error) {
	if err := s.requireAssistantDeliveryMembership(
		ctx,
		req.ConversationID,
		req.CreatorPersonaID,
		req.AssistantSkillID,
	); err != nil {
		return nil, err
	}
	return s.SendMessage(ctx, SendMessageRequest{
		ConversationId: req.ConversationID,
		SenderId:       "assistant",
		Type:           req.Type,
		Content:        req.Content,
		ClientMsgId:    req.ClientMsgID,
	})
}

func (s *MessageService) requireAssistantDeliveryMembership(
	ctx context.Context,
	conversationID string,
	creatorPersonaID string,
	assistantSkillID string,
) error {
	membership, err := resolveAssistantDeliveryMembership(
		ctx,
		s.members,
		conversationID,
		creatorPersonaID,
		"",
		assistantSkillID,
	)
	if err != nil {
		return err
	}
	if !membership.CreatorMember || !membership.AssistantSkillMember {
		return generated.AppErrorFromBlocked(
			"assistant delivery requires current creator and assistant skill membership",
		)
	}
	return nil
}

// SendAnnouncementSystemMessage 写入一条 type=system_announcement 的会话消息
// （公告即触达）。该类型不在公开 SendMessage 白名单内，只能由服务端公告命令
// 内部产生；seq 分配、幂等、outbox 与未读投影复用消息主线。
func (s *MessageService) SendAnnouncementSystemMessage(
	ctx context.Context,
	conversationID, senderID, content, clientMsgID string,
) error {
	if strings.TrimSpace(clientMsgID) == "" {
		return generated.AppErrorFromMessageInvalid("announcement clientMsgId is required")
	}
	if strings.TrimSpace(content) == "" {
		return generated.AppErrorFromMessageInvalid("announcement content is required")
	}
	now := time.Now().UTC()
	msg := messagemodel.Message{
		ID:              generateID(),
		ConversationID:  conversationID,
		ClientMessageID: clientMsgID,
		SenderID:        senderID,
		Type:            "system_announcement",
		Content:         content,
		Status:          "sent",
		Timestamp:       now,
		Version:         1,
	}
	commandDigest, err := sendMessageCommandDigest(SendMessageRequest{
		ConversationId: conversationID,
		SenderId:       senderID,
		Type:           msg.Type,
		Content:        content,
		ClientMsgId:    clientMsgID,
	})
	if err != nil {
		return err
	}
	committed, err := s.messages.CommitMessage(ctx, MessageCommit{
		Message:       msg,
		CommandDigest: commandDigest,
		Events: []MessageOutboxEvent{{
			EventID:        msg.ID + ":v1:" + messageevent.MessageSent,
			EventType:      messageevent.MessageSent,
			ConversationID: conversationID,
			ActorID:        senderID,
			Payload: map[string]any{
				"conversationId": conversationID,
				"type":           msg.Type,
				"content":        msg.Content,
				"clientMsgId":    clientMsgID,
				"senderId":       senderID,
			},
		}},
	})
	if err != nil {
		if errors.Is(err, messagemodel.ErrMessageIdempotencyConflict) {
			// 同一公告命令重试：消息已写入，视为触达完成。
			return nil
		}
		return err
	}
	if err := s.projection.ProjectCommittedMessage(ctx, committed.Message); err != nil {
		return err
	}
	return s.cache.InvalidateConversation(ctx, conversationID)
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

// canonicalMentions 是 SendMessage 提及语义的唯一校验入口。正文只负责显示，
// 权限、目标和未读推进均消费这里产出的稳定成员 ID。
func (s *MessageService) canonicalMentions(
	ctx context.Context,
	req SendMessageRequest,
) ([]string, error) {
	if len(req.Mentions) == 0 {
		return nil, nil
	}
	if len(req.Mentions) > messageMentionLimit {
		return nil, generated.AppErrorFromMessageInvalid("mentions exceed 50 targets")
	}
	conversation, err := s.conversations.FindConversationByID(ctx, req.ConversationId)
	if err != nil {
		return nil, err
	}
	if conversation.Type != conversationTypeGroup {
		return nil, generated.AppErrorFromMessageInvalid(
			"mentions are only supported in group conversations",
		)
	}
	sender, err := s.members.FindMember(ctx, req.ConversationId, req.SenderId)
	if err != nil {
		return nil, generated.AppErrorFromMessageInvalid("mention sender is not an active member")
	}

	canonical := make([]string, 0, len(req.Mentions))
	seen := make(map[string]struct{}, len(req.Mentions))
	for _, raw := range req.Mentions {
		targetID := strings.TrimSpace(raw)
		if targetID == "" {
			continue
		}
		if targetID == "__all__" {
			if sender.Role != "owner" && sender.Role != "admin" {
				return nil, generated.AppErrorFromMessageInvalid(
					"only group owner or admin may mention all members",
				)
			}
		} else if targetID == "assistant" {
			assistantMember, findErr := s.members.FindAssistantMember(
				ctx,
				req.ConversationId,
			)
			if findErr != nil || assistantMember == nil ||
				strings.TrimSpace(assistantMember.UserId) == "" {
				return nil, generated.AppErrorFromMessageInvalid(
					"assistant mention requires an active assistant member",
				)
			}
			targetID = strings.TrimSpace(assistantMember.UserId)
		} else {
			member, findErr := s.members.FindMember(
				ctx,
				req.ConversationId,
				targetID,
			)
			if findErr != nil || member == nil {
				return nil, generated.AppErrorFromMessageInvalid(
					"mention target is not an active conversation member",
				)
			}
		}
		if _, exists := seen[targetID]; exists {
			continue
		}
		seen[targetID] = struct{}{}
		canonical = append(canonical, targetID)
	}
	return canonical, nil
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
	return strings.TrimSpace(req.SenderId) == "assistant"
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
	if strings.TrimSpace(req.SenderId) == "assistant" {
		return nil
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

	if msg.Status == "recalled" {
		// no-op：已撤回消息重复撤回，重放原结果；事件由唯一索引折叠。
		return nil
	}

	if time.Since(msg.Timestamp) > recallTimeLimit {
		return generated.AppErrorFromMessageRecallExpired("recall window exceeded")
	}

	if err := s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		if err := s.messages.SetMessageRecalled(txCtx, messageId); err != nil {
			return err
		}
		return s.messages.AppendMessageOutboxEvent(
			txCtx,
			MessageOutboxEvent{
				EventID:        chatAggregateEventID("recall:"+messageId, string(messageevent.MessageRecalled)),
				EventType:      string(messageevent.MessageRecalled),
				ConversationID: conversationId,
				ActorID:        senderId,
				Payload: map[string]any{
					"messageId":      messageId,
					"conversationId": conversationId,
					"seq":            msg.Seq,
					"recalledAt":     time.Now().UTC(),
				},
			},
			messageId,
			msg.Version+1,
		)
	}); err != nil {
		return err
	}

	_ = s.cache.InvalidateConversation(ctx, conversationId)
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
			receiptErr := s.receipts.CreateReceipt(
				txCtx,
				&messagemodel.MessageReceipt{
					ID:             generateID(),
					MessageID:      req.MessageId,
					ConversationID: req.ConversationId,
					UserID:         req.UserId,
					ReadAt:         now,
				},
			)
			if receiptErr != nil &&
				!errors.Is(
					receiptErr,
					messagemodel.ErrMessageReceiptAlreadyExists,
				) {
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
