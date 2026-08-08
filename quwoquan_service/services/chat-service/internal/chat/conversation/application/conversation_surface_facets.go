package application

import (
	"context"
	"errors"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/chat-service/generated/chat/conversation"
	conversationevent "quwoquan_service/services/chat-service/generated/chat/conversation/contract/event"
	userstateevent "quwoquan_service/services/chat-service/generated/chat/conversation_user_state/contract/event"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	userstateapp "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/application"
)

func (s *ConversationService) GetConversation(ctx context.Context, conversationId string) (*model.Conversation, error) {
	return s.conversations.FindConversationByID(ctx, conversationId)
}

type GatheringChatAccessSummary struct {
	GatheringID    string `json:"gatheringId"`
	ConversationID string `json:"conversationId"`
	AccessMode     string `json:"accessMode"`
	PostingPolicy  string `json:"postingPolicy"`
	ViewerRole     string `json:"viewerRole"`
	CanPost        bool   `json:"canPost"`
}

type GatheringPinnedAnnouncement struct {
	Content   string    `json:"content"`
	UpdatedBy string    `json:"updatedBy"`
	UpdatedAt time.Time `json:"updatedAt"`
}

type GatheringAssetIndexItem struct {
	MessageID    string    `json:"messageId"`
	Seq          int64     `json:"seq"`
	MediaAssetID string    `json:"mediaAssetId"`
	MessageType  string    `json:"messageType"`
	CreatedAt    time.Time `json:"createdAt"`
}

type GatheringChatBoardSlice struct {
	Access             GatheringChatAccessSummary   `json:"access"`
	PinnedAnnouncement *GatheringPinnedAnnouncement `json:"pinnedAnnouncement"`
	Assets             []GatheringAssetIndexItem    `json:"assets"`
}

func (s *ConversationService) GetGatheringChatBoard(
	ctx context.Context,
	conversationID string,
	viewerPersonaID string,
) (GatheringChatBoardSlice, error) {
	conversationID = strings.TrimSpace(conversationID)
	viewerPersonaID = strings.TrimSpace(viewerPersonaID)
	if conversationID == "" || viewerPersonaID == "" {
		return GatheringChatBoardSlice{}, generated.AppErrorFromUnauthorized(
			"Gathering Chat board requires conversation and trusted viewer persona",
		)
	}
	conversation, err := s.conversations.FindConversationByID(ctx, conversationID)
	if err != nil {
		return GatheringChatBoardSlice{}, err
	}
	if conversation.Type != conversationTypeGroup || conversation.OriginType != "gathering" ||
		strings.TrimSpace(conversation.GatheringId) == "" {
		return GatheringChatBoardSlice{}, generated.AppErrorFromConversationNotFound(
			"Gathering Chat board is not available for this conversation",
		)
	}
	member, err := s.members.FindMember(ctx, conversationID, viewerPersonaID)
	if err != nil {
		if errors.Is(err, model.ErrMemberNotFound) {
			return GatheringChatBoardSlice{}, generated.AppErrorFromBlocked(
				"Gathering Chat board requires active membership",
			)
		}
		return GatheringChatBoardSlice{}, err
	}
	accessMode := effectiveConversationAccessMode(conversation)
	postingPolicy := effectiveConversationPostingPolicy(conversation)
	board := GatheringChatBoardSlice{
		Access: GatheringChatAccessSummary{
			GatheringID: conversation.GatheringId, ConversationID: conversation.ID,
			AccessMode: accessMode, PostingPolicy: postingPolicy, ViewerRole: member.Role,
			CanPost: conversation.Status == model.ConversationStatusActive &&
				accessMode == ConversationAccessModeActive &&
				postingPolicy == ConversationPostingPolicyMemberChat,
		},
		Assets: []GatheringAssetIndexItem{},
	}
	if strings.TrimSpace(conversation.Announcement) != "" && conversation.AnnouncementUpdatedAt != nil {
		board.PinnedAnnouncement = &GatheringPinnedAnnouncement{
			Content: conversation.Announcement, UpdatedBy: conversation.AnnouncementUpdatedBy,
			UpdatedAt: conversation.AnnouncementUpdatedAt.UTC(),
		}
	}
	messages, err := s.messages.ListMessages(ctx, conversationID, 200, 0, 0)
	if err != nil {
		return GatheringChatBoardSlice{}, err
	}
	for _, message := range messages {
		if strings.TrimSpace(message.MediaAssetID) == "" || message.Status == "recalled" {
			continue
		}
		board.Assets = append(board.Assets, GatheringAssetIndexItem{
			MessageID: message.ID, Seq: message.Seq, MediaAssetID: message.MediaAssetID,
			MessageType: message.Type, CreatedAt: message.Timestamp.UTC(),
		})
	}
	return board, nil
}

type UpdateConversationTitleRequest struct {
	ConversationId string
	OperatorId     string
	Title          string
}

