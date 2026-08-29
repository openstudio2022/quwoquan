package application

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/chat-service/generated/chat/conversation"
	conversationevent "quwoquan_service/services/chat-service/generated/chat/conversation/contract/event"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

const (
	defaultGroupSizeLimit = 1000
	maxGroupSizeLimit     = 1000

	ConversationAccessModeActive   = "active"
	ConversationAccessModeReadOnly = "read_only"

	ConversationPostingPolicyMemberChat        = "member_chat"
	ConversationPostingPolicyAnnouncementsOnly = "announcements_only"
)

var errGatheringProjectionConcurrentUpdate = errors.New("Gathering conversation projection changed concurrently")

type ConversationService struct {
	transactions                      TransactionRunner
	conversations                     ConversationStore
	circleGroupConversations          CircleGroupConversationReader
	gatheringConversations            GatheringConversationReader
	circleGroupChatBindingProjections CircleGroupChatBindingProjectionStore
	messages                          MessageStore
	members                           MemberStore
	userStates                        UserStateStore
	conversationCommands              AggregateCommandStore
	userStateCommands                 AggregateCommandStore
	cache                             ConversationCache
	publisher                         EventPublisher
	profiles                          ProfileSnapshotResolver
	relationships                     RelationshipGate
	media                             GroupAvatarAssetizer
	syncPublisher                     UserSyncPublisher
	scheduler                         GroupAvatarTaskScheduler
	announcementSender                AnnouncementMessageSender
}

func NewConversationService(
	storage ChatStoragePorts,
	cache ConversationCache,
	publisher EventPublisher,
	profiles ProfileSnapshotResolver,
	relationships RelationshipGate,
	media GroupAvatarAssetizer,
	sync UserSyncPublisher,
	scheduler GroupAvatarTaskScheduler,
) *ConversationService {
	publisher = requireEventPublisher(publisher)
	if profiles == nil {
		profiles = noopProfileResolver{}
	}
	if relationships == nil {
		relationships = DenyRelationshipGate()
	}
	scheduler = requireGroupAvatarTaskScheduler(scheduler)
	return &ConversationService{
		transactions:                      storage.Transactions,
		conversations:                     storage.Conversations,
		circleGroupConversations:          storage.CircleGroupConversations,
		gatheringConversations:            storage.GatheringConversations,
		circleGroupChatBindingProjections: storage.CircleGroupChatBindingProjections,
		messages:                          storage.Messages,
		members:                           storage.Members,
		userStates:                        storage.UserStates,
		conversationCommands:              storage.ConversationCommands,
		userStateCommands:                 storage.UserStateCommands,
		cache:                             cache,
		publisher:                         publisher,
		profiles:                          profiles,
		relationships:                     relationships,
		media:                             media,
		syncPublisher:                     sync,
		scheduler:                         scheduler,
	}
}

type CreateConversationRequest struct {
	Type                       string
	Title                      string
	CircleId                   string
	CircleGroupId              string
	GatheringId                string
	EntityId                   string
	OriginType                 string
	OriginGreetingRequestID    string
	OriginIntersectionSnapshot *model.GreetingIntersectionSnapshot
	CircleGroupSourceEventID   string
	GatheringSourceEventID     string
	GatheringSourceVersion     int64
	AccessMode                 string
	PostingPolicy              string
	MaxGroupSize               int
	CreatorId                  string
	InitialMemberIds           []string
}

// CreateConversation 是公开创建命令：direct/encrypted 会话按参与者对唯一
// （重复创建返回既有会话），group 创建以 actor-scoped Idempotency-Key 回执
// 保证重放返回首个会话；事件在同一事务写入 conversations_outbox。
func (s *ConversationService) CreateConversation(ctx context.Context, req CreateConversationRequest) (*model.Conversation, error) {
	if isManagedBindingCreateRequest(req) ||
		strings.TrimSpace(req.EntityId) != "" ||
		strings.TrimSpace(req.OriginType) != "" ||
		strings.TrimSpace(req.CircleGroupSourceEventID) != "" ||
		strings.TrimSpace(req.GatheringSourceEventID) != "" {
		return nil, generated.AppErrorFromSourceManagedBindingWriteForbidden(
			"public CreateConversation must not supply source binding fields",
		)
	}
	scopedKey, err := scopedChatIdempotencyKey(ctx, req.CreatorId)
	if err != nil {
		return nil, err
	}
	digest, err := chatCommandDigest("CreateConversation", req)
	if err != nil {
		return nil, err
	}
	var replayed model.Conversation
	if found, err := s.replayCreateConversation(
		ctx, scopedKey, digest, &replayed,
	); err != nil {
		return nil, err
	} else if found {
		return &replayed, nil
	}
	created, err := s.createDirectConversation(ctx, req, false, &commandReceiptSpec{
		ScopedKey:     scopedKey,
		CommandName:   "CreateConversation",
		CommandDigest: digest,
	})
	if err != nil {
		if errors.Is(err, ErrAggregateIdempotencyKeyTaken) {
			if found, replayErr := s.replayCreateConversation(
				ctx, scopedKey, digest, &replayed,
			); replayErr != nil {
				return nil, replayErr
			} else if found {
				return &replayed, nil
			}
		}
		return nil, mapConversationCreateIdempotencyError(err)
	}
	return created, nil
}

