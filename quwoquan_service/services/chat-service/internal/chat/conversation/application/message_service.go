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
	messageevent "quwoquan_service/services/chat-service/generated/chat/message/contract/event"
	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	messageapp "quwoquan_service/services/chat-service/internal/chat/message/application"
	messagemodel "quwoquan_service/services/chat-service/internal/chat/message/domain/model"
	messageports "quwoquan_service/services/chat-service/internal/chat/message/domain/ports"
)

const recallTimeLimit = 2 * time.Minute

const (
	messageContentRuneLimit      = 5000
	messageAudioWaveformMaxItems = 128
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
	receiptFacts      ReceiptFactStore
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
		receiptFacts:      storage.ReceiptFacts,
		projection:        storage.MessageProjection,
		cache:             cache,
		publisher:         publisher,
		relationships:     relationships,
		mediaAssets:       mediaAssets,
	}
}

type SendMessageRequest = messageapp.SendMessageRequest
type MessageCardCommand = messageapp.MessageCardCommand
type MessageCardObjectRefCommand = messageapp.MessageCardObjectRefCommand
type MessageCardAttributeCommand = messageapp.MessageCardAttributeCommand
type SendMessageResponse = messageapp.SendMessageResponse
type AssistantDeliveryMessageRequest = messageapp.AssistantDeliveryMessageRequest

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
	if err := s.validateReplyTarget(ctx, req); err != nil {
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
		AudioDurationMs:           req.AudioDurationMs,
		AudioWaveform:             req.AudioWaveform,
		Card:                      card,
		ReplyToMessageID:          req.ReplyToMessageId,
		Mentions:                  req.Mentions,
		Status:                    "sent",
		Timestamp:                 now,
		Version:                   1,
	}

	events := []messageports.OutboxEvent{{
		EventID:        msg.ID + ":" + messageevent.MessageSent,
		EventType:      messageevent.MessageSent,
		ConversationID: req.ConversationId,
		ActorID:        req.SenderId,
		Payload: map[string]any{
			"conversationId":            req.ConversationId,
			"type":                      msg.Type,
			"content":                   msg.Content,
			"mediaAssetId":              msg.MediaAssetID,
			"audioDurationMs":           msg.AudioDurationMs,
			"audioWaveform":             msg.AudioWaveform,
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
			events = append(events, messageports.OutboxEvent{
				EventID:        msg.ID + ":" + messageevent.AssistantMentioned,
				EventType:      messageevent.AssistantMentioned,
				ConversationID: req.ConversationId,
				ActorID:        req.SenderId,
				Payload: map[string]any{
					"conversationId":     req.ConversationId,
					"senderId":           req.SenderId,
					"senderAccountId":    req.SenderAccountID,
					"content":            msg.Content,
					"assistantMemberId":  assistantMember.UserId,
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
	beforeSeq int64,
	limit int,
) ([]MessageSlice, error) {
	if err := s.requireAssistantDeliveryMembership(
		ctx,
		conversationID,
		creatorPersonaID,
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
) error {
	membership, err := resolveAssistantDeliveryMembership(
		ctx,
		s.members,
		conversationID,
		creatorPersonaID,
		"",
	)
	if err != nil {
		return err
	}
	if !membership.CreatorMember || !membership.AssistantMember {
		return generated.AppErrorFromBlocked(
			"assistant delivery requires current creator and assistant membership",
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
		Events: []messageports.OutboxEvent{{
			EventID:        msg.ID + ":" + messageevent.MessageSent,
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

// SendGreetingOpeningMessage 把打招呼时写下的那句话落成会话首条消息。
//
// 为什么必须服务端写：破冰的语义是「A 先说了一句话，B 同意后这句话成为对话开头」。
// 若不落库，B 同意后打开的是空会话，A 说过的话凭空消失，B 也无从判断该回什么——
// 整条 打招呼 → 同意 → 私信 链路在成功的那一刻丢掉了唯一的上下文。
//
// 与 SendMessage 的差别只在通行判定：此刻 GreetingRequest 还没提交为 replied，
// 关系投影里 A 仍是陌生人，公开路径的 ensureMessageAllowed 必然拒绝。回复动作
// 本身就是对方的同意证据，因此这里跳过关系门，但保留消息主线的
// seq 分配 / 幂等 / outbox / 未读投影，不另建第二条写路径。
//
// 发送者是打招呼的发起者（不是系统），因为这句话确实是他写的；
// clientMsgID 由调用方按 greetingId 派生，重放只会命中同一条消息。
func (s *MessageService) SendGreetingOpeningMessage(
	ctx context.Context,
	conversationID, requesterID, content, clientMsgID string,
) error {
	conversationID = strings.TrimSpace(conversationID)
	requesterID = strings.TrimSpace(requesterID)
	clientMsgID = strings.TrimSpace(clientMsgID)
	content = strings.TrimSpace(content)
	if conversationID == "" || requesterID == "" || clientMsgID == "" {
		return generated.AppErrorFromMessageInvalid(
			"greeting opening message requires conversationId, requesterId and clientMsgId",
		)
	}
	if content == "" {
		// 打招呼可以不带话（fields.yaml 的 requestMessage 可空）：没有话就没有首条消息，
		// 不得替用户编造一句问候。
		return nil
	}
	req := SendMessageRequest{
		ConversationId: conversationID,
		SenderId:       requesterID,
		Type:           "text",
		Content:        content,
		ClientMsgId:    clientMsgID,
	}
	if _, err := validateMessageCommand(req); err != nil {
		return err
	}
	commandDigest, err := sendMessageCommandDigest(req)
	if err != nil {
		return err
	}
	now := time.Now().UTC()
	msg := messagemodel.Message{
		ID:              generateID(),
		ConversationID:  conversationID,
		ClientMessageID: clientMsgID,
		SenderID:        requesterID,
		Type:            req.Type,
		Content:         req.Content,
		Status:          "sent",
		Timestamp:       now,
		Version:         1,
	}
	committed, err := s.messages.CommitMessage(ctx, MessageCommit{
		Message:       msg,
		CommandDigest: commandDigest,
		Events: []messageports.OutboxEvent{{
			EventID:        msg.ID + ":" + messageevent.MessageSent,
			EventType:      messageevent.MessageSent,
			ConversationID: conversationID,
			ActorID:        requesterID,
			Payload: map[string]any{
				"conversationId": conversationID,
				"type":           msg.Type,
				"content":        msg.Content,
				"clientMsgId":    clientMsgID,
				"senderId":       requesterID,
			},
		}},
	})
	if err != nil {
		if errors.Is(err, messagemodel.ErrMessageIdempotencyConflict) {
			// 同一次回复重放：首条消息已落库，视为已完成。
			return nil
		}
		return err
	}
	if err := s.projection.ProjectCommittedMessage(ctx, committed.Message); err != nil {
		return err
	}
	return s.cache.InvalidateConversation(ctx, conversationID)
}

// validateReplyTarget 校验引用回复的目标：必须存在且属于同一会话，
// 否则脏 ID 入库后接收端引用块永远解析失败。已撤回目标允许引用
//（渲染为撤回占位），与主流 IM 语义一致。
func (s *MessageService) validateReplyTarget(
	ctx context.Context,
	req SendMessageRequest,
) error {
	replyTo := strings.TrimSpace(req.ReplyToMessageId)
	if replyTo == "" {
		return nil
	}
	target, err := s.messages.FindMessageByID(ctx, replyTo)
	if err != nil {
		if errors.Is(err, messagemodel.ErrMessageNotFound) {
			return generated.AppErrorFromMessageInvalid(
				"replyToMessageId does not reference an existing message",
			)
		}
		return err
	}
	if target.ConversationID != req.ConversationId {
		return generated.AppErrorFromMessageInvalid(
			"replyToMessageId references a message from another conversation",
		)
	}
	return nil
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
	if messageType != "audio" {
		if req.AudioDurationMs != 0 || len(req.AudioWaveform) != 0 {
			return nil, generated.AppErrorFromMessageInvalid(
				"audio metadata is only allowed on audio messages",
			)
		}
	} else {
		if req.AudioDurationMs < 0 {
			return nil, generated.AppErrorFromMessageInvalid(
				"audioDurationMs must be positive",
			)
		}
		if len(req.AudioWaveform) > messageAudioWaveformMaxItems {
			return nil, generated.AppErrorFromMessageInvalid(
				"audioWaveform exceeds 128 samples",
			)
		}
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
	kind := messagemodel.MessageCardKind(strings.TrimSpace(req.Card.Kind))
	title := strings.TrimSpace(req.Card.Title)
	if kind == "" || title == "" {
		return nil, generated.AppErrorFromMessageInvalid("card kind and title are required")
	}
	if !kind.Valid() {
		return nil, generated.AppErrorFromMessageInvalid("unsupported card kind")
	}
	objectRef, err := validateMessageCardObjectRef(kind, req.Card.ObjectRef)
	if err != nil {
		return nil, err
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
		ObjectRef:    objectRef,
		Subtitle:     strings.TrimSpace(req.Card.Subtitle),
		ThumbnailURL: strings.TrimSpace(req.Card.ThumbnailURL),
		DeepLink:     strings.TrimSpace(req.Card.DeepLink),
		LandingURL:   strings.TrimSpace(req.Card.LandingURL),
		ShareText:    strings.TrimSpace(req.Card.ShareText),
		Message:      strings.TrimSpace(req.Card.Message),
		Attributes:   attributes,
	}, nil
}

func validateMessageCardObjectRef(
	kind messagemodel.MessageCardKind,
	ref *MessageCardObjectRefCommand,
) (*messagemodel.MessageCardObjectRef, error) {
	required := map[messagemodel.MessageCardKind]struct {
		objectType string
		routeID    string
	}{
		messagemodel.MessageCardKindContentPost:   {"post", "contentDetail"},
		messagemodel.MessageCardKindUserProfile:   {"user", "userProfile"},
		messagemodel.MessageCardKindEntityProfile: {"homepage", "homepageDetail"},
		messagemodel.MessageCardKindCircle:        {"circle", "circleDetail"},
		messagemodel.MessageCardKindGathering:     {"gathering", "gatheringDetail"},
	}
	expected, actionable := required[kind]
	if !actionable {
		if ref != nil {
			return nil, generated.AppErrorFromMessageInvalid("non-actionable card must not contain objectRef")
		}
		return nil, nil
	}
	if ref == nil {
		return nil, generated.AppErrorFromMessageInvalid("actionable card requires objectRef")
	}
	objectType := strings.TrimSpace(ref.ObjectTypeRef)
	objectID := strings.TrimSpace(ref.ObjectID)
	routeID := strings.TrimSpace(ref.RouteID)
	if objectID == "" || objectType != expected.objectType || routeID != expected.routeID {
		return nil, generated.AppErrorFromMessageInvalid("card objectRef does not match kind")
	}
	return &messagemodel.MessageCardObjectRef{
		ObjectTypeRef: objectType,
		ObjectID:      objectID,
		RouteID:       routeID,
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
	if conv.Status != conversationmodel.ConversationStatusActive {
		return chatBlocked("conversation is not active")
	}
	if effectiveConversationAccessMode(conv) == ConversationAccessModeReadOnly {
		return chatBlocked("conversation access mode is read_only")
	}
	if effectiveConversationPostingPolicy(conv) == ConversationPostingPolicyAnnouncementsOnly {
		return chatBlocked("conversation posting policy is announcements_only")
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
			messageports.OutboxEvent{
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

type ListMessagesRequest = messageapp.ListMessagesRequest
type MessageSlice = messageapp.MessageSlice

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

type ListConversationAssetsRequest = messageapp.ListConversationAssetsRequest
type ConversationAssetRow = messageapp.ConversationAssetRow
type ConversationAssetsPage = messageapp.ConversationAssetsPage

// ListConversationAssets 是群空间相册/文件宫格的媒体索引读面：
// Message owner 事实 + MediaAsset delivery Reader 组合，App 直接渲染。
func (s *MessageService) ListConversationAssets(
	ctx context.Context,
	req ListConversationAssetsRequest,
) (_ *ConversationAssetsPage, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "chat.ListConversationAssets",
		attribute.String("conversation.id", req.ConversationId),
		attribute.String("assets.kind", req.Kind))
	defer func() { rtobs.EndSpan(span, err) }()

	kind := strings.TrimSpace(req.Kind)
	var messageType string
	switch kind {
	case "image":
		messageType = "image"
	case "file":
		messageType = "file"
	default:
		return nil, generated.AppErrorFromInvalidArgument(
			"assets kind must be image or file",
		)
	}
	if err := s.requireConversationMembership(ctx, req.ConversationId, req.ViewerID); err != nil {
		return nil, err
	}
	limit := req.Limit
	if limit <= 0 || limit > 200 {
		limit = 60
	}
	messages, err := s.messages.ListMediaMessages(
		ctx,
		req.ConversationId,
		messageType,
		limit+1,
		req.BeforeSeq,
	)
	if err != nil {
		return nil, err
	}
	hasMore := len(messages) > limit
	if hasMore {
		messages = messages[:limit]
	}
	slices, err := s.hydrateMessageSlices(ctx, messages)
	if err != nil {
		return nil, err
	}
	rows := make([]ConversationAssetRow, 0, len(slices))
	for _, slice := range slices {
		row := ConversationAssetRow{
			MessageID:   slice.Message.ID,
			Seq:         slice.Message.Seq,
			MediaAssetID: slice.Message.MediaAssetID,
			MessageType: slice.Message.Type,
			SenderID:    slice.Message.SenderID,
			SenderName:  slice.Message.SenderDisplayNameSnapshot,
			FileName:    slice.Message.Content,
			CreatedAt:   slice.Message.Timestamp,
		}
		if slice.Media != nil {
			row.MediaDeliveryURL = slice.Media.DeliveryURL
			row.MediaContentType = slice.Media.ContentType
			row.MediaFileSizeBytes = slice.Media.FileSize
		}
		rows = append(rows, row)
	}
	page := &ConversationAssetsPage{Items: rows, HasMore: hasMore}
	if hasMore && len(rows) > 0 {
		next := rows[len(rows)-1].Seq
		page.NextBeforeSeq = &next
	}
	return page, nil
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

type SyncMessagesRequest = messageapp.SyncMessagesRequest
type SyncMessagesResponse = messageapp.SyncMessagesResponse

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