func (s *ConversationService) UpdateConversationTitle(ctx context.Context, req UpdateConversationTitleRequest) (*model.Conversation, error) {
	scopedKey, err := scopedChatIdempotencyKey(ctx, req.OperatorId)
	if err != nil {
		return nil, err
	}
	digest, err := chatCommandDigest("UpdateConversationTitle", req)
	if err != nil {
		return nil, err
	}
	var replayed model.Conversation
	if found, err := replayChatCommand(
		ctx, s.conversationCommands, scopedKey, "UpdateConversationTitle", digest, &replayed,
	); err != nil {
		return nil, err
	} else if found {
		return &replayed, nil
	}
	conv, err := s.conversations.FindConversationByID(ctx, req.ConversationId)
	if err != nil {
		return nil, err
	}
	if err := rejectSourceManagedConversation(conv, "UpdateConversationTitle"); err != nil {
		return nil, err
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
	// 治理开关消费点：仅当群开启 nameEditableByAdminOnly 时收紧为 owner/admin。
	if conv.Type == "group" && conv.NameEditableByAdminOnly &&
		operator.Role != "owner" && operator.Role != "admin" {
		return nil, chatGroupGovernanceForbidden(
			"group name editing is restricted to owner or admin",
		)
	}
	title := strings.TrimSpace(req.Title)
	if title == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleChat, "群名称不能为空", "conversation title is empty")
	}
	if conv.Title == title {
		// no-op：标题已一致，持久化回执但不递增 roster revision、不产生事件。
		receipt, receiptErr := chatCommandReceipt(scopedKey, "UpdateConversationTitle", digest, conv.ID, conv)
		if receiptErr != nil {
			return nil, receiptErr
		}
		if err := s.conversationCommands.CommitAggregateCommand(ctx, receipt, nil); err != nil {
			return nil, mapChatIdempotencyError(err)
		}
		return conv, nil
	}
	conv.Title = title
	conv.MembersRosterRevision++
	conv.UpdatedAt = time.Now()
	if err := s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		if err := s.conversations.UpdateConversation(txCtx, conv.ID, conv); err != nil {
			return err
		}
		receipt, receiptErr := chatCommandReceipt(scopedKey, "UpdateConversationTitle", digest, conv.ID, conv)
		if receiptErr != nil {
			return receiptErr
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
					"aspects":               []string{"title"},
				},
			}},
		))
	}); err != nil {
		return nil, err
	}
	_ = s.cache.InvalidateConversation(ctx, conv.ID)
	return conv, nil
}

// DirectConversationPromotion 描述「这条 1v1 会话是被什么升级出来的」。
//
// GreetingRequestID 非空表示来源是被回复的打招呼请求：会话按 contracts 声明落
// originType=greeting_reply + originGreetingRequestId，让破冰产生的会话与冷启动
// 私信可区分。零值表示无升级来源（保持 direct_init）。
type DirectConversationPromotion struct {
	GreetingRequestID string
	Intersection      *model.GreetingIntersectionSnapshot
}

// CreateOrReuseDirect 是 user-service 破冰升级的受信任入口：绕过关系门，
// 因为「对方已回复打招呼」本身就是同意证据，而该同意此刻还没写回关系投影。
//
// 复用既有会话时不覆盖 originType：一段已经存在的私信关系不应被后来的打招呼
// 改写来源，否则漏斗归因会把老会话算成破冰新增。
func (s *ConversationService) CreateOrReuseDirect(
	ctx context.Context,
	creatorID, peerID string,
	promotion DirectConversationPromotion,
) (*model.Conversation, error) {
	if strings.TrimSpace(creatorID) == "" || strings.TrimSpace(peerID) == "" {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"创建 1v1 会话需要双方成员",
			"creatorId and peerId required",
		)
	}
	if existing, err := s.findDirectConversationBetween(ctx, creatorID, peerID); err != nil {
		return nil, err
	} else if existing != nil {
		return existing, nil
	}
	greetingID := strings.TrimSpace(promotion.GreetingRequestID)
	originType := ""
	if greetingID != "" {
		originType = conversationOriginGreetingReply
	}
	return s.createDirectConversation(ctx, CreateConversationRequest{
		Type:                       conversationTypeDirect,
		CreatorId:                  creatorID,
		InitialMemberIds:           []string{peerID},
		OriginType:                 originType,
		OriginGreetingRequestID:    greetingID,
		OriginIntersectionSnapshot: promotion.Intersection,
	}, true, nil)
}

func (s *ConversationService) HasDirectBetween(ctx context.Context, memberA, memberB string) (bool, error) {
	conv, err := s.findDirectConversationBetween(ctx, memberA, memberB)
	if err != nil {
		return false, err
	}
	return conv != nil, nil
}