type GatheringConversationProvisioningRequest struct {
	SourceEventID  string
	SourceVersion  int64
	GatheringID    string
	OwnerPersonaID string
	Title          string
	AccessMode     string
	PostingPolicy  string
}

// ProvisionGatheringConversation creates the sole Chat Conversation bound to
// one Gathering. The command receipt, Conversation, owner membership/UserState
// and outbox facts commit atomically; replay returns the first binding.
func (s *ConversationService) ProvisionGatheringConversation(
	ctx context.Context,
	req GatheringConversationProvisioningRequest,
) (*model.Conversation, error) {
	req.SourceEventID = strings.TrimSpace(req.SourceEventID)
	req.GatheringID = strings.TrimSpace(req.GatheringID)
	req.OwnerPersonaID = strings.TrimSpace(req.OwnerPersonaID)
	req.Title = strings.TrimSpace(req.Title)
	req.AccessMode = strings.TrimSpace(req.AccessMode)
	req.PostingPolicy = strings.TrimSpace(req.PostingPolicy)
	if req.SourceEventID == "" || req.GatheringID == "" || req.OwnerPersonaID == "" ||
		req.Title == "" || req.SourceVersion <= 0 ||
		!isConversationAccessMode(req.AccessMode) ||
		!isConversationPostingPolicy(req.PostingPolicy) {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"相聚会话事实不完整",
			"Gathering conversation projection requires versioned room and policy facts",
		)
	}
	if s.gatheringConversations == nil {
		return nil, generated.AppErrorFromConversationProjectionUnavailable("Gathering conversation reader is not configured")
	}
	if existing, err := s.gatheringConversations.FindConversationByGatheringID(ctx, req.GatheringID); err == nil {
		return s.projectExistingGatheringConversation(ctx, existing, req)
	} else if !isConversationNotFound(err) {
		return nil, err
	}

	receiptKey := "system:gathering-provision:" + req.SourceEventID
	internalCreate := CreateConversationRequest{
		Type: conversationTypeGroup, Title: req.Title, GatheringId: req.GatheringID,
		OriginType: "gathering", GatheringSourceEventID: req.SourceEventID,
		GatheringSourceVersion: req.SourceVersion,
		AccessMode:             req.AccessMode, PostingPolicy: req.PostingPolicy,
		MaxGroupSize: defaultGroupSizeLimit, CreatorId: req.OwnerPersonaID,
	}
	digest, err := chatCommandDigest("ProvisionGatheringConversation", internalCreate)
	if err != nil {
		return nil, err
	}
	var replayed model.Conversation
	if found, err := replayChatCommand(
		ctx, s.conversationCommands, receiptKey, "ProvisionGatheringConversation", digest, &replayed,
	); err != nil {
		return nil, err
	} else if found {
		return &replayed, nil
	}
	return s.createDirectConversation(ctx, internalCreate, true, &commandReceiptSpec{
		ScopedKey: receiptKey, CommandName: "ProvisionGatheringConversation", CommandDigest: digest,
	})
}