// findDirectConversationBetween composes the Conversation aggregate with the
// ConversationMembership identity index without allowing Conversation storage
// to read the membership collection directly.
func (s *ConversationService) findDirectConversationBetween(
	ctx context.Context,
	memberA string,
	memberB string,
) (*model.Conversation, error) {
	conversationIDs, err := s.members.ListSharedConversationIDs(ctx, memberA, memberB)
	if err != nil || len(conversationIDs) == 0 {
		return nil, err
	}
	conversations, err := s.conversations.FindConversationsByIDs(ctx, conversationIDs)
	if err != nil {
		return nil, err
	}
	for index := range conversations {
		conversation := conversations[index]
		if (conversation.Type == conversationTypeDirect || conversation.Type == conversationTypeEncrypted) &&
			(conversation.Status == "" || conversation.Status == model.ConversationStatusActive) {
			return &conversation, nil
		}
	}
	return nil, nil
}

type ListConversationsRequest struct {
	UserId string
	Cursor string
	Limit  int
}

func (s *ConversationService) ListConversations(ctx context.Context, req ListConversationsRequest) ([]model.Conversation, error) {
	page, err := s.ListConversationPage(ctx, req)
	if err != nil {
		return nil, err
	}
	return page.Items, nil
}

// ListConversationPage is the remote query facet; it retains the opaque
// keyset continuation generated by the Conversation reader.
func (s *ConversationService) ListConversationPage(
	ctx context.Context,
	req ListConversationsRequest,
) (model.ConversationPage, error) {
	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}
	statePage, err := s.userStates.ListUserStatePage(ctx, req.UserId, limit, req.Cursor)
	if err != nil {
		return model.ConversationPage{}, err
	}
	conversationIDs := make([]string, 0, len(statePage.Items))
	for _, state := range statePage.Items {
		conversationIDs = append(conversationIDs, state.ConversationId)
	}
	conversations, err := s.conversations.FindConversationsByIDs(ctx, conversationIDs)
	if err != nil {
		return model.ConversationPage{}, err
	}
	byID := make(map[string]model.Conversation, len(conversations))
	for _, conversation := range conversations {
		byID[conversation.ID] = conversation
	}
	items := make([]model.Conversation, 0, len(conversationIDs))
	for _, conversationID := range conversationIDs {
		if conversation, exists := byID[conversationID]; exists &&
			conversation.Status == model.ConversationStatusActive {
			items = append(items, conversation)
		}
	}
	return model.ConversationPage{Items: items, NextCursor: statePage.NextCursor}, nil
}

type UpdateSettingsRequest = userstateapp.UpdateSettingsRequest

func (s *ConversationService) UpdateSettings(ctx context.Context, req UpdateSettingsRequest) error {
	if _, _, err := requireActiveConversationMember(
		ctx,
		s.conversations,
		s.members,
		req.ConversationId,
		req.UserId,
	); err != nil {
		return err
	}
	scopedKey, err := scopedChatIdempotencyKey(ctx, req.UserId)
	if err != nil {
		return err
	}
	digest, err := chatCommandDigest("UpdateConversationSettings", req)
	if err != nil {
		return err
	}
	if found, err := replayChatCommand(
		ctx, s.userStateCommands, scopedKey, "UpdateConversationSettings", digest, nil,
	); err != nil || found {
		return err
	}
	state, err := s.userStates.FindUserState(ctx, req.UserId, req.ConversationId)
	if err != nil {
		now := time.Now()
		state = &model.ConversationUserState{
			ID:             generateID(),
			UserId:         req.UserId,
			ConversationId: req.ConversationId,
			UpdatedAt:      now,
		}
	}

	receipt, err := chatCommandReceipt(scopedKey, "UpdateConversationSettings", digest, state.ID, nil)
	if err != nil {
		return err
	}
	unchanged := (req.Muted == nil || state.Muted == *req.Muted) &&
		(req.Pinned == nil || state.Pinned == *req.Pinned)
	if unchanged {
		// no-op：目标设置已满足，持久化回执且不产生事件。
		if err := s.userStateCommands.CommitAggregateCommand(ctx, receipt, nil); err != nil {
			return mapChatIdempotencyError(err)
		}
		return nil
	}

	if req.Muted != nil {
		state.Muted = *req.Muted
	}
	if req.Pinned != nil {
		state.Pinned = *req.Pinned
	}
	state.UpdatedAt = time.Now()

	if err := s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		if err := s.userStates.UpsertUserState(txCtx, state); err != nil {
			return err
		}
		return mapChatIdempotencyError(s.userStateCommands.CommitAggregateCommand(
			txCtx,
			receipt,
			[]AggregateOutboxEvent{{
				EventID:        chatAggregateEventID(scopedKey, string(userstateevent.ConversationUserSettingsChanged)),
				EventType:      string(userstateevent.ConversationUserSettingsChanged),
				AggregateID:    state.ID,
				ConversationID: req.ConversationId,
				ActorID:        req.UserId,
				Payload: map[string]any{
					"conversationId": req.ConversationId,
					"userId":         req.UserId,
					"muted":          state.Muted,
					"pinned":         state.Pinned,
					"updatedAt":      state.UpdatedAt,
				},
			}},
		))
	}); err != nil {
		return err
	}

	_ = s.cache.InvalidateConversation(ctx, req.ConversationId)
	return nil
}