func (s *ConversationService) projectExistingGatheringConversation(
	ctx context.Context,
	existing *model.Conversation,
	req GatheringConversationProvisioningRequest,
) (*model.Conversation, error) {
	if existing.CreatorId != req.OwnerPersonaID || existing.Type != conversationTypeGroup ||
		existing.OriginType != "gathering" {
		return nil, generated.AppErrorFromGatheringBindingConflict(
			"existing Gathering conversation binding does not match source fact",
		)
	}
	if existing.GatheringSourceVersion > req.SourceVersion {
		return existing, nil
	}
	if existing.GatheringSourceVersion == req.SourceVersion {
		if gatheringConversationProjectionMatches(existing, req) {
			return existing, nil
		}
		return nil, generated.AppErrorFromGatheringBindingConflict(
			"Gathering source version was reused by another room or policy fact",
		)
	}

	for attempt := 0; attempt < 3; attempt++ {
		var projected *model.Conversation
		err := s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
			current, err := s.gatheringConversations.FindConversationByGatheringID(txCtx, req.GatheringID)
			if err != nil {
				return err
			}
			if current.CreatorId != req.OwnerPersonaID || current.Type != conversationTypeGroup ||
				current.OriginType != "gathering" {
				return generated.AppErrorFromGatheringBindingConflict(
					"existing Gathering conversation binding does not match source fact",
				)
			}
			if current.GatheringSourceVersion > req.SourceVersion {
				projected = current
				return nil
			}
			if current.GatheringSourceVersion == req.SourceVersion {
				if !gatheringConversationProjectionMatches(current, req) {
					return generated.AppErrorFromGatheringBindingConflict(
						"Gathering source version was reused by another room or policy fact",
					)
				}
				projected = current
				return nil
			}

			next := *current
			policyChanged := effectiveConversationAccessMode(current) != req.AccessMode ||
				effectiveConversationPostingPolicy(current) != req.PostingPolicy
			next.Title = req.Title
			next.GatheringSourceVersion = req.SourceVersion
			next.GatheringSourceEventID = req.SourceEventID
			next.AccessMode = req.AccessMode
			next.PostingPolicy = req.PostingPolicy
			applied, err := s.gatheringConversations.ApplyGatheringConversationProjection(
				txCtx, req.GatheringID, current.GatheringSourceVersion, &next,
			)
			if err != nil {
				return err
			}
			if !applied {
				return errGatheringProjectionConcurrentUpdate
			}
			if policyChanged {
				if err := s.conversationCommands.AppendAggregateOutboxEvents(
					txCtx,
					[]AggregateOutboxEvent{{
						EventID:        chatAggregateEventID(req.SourceEventID, "GatheringConversationPolicyChanged"),
						EventType:      "GatheringConversationPolicyChanged",
						AggregateID:    next.ID,
						ConversationID: next.ID,
						ActorID:        "gathering_projector",
						Payload: map[string]any{
							"conversationId": next.ID, "gatheringId": req.GatheringID,
							"accessMode":    req.AccessMode,
							"postingPolicy": req.PostingPolicy, "sourceVersion": req.SourceVersion,
							"updatedAt": next.UpdatedAt,
						},
					}},
				); err != nil {
					return err
				}
			}
			projected = &next
			return nil
		})
		if errors.Is(err, errGatheringProjectionConcurrentUpdate) {
			continue
		}
		if err != nil {
			return nil, err
		}
		return projected, nil
	}
	return nil, generated.AppErrorFromGatheringBindingConflict(
		"Gathering conversation projection did not converge after concurrent updates",
	)
}

func gatheringConversationProjectionMatches(
	conversation *model.Conversation,
	req GatheringConversationProvisioningRequest,
) bool {
	return conversation.Title == req.Title &&
		effectiveConversationAccessMode(conversation) == req.AccessMode &&
		effectiveConversationPostingPolicy(conversation) == req.PostingPolicy
}

func isConversationAccessMode(value string) bool {
	return value == ConversationAccessModeActive || value == ConversationAccessModeReadOnly
}

func isConversationPostingPolicy(value string) bool {
	return value == ConversationPostingPolicyMemberChat ||
		value == ConversationPostingPolicyAnnouncementsOnly
}

func effectiveConversationAccessMode(conversation *model.Conversation) string {
	if conversation != nil && conversation.AccessMode == ConversationAccessModeReadOnly {
		return ConversationAccessModeReadOnly
	}
	return ConversationAccessModeActive
}

func EffectiveConversationAccessMode(conversation model.Conversation) string {
	return effectiveConversationAccessMode(&conversation)
}

func effectiveConversationPostingPolicy(conversation *model.Conversation) string {
	if conversation != nil && conversation.PostingPolicy == ConversationPostingPolicyAnnouncementsOnly {
		return ConversationPostingPolicyAnnouncementsOnly
	}
	return ConversationPostingPolicyMemberChat
}

func EffectiveConversationPostingPolicy(conversation model.Conversation) string {
	return effectiveConversationPostingPolicy(&conversation)
}

// replayCreateConversation reads the command receipt with the operation's
// conflict mapping. It is also used after a concurrent receipt insertion:
// retrying the exact command returns the first conversation, while a different
// payload receives the declared conversation idempotency conflict.
func (s *ConversationService) replayCreateConversation(
	ctx context.Context,
	scopedKey string,
	commandDigest string,
	result *model.Conversation,
) (bool, error) {
	raw, found, err := s.conversationCommands.FindAggregateCommandReceipt(
		ctx, scopedKey, "CreateConversation", commandDigest,
	)
	if err != nil {
		return false, mapConversationCreateIdempotencyError(err)
	}
	if !found {
		return false, nil
	}
	if err := json.Unmarshal(raw, result); err != nil {
		return false, fmt.Errorf("decode replayed CreateConversation result: %w", err)
	}
	return true, nil
}

// CircleGroupConversationProvisioningRequest 是 CircleGroupCreated durable event
// 的受信任输入。它绝不能由 HTTP 或客户端 DTO 构造。
type CircleGroupConversationProvisioningRequest struct {
	SourceEventID  string
	CircleID       string
	CircleGroupID  string
	OwnerPersonaID string
	Title          string
}

// ProvisionCircleGroupConversation 将 CircleGroupCreated 投影为唯一的 Chat
// Conversation。事件回执、Conversation、owner 名册/UserState 与反向绑定 outbox
// 同一事务提交；因此在 ACK 前崩溃时重放会返回相同绑定，而不会创建第二会话。
func (s *ConversationService) ProvisionCircleGroupConversation(
	ctx context.Context,
	req CircleGroupConversationProvisioningRequest,
) (*model.Conversation, error) {
	req.SourceEventID = strings.TrimSpace(req.SourceEventID)
	req.CircleID = strings.TrimSpace(req.CircleID)
	req.CircleGroupID = strings.TrimSpace(req.CircleGroupID)
	req.OwnerPersonaID = strings.TrimSpace(req.OwnerPersonaID)
	req.Title = strings.TrimSpace(req.Title)
	if req.SourceEventID == "" || req.CircleID == "" || req.CircleGroupID == "" ||
		req.OwnerPersonaID == "" || req.Title == "" {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"圈群创建事件不完整",
			"CircleGroupCreated requires event, circle, group, owner and name",
		)
	}
	if s.circleGroupConversations == nil {
		return nil, generated.AppErrorFromConversationProjectionUnavailable("circle group conversation reader is not configured")
	}
	if existing, err := s.circleGroupConversations.FindConversationByCircleGroupID(
		ctx, req.CircleGroupID,
	); err == nil {
		if existing.CircleId != req.CircleID || existing.CreatorId != req.OwnerPersonaID {
			return nil, generated.AppErrorFromCircleGroupBindingConflict(
				"existing circle group conversation binding does not match source fact",
			)
		}
		return existing, nil
	} else if !isConversationNotFound(err) {
		return nil, err
	}

	receiptKey := "system:circle-group-provision:" + req.SourceEventID
	internalCreate := CreateConversationRequest{
		Type:                     conversationTypeGroup,
		Title:                    req.Title,
		CircleId:                 req.CircleID,
		CircleGroupId:            req.CircleGroupID,
		OriginType:               "circle_group",
		CircleGroupSourceEventID: req.SourceEventID,
		MaxGroupSize:             maxGroupSizeLimit,
		CreatorId:                req.OwnerPersonaID,
	}
	digest, err := chatCommandDigest("ProvisionCircleGroupConversation", internalCreate)
	if err != nil {
		return nil, err
	}
	var replayed model.Conversation
	if found, err := replayChatCommand(
		ctx,
		s.conversationCommands,
		receiptKey,
		"ProvisionCircleGroupConversation",
		digest,
		&replayed,
	); err != nil {
		return nil, err
	} else if found {
		return &replayed, nil
	}
	return s.createDirectConversation(ctx, internalCreate, true, &commandReceiptSpec{
		ScopedKey:     receiptKey,
		CommandName:   "ProvisionCircleGroupConversation",
		CommandDigest: digest,
	})
}

// commandReceiptSpec 携带公开命令的幂等回执材料；内部复用路径传 nil。
type commandReceiptSpec struct {
	ScopedKey     string
	CommandName   string
	CommandDigest string
}

func (s *ConversationService) createDirectConversation(
	ctx context.Context,
	req CreateConversationRequest,
	bypassRelationshipGate bool,
	receiptSpec *commandReceiptSpec,
) (*model.Conversation, error) {
	now := time.Now()
	req.Type = strings.TrimSpace(req.Type)
	if req.Type != conversationTypeDirect && req.Type != conversationTypeGroup && req.Type != conversationTypeEncrypted {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"不支持的会话类型",
			"unsupported conversation type",
		)
	}
	originType := defaultString(req.OriginType, "direct_init")
	if req.Type == conversationTypeGroup {
		originType = inferGroupConversationOrigin(req, originType)
	}
	maxGroupSize := 2
	if req.Type == conversationTypeGroup {
		maxGroupSize = req.MaxGroupSize
		if maxGroupSize <= 0 {
			maxGroupSize = defaultGroupSizeLimit
		}
		if maxGroupSize > maxGroupSizeLimit {
			return nil, chatGroupFull("max group size exceeds supported limit")
		}
	}
	initialMemberIds := dedupeUserIDs(req.InitialMemberIds, req.CreatorId)
	if req.Type == conversationTypeDirect || req.Type == conversationTypeEncrypted {
		if len(initialMemberIds) != 1 {
			return nil, rterr.NewInvalidArgument(
				rterr.ModuleChat,
				"1 对 1 会话必须只有一个对方成员",
				"direct conversation requires exactly one invitee",
			)
		}
		peerID := initialMemberIds[0]
		if existing, findErr := s.findDirectConversationBetween(ctx, req.CreatorId, peerID); findErr == nil && existing != nil {
			return existing, nil
		}
		if !bypassRelationshipGate {
			capability, err := s.relationships.GetCapability(ctx, req.CreatorId, peerID)
			if err != nil {
				return nil, err
			}
			if capability.IsBlocked || capability.IsBlockedBy {
				return nil, chatBlocked("direct conversation blocked by relationship gate")
			}
			if !capability.CanCreateDirectConversation && !capability.HasFormalConversation {
				return nil, chatGreetingRequired("direct conversation requires mutual follow or replied greeting")
			}
		}
	}
	if req.Type == conversationTypeGroup && len(initialMemberIds)+1 > maxGroupSize {
		return nil, chatGroupFull("initial members exceed max group size")
	}
	if req.Type == conversationTypeGroup && !bypassRelationshipGate && !isManagedBindingCreateRequest(req) {
		if err := s.validateGroupInitialMembers(ctx, req.CreatorId, initialMemberIds); err != nil {
			return nil, err
		}
	}
	receiptEnabled := maxGroupSize <= 50

	conv := &model.Conversation{
		ID:                         generateID(),
		Type:                       req.Type,
		Title:                      req.Title,
		CreatorId:                  req.CreatorId,
		CircleId:                   req.CircleId,
		CircleGroupId:              req.CircleGroupId,
		GatheringId:                req.GatheringId,
		GatheringSourceVersion:     req.GatheringSourceVersion,
		GatheringSourceEventID:     req.GatheringSourceEventID,
		AccessMode:                 defaultString(req.AccessMode, ConversationAccessModeActive),
		PostingPolicy:              defaultString(req.PostingPolicy, ConversationPostingPolicyMemberChat),
		EntityId:                   req.EntityId,
		OriginType:                 originType,
		OriginGreetingRequestID:    strings.TrimSpace(req.OriginGreetingRequestID),
		OriginIntersectionSnapshot: req.OriginIntersectionSnapshot,
		MaxGroupSize:               maxGroupSize,
		ReceiptEnabled:             receiptEnabled,
		Status:                     model.ConversationStatusActive,
		CreatedAt:                  now,
		UpdatedAt:                  now,
	}
	profileIDs := append([]string{req.CreatorId}, initialMemberIds...)
	profMap, _ := s.profiles.ResolveMany(ctx, profileIDs)
	lookup := func(uid string) (string, string, string, string, int) {
		if p, ok := profMap[uid]; ok {
			return p.UserHandle, p.DisplayName, p.AvatarURL, p.AvatarAssetID, p.AvatarVersion
		}
		return "", "", "", "", 0
	}

	creatorHandle, creatorDN, creatorAV, creatorAssetID, creatorAvatarVersion := lookup(req.CreatorId)
	if IsGroupConversation(*conv) {
		conv.AvatarUrl = strings.TrimSpace(creatorAV)
		if conv.AvatarUrl == "" {
			conv.AvatarUrl = DefaultGroupAvatarURL()
		}
	}
	creator := &model.ConversationMember{
		ID:             generateID(),
		ConversationId: conv.ID,
		UserId:         req.CreatorId,
		UserHandle:     creatorHandle,
		DisplayName:    creatorDN,
		AvatarUrl:      creatorAV,
		AvatarAssetId:  creatorAssetID,
		AvatarVersion:  int64(creatorAvatarVersion),
		MemberType:     "user",
		Role:           "owner",
		JoinedAt:       now,
	}
	initialMembers := make([]*model.ConversationMember, 0, len(initialMemberIds))
	for i, userID := range initialMemberIds {
		userHandle, dn, av, assetID, avatarVersion := lookup(userID)
		initialMembers = append(initialMembers, &model.ConversationMember{
			ID:             generateID(),
			ConversationId: conv.ID,
			UserId:         userID,
			UserHandle:     userHandle,
			DisplayName:    dn,
			AvatarUrl:      av,
			AvatarAssetId:  assetID,
			AvatarVersion:  int64(avatarVersion),
			MemberType:     "user",
			Role:           "member",
			InvitedBy:      req.CreatorId,
			JoinedAt:       now.Add(time.Duration(i+1) * time.Millisecond),
		})
	}
	creatorState := &model.ConversationUserState{
		ID:             generateID(),
		UserId:         req.CreatorId,
		ConversationId: conv.ID,
		UpdatedAt:      now,
	}
	initialStates := make([]*model.ConversationUserState, 0, len(initialMemberIds))
	for _, userID := range initialMemberIds {
		initialStates = append(initialStates, &model.ConversationUserState{
			ID:             generateID(),
			UserId:         userID,
			ConversationId: conv.ID,
			UpdatedAt:      now,
		})
	}

	conv.MemberCount = len(initialMemberIds) + 1
	conv.MembersRosterRevision = 1
	conv.UpdatedAt = time.Now()
	eventSeed := conv.ID
	if receiptSpec != nil {
		eventSeed = receiptSpec.ScopedKey
	}
	outboxEvents := []AggregateOutboxEvent{
		{
			EventID:        chatAggregateEventID(eventSeed, string(conversationevent.ConversationCreated)),
			EventType:      string(conversationevent.ConversationCreated),
			AggregateID:    conv.ID,
			ConversationID: conv.ID,
			ActorID:        req.CreatorId,
			Payload: map[string]any{
				"conversationId":         conv.ID,
				"type":                   conv.Type,
				"creatorId":              req.CreatorId,
				"circleId":               conv.CircleId,
				"circleGroupId":          conv.CircleGroupId,
				"gatheringId":            conv.GatheringId,
				"gatheringSourceVersion": conv.GatheringSourceVersion,
				"gatheringSourceEventId": conv.GatheringSourceEventID,
				"accessMode":             conv.AccessMode,
				"postingPolicy":          conv.PostingPolicy,
				"entityId":               conv.EntityId,
				"originType":             conv.OriginType,
				"maxGroupSize":           conv.MaxGroupSize,
				"receiptEnabled":         conv.ReceiptEnabled,
				"createdAt":              conv.CreatedAt,
			},
		},
		{
			EventID:        chatAggregateEventID(eventSeed, string(conversationevent.ConversationRosterUpdated)),
			EventType:      string(conversationevent.ConversationRosterUpdated),
			AggregateID:    conv.ID,
			ConversationID: conv.ID,
			ActorID:        req.CreatorId,
			Payload: map[string]any{
				"membersRosterRevision": conv.MembersRosterRevision,
				"updatedAt":             conv.UpdatedAt,
				"aspects":               []string{"members", "created"},
			},
		},
	}
	if conv.CircleGroupId != "" {
		outboxEvents = append(outboxEvents, AggregateOutboxEvent{
			EventID:        chatAggregateEventID(eventSeed, string(conversationevent.CircleGroupConversationProvisioned)),
			EventType:      string(conversationevent.CircleGroupConversationProvisioned),
			AggregateID:    conv.ID,
			ConversationID: conv.ID,
			ActorID:        req.CreatorId,
			Payload: map[string]any{
				"conversationId":      conv.ID,
				"circleId":            conv.CircleId,
				"circleGroupId":       conv.CircleGroupId,
				"creatorId":           conv.CreatorId,
				"sourceCircleEventId": req.CircleGroupSourceEventID,
				"createdAt":           conv.CreatedAt.UTC(),
			},
		})
	}
	if err := s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		if err := s.conversations.CreateConversation(txCtx, conv); err != nil {
			return err
		}
		if err := s.members.CreateMember(txCtx, creator); err != nil {
			return err
		}
		for _, member := range initialMembers {
			if err := s.members.CreateMember(txCtx, member); err != nil {
				return err
			}
		}
		if err := s.conversations.UpdateConversation(txCtx, conv.ID, conv); err != nil {
			return err
		}
		if err := s.userStates.UpsertUserState(txCtx, creatorState); err != nil {
			return err
		}
		for _, state := range initialStates {
			if err := s.userStates.UpsertUserState(txCtx, state); err != nil {
				return err
			}
		}
		if receiptSpec != nil {
			receipt, receiptErr := chatCommandReceipt(
				receiptSpec.ScopedKey,
				receiptSpec.CommandName,
				receiptSpec.CommandDigest,
				conv.ID,
				conv,
			)
			if receiptErr != nil {
				return receiptErr
			}
			if commitErr := s.conversationCommands.CommitAggregateCommand(
				txCtx, receipt, outboxEvents,
			); commitErr != nil {
				if receiptSpec.CommandName == "CreateConversation" &&
					errors.Is(commitErr, ErrAggregateIdempotencyKeyTaken) {
					return commitErr
				}
				return mapChatIdempotencyError(commitErr)
			}
		} else if err := s.conversationCommands.AppendAggregateOutboxEvents(
			txCtx, outboxEvents,
		); err != nil {
			return err
		}
		if IsGroupConversation(*conv) {
			return s.scheduler.EnqueueRecompute(txCtx, GroupAvatarRecomputeTask{
				ConversationID: conv.ID,
				ActorID:        req.CreatorId,
				Trigger:        "conversation.created",
			})
		}
		return nil
	}); err != nil {
		if errors.Is(err, model.ErrCircleGroupConversationAlreadyBound) &&
			strings.TrimSpace(conv.CircleGroupId) != "" &&
			s.circleGroupConversations != nil {
			existing, findErr := s.circleGroupConversations.FindConversationByCircleGroupID(
				ctx,
				conv.CircleGroupId,
			)
			if findErr == nil {
				if existing.CircleId != conv.CircleId || existing.CreatorId != conv.CreatorId {
					return nil, generated.AppErrorFromCircleGroupBindingConflict(
						"concurrent circle group conversation binding differs from source fact",
					)
				}
				return existing, nil
			}
			if !isConversationNotFound(findErr) {
				return nil, findErr
			}
		}
		if errors.Is(err, model.ErrGatheringConversationAlreadyBound) &&
			strings.TrimSpace(conv.GatheringId) != "" && s.gatheringConversations != nil {
			existing, findErr := s.gatheringConversations.FindConversationByGatheringID(ctx, conv.GatheringId)
			if findErr == nil {
				return s.projectExistingGatheringConversation(ctx, existing, GatheringConversationProvisioningRequest{
					SourceEventID: conv.GatheringSourceEventID, SourceVersion: conv.GatheringSourceVersion,
					GatheringID: conv.GatheringId, OwnerPersonaID: conv.CreatorId, Title: conv.Title,
					AccessMode: conv.AccessMode, PostingPolicy: conv.PostingPolicy,
				})
			}
			if !isConversationNotFound(findErr) {
				return nil, findErr
			}
		}
		return nil, err
	}
	return conv, nil
}

type DissolveConversationRequest struct {
	ConversationId string
	OperatorId     string
}

func (s *ConversationService) DissolveConversation(ctx context.Context, req DissolveConversationRequest) error {
	scopedKey, err := scopedChatIdempotencyKey(ctx, req.OperatorId)
	if err != nil {
		return err
	}
	digest, err := chatCommandDigest("DissolveConversation", req)
	if err != nil {
		return err
	}
	if found, err := replayChatCommand(
		ctx, s.conversationCommands, scopedKey, "DissolveConversation", digest, nil,
	); err != nil || found {
		return err
	}
	conv, err := s.conversations.FindConversationByID(ctx, req.ConversationId)
	if err != nil {
		return err
	}
	if err := rejectSourceManagedConversation(conv, "DissolveConversation"); err != nil {
		return err
	}
	owner, err := s.members.FindMember(ctx, req.ConversationId, req.OperatorId)
	if err != nil || owner.Role != "owner" {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "group_governance_forbidden"),
			"仅群主可解散群聊",
			"only owner can dissolve conversation",
		)
	}
	receipt, err := chatCommandReceipt(scopedKey, "DissolveConversation", digest, conv.ID, nil)
	if err != nil {
		return err
	}
	if conv.Status == model.ConversationStatusDissolved {
		// no-op：已解散，仅持久化回执供相同 key 重放，不再产生事件。
		if err := s.conversationCommands.CommitAggregateCommand(ctx, receipt, nil); err != nil {
			return mapChatIdempotencyError(err)
		}
		return nil
	}
	dissolvedAt := time.Now()
	conv.Status = model.ConversationStatusDissolved
	conv.UpdatedAt = dissolvedAt
	if err := s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		if err := s.conversations.UpdateConversation(txCtx, conv.ID, conv); err != nil {
			return err
		}
		return mapChatIdempotencyError(s.conversationCommands.CommitAggregateCommand(
			txCtx,
			receipt,
			[]AggregateOutboxEvent{{
				EventID:        chatAggregateEventID(scopedKey, string(conversationevent.ConversationDissolved)),
				EventType:      string(conversationevent.ConversationDissolved),
				AggregateID:    conv.ID,
				ConversationID: conv.ID,
				ActorID:        req.OperatorId,
				Payload: map[string]any{
					"conversationId": conv.ID,
					"status":         conv.Status,
					"dissolvedBy":    req.OperatorId,
					"dissolvedAt":    dissolvedAt,
				},
			}},
		))
	}); err != nil {
		return err
	}
	_ = s.cache.InvalidateConversation(ctx, req.ConversationId)
	return nil
}

// isManagedBindingCreateRequest reports whether the create request carries a
// CircleGroup or Gathering source binding. Only the corresponding trusted
// source projector may set these fields; the hand-picked group flow never may.
func isManagedBindingCreateRequest(req CreateConversationRequest) bool {
	return strings.TrimSpace(req.CircleId) != "" || strings.TrimSpace(req.CircleGroupId) != "" ||
		strings.TrimSpace(req.GatheringId) != ""
}

func isConversationNotFound(err error) bool {
	return errors.Is(err, model.ErrConversationNotFound)
}

// validateGroupInitialMembers enforces, server-side, that every hand-picked
// initial member of an ad-hoc group is mutually followed by the creator and is
// not in a block relationship. This mirrors the client candidate surfaces
// (which only expose mutual contacts) so a forged request cannot inject
// non-mutual or blocked members into a new group.
func (s *ConversationService) validateGroupInitialMembers(ctx context.Context, creatorID string, memberIDs []string) error {
	for _, memberID := range memberIDs {
		capability, err := s.relationships.GetCapability(ctx, creatorID, memberID)
		if err != nil {
			return err
		}
		if capability.IsBlocked || capability.IsBlockedBy {
			return chatGroupMemberBlocked("group conversation member blocked by relationship gate")
		}
		if !capability.IsMutual {
			return chatGroupMemberNotMutual("group conversation requires mutual follow with each invited member")
		}
	}
	return nil
}

func dedupeUserIDs(ids []string, exclude ...string) []string {
	excluded := make(map[string]struct{}, len(exclude))
	for _, id := range exclude {
		trimmed := strings.TrimSpace(id)
		if trimmed != "" {
			excluded[trimmed] = struct{}{}
		}
	}
	seen := make(map[string]struct{}, len(ids))
	out := make([]string, 0, len(ids))
	for _, id := range ids {
		trimmed := strings.TrimSpace(id)
		if trimmed == "" {
			continue
		}
		if _, ok := excluded[trimmed]; ok {
			continue
		}
		if _, ok := seen[trimmed]; ok {
			continue
		}
		seen[trimmed] = struct{}{}
		out = append(out, trimmed)
	}
	return out
}

func defaultString(value string, fallback string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return fallback
	}
	return trimmed
}

func inferGroupConversationOrigin(
	req CreateConversationRequest,
	originType string,
) string {
	hasCircleGroup := strings.TrimSpace(req.CircleGroupId) != ""
	hasCircle := strings.TrimSpace(req.CircleId) != ""
	if strings.TrimSpace(req.GatheringId) != "" {
		return "gathering"
	}
	if hasCircleGroup || hasCircle {
		if originType == "direct_init" {
			originType = "circle_group"
		}
		return originType
	}
	if originType == "direct_init" {
		originType = "ad_hoc_group"
	}
	return originType
}
