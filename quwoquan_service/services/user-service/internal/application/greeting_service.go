package application

import (
	"context"
	"log/slog"
	"strings"
	"time"

	"github.com/google/uuid"

	settingsports "quwoquan_service/services/user-service/internal/domain/account/user_settings/ports"
	relports "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/ports"
	userevent "quwoquan_service/services/user-service/internal/domain/user/event"
	usermodel "quwoquan_service/services/user-service/internal/domain/user/model"
	greetingrepo "quwoquan_service/services/user-service/internal/domain/user/ports"
	"quwoquan_service/services/user-service/internal/generated"
)

const greetingDefaultTTL = 30 * 24 * time.Hour

// GreetingStreamEvent 是 GreetingRequest 的 durable 跨上下文事件，payload
// 自包含通知接收者与投递条件（targetAllowsStrangerGreeting），消费者不得
// 跨服务反查写模型。
type GreetingStreamEvent struct {
	EventID                      string
	EventName                    string
	GreetingID                   string
	RequesterSubAccountID        string
	TargetSubAccountID           string
	Source                       string
	PromotedConversationID       string
	TargetAllowsStrangerGreeting bool
	OccurredAt                   time.Time
}

// GreetingEventStream 是 GreetingRequest 事件的 durable 投递端口
// （Redis Stream at-least-once，消费者按 eventId 去重）。
type GreetingEventStream interface {
	PublishGreetingEvent(ctx context.Context, event GreetingStreamEvent) error
}

// greetingNotifyPolicyReader 只读取影响打招呼通知的隐私设置位。
type greetingNotifyPolicyReader interface {
	AllowsStrangerGreeting(ctx context.Context, subAccountID string) (bool, error)
}

// SettingsGreetingNotifyPolicy 从 UserSettings 派生打招呼通知条件
// （side_effects: targetUser.allowStrangerGreeting）。缺省设置视为允许。
type SettingsGreetingNotifyPolicy struct {
	settings settingsports.SnapshotReader
	personas greetingrepo.PersonaReader
}

func NewSettingsGreetingNotifyPolicy(
	settings settingsports.SnapshotReader,
	personas greetingrepo.PersonaReader,
) *SettingsGreetingNotifyPolicy {
	if settings == nil || personas == nil {
		panic("greeting notify policy requires UserSettings and Persona readers")
	}
	return &SettingsGreetingNotifyPolicy{
		settings: settings,
		personas: personas,
	}
}

func (p *SettingsGreetingNotifyPolicy) AllowsStrangerGreeting(
	ctx context.Context,
	subAccountID string,
) (bool, error) {
	persona, err := p.personas.FindBySubAccountID(
		ctx,
		strings.TrimSpace(subAccountID),
	)
	if err != nil {
		return false, err
	}
	if persona == nil {
		return true, nil
	}
	setting, found, err := p.settings.ReadUserSettingsSnapshot(
		ctx,
		strings.TrimSpace(persona.UserID),
	)
	if err != nil {
		return false, err
	}
	if !found {
		return true, nil
	}
	return setting.Privacy.AllowStrangerMsg, nil
}

// greetingDailyQuota 是 24h 窗口内单个发起者的打招呼上限
// （USER.GREETING.rate_limited 的触发阈值）。
const greetingDailyQuota = 20

type GreetingService struct {
	greetings     greetingrepo.GreetingRequestStore
	commands      greetingrepo.GreetingCommandStore
	relationships relports.RelationshipReader
	conversations ConversationGateway
	events        UserEventPublisher
	stream        GreetingEventStream
	notifyPolicy  greetingNotifyPolicyReader
}

func NewGreetingService(
	greetings greetingrepo.GreetingRequestStore,
	commands greetingrepo.GreetingCommandStore,
	relationships relports.RelationshipReader,
	conversations ConversationGateway,
	events UserEventPublisher,
	stream GreetingEventStream,
	notifyPolicy greetingNotifyPolicyReader,
) *GreetingService {
	conversations = requireConversationGateway(conversations)
	events = requireUserEventPublisher(events)
	if commands == nil {
		panic("greeting application requires GreetingCommandStore")
	}
	if stream == nil {
		panic("greeting application requires GreetingEventStream")
	}
	if notifyPolicy == nil {
		panic("greeting application requires greeting notify policy reader")
	}
	return &GreetingService{
		greetings:     greetings,
		commands:      commands,
		relationships: relationships,
		conversations: conversations,
		events:        events,
		stream:        stream,
		notifyPolicy:  notifyPolicy,
	}
}

type SendGreetingRequest struct {
	RequesterSubAccountID string
	TargetSubAccountID    string
	RequestMessage        string
	Source                string
	IdempotencyKey        string
}

func (s *GreetingService) Send(ctx context.Context, req SendGreetingRequest) (*usermodel.GreetingRequest, error) {
	requesterID := strings.TrimSpace(req.RequesterSubAccountID)
	targetID := strings.TrimSpace(req.TargetSubAccountID)
	if requesterID == "" || targetID == "" {
		return nil, generated.AppErrorFromInvalidArgument("requesterSubAccountId and targetSubAccountId required")
	}
	if requesterID == targetID {
		return nil, generated.AppErrorFromInvalidArgument("cannot greet self")
	}
	idempotencyKey := strings.TrimSpace(req.IdempotencyKey)
	if idempotencyKey != "" {
		if replayed, found, err := s.commands.LoadCommandReceipt(
			ctx, requesterID, idempotencyKey, "SendGreetingRequest",
		); err != nil {
			return nil, err
		} else if found {
			return replayed, nil
		}
	}
	if blocked, err := s.isBlockedEitherWay(ctx, requesterID, targetID); err != nil {
		return nil, err
	} else if blocked {
		return nil, generated.AppErrorFromGreetingTargetBlockedSender("send greeting blocked by relationship gate")
	}
	if mutual, err := s.isMutual(ctx, requesterID, targetID); err != nil {
		return nil, err
	} else if mutual {
		return nil, generated.AppErrorFromGreetingAlreadyContact("requester and target are mutual followers")
	}
	if recent, err := s.commands.CountRecentByRequester(ctx, requesterID, 24*time.Hour); err != nil {
		return nil, err
	} else if recent >= greetingDailyQuota {
		return nil, generated.AppErrorFromGreetingRateLimited("sender exceeded daily greeting quota")
	}
	if pending, err := s.greetings.FindPendingBetween(ctx, requesterID, targetID); err != nil {
		return nil, err
	} else if pending != nil {
		return nil, generated.AppErrorFromGreetingDuplicatePending("pending greeting already exists")
	}

	now := time.Now().UTC()
	expireAt := now.Add(greetingDefaultTTL)
	source := normalizeGreetingSource(req.Source)
	greeting := &usermodel.GreetingRequest{
		ID:                    uuid.New().String(),
		RequesterSubAccountID: requesterID,
		TargetSubAccountID:    targetID,
		RequestMessage:        strings.TrimSpace(req.RequestMessage),
		Status:                usermodel.GreetingStatusPending,
		Source:                source,
		ExpireAt:              &expireAt,
	}

	allowsGreeting, policyErr := s.notifyPolicy.AllowsStrangerGreeting(ctx, targetID)
	if policyErr != nil {
		slog.ErrorContext(ctx, "greeting notify policy read failed; defaulting to notify",
			slog.String("greetingId", greeting.ID),
			slog.String("error", policyErr.Error()),
		)
		allowsGreeting = true
	}
	if err := s.commands.CommitCommand(ctx, greetingrepo.GreetingCommit{
		Greeting:          greeting,
		Insert:            true,
		ActorSubAccountID: requesterID,
		IdempotencyKey:    idempotencyKey,
		Operation:         "SendGreetingRequest",
		EventID:           "greeting:" + greeting.ID + ":" + userevent.GreetingRequestSent,
		EventName:         userevent.GreetingRequestSent,
		EventPayload: map[string]any{
			"id":                           greeting.ID,
			"requesterSubAccountId":        requesterID,
			"targetSubAccountId":           targetID,
			"source":                       source,
			"expireAt":                     expireAt.Format(time.RFC3339),
			"targetAllowsStrangerGreeting": allowsGreeting,
		},
		OccurredAt: now,
	}); err != nil {
		return nil, err
	}
	return greeting, nil
}

func (s *GreetingService) ListInbox(ctx context.Context, targetID, status, cursor string, limit int) ([]usermodel.GreetingRequest, string, error) {
	return s.greetings.ListInbox(ctx, targetID, status, cursor, limit)
}

func (s *GreetingService) ListOutbox(ctx context.Context, requesterID, status, cursor string, limit int) ([]usermodel.GreetingRequest, string, error) {
	return s.greetings.ListOutbox(ctx, requesterID, status, cursor, limit)
}

func (s *GreetingService) Reply(ctx context.Context, actorID, requestID, idempotencyKey string) (*usermodel.GreetingRequest, error) {
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if idempotencyKey != "" {
		if replayed, found, err := s.commands.LoadCommandReceipt(
			ctx, actorID, idempotencyKey, "ReplyGreetingRequest",
		); err != nil {
			return nil, err
		} else if found {
			return replayed, nil
		}
	}
	greeting, err := s.loadAuthorizedGreeting(ctx, actorID, requestID)
	if err != nil {
		return nil, err
	}
	if greeting.Status != usermodel.GreetingStatusPending {
		return nil, generated.AppErrorFromGreetingInvalidStatusTransition("only pending greeting can be replied")
	}
	if blocked, err := s.isBlockedEitherWay(ctx, greeting.RequesterSubAccountID, greeting.TargetSubAccountID); err != nil {
		return nil, err
	} else if blocked {
		return nil, generated.AppErrorFromGreetingTargetBlockedSender("reply blocked by relationship gate")
	}

	conversationID, err := s.conversations.CreateOrReuseDirect(
		ctx,
		greeting.TargetSubAccountID,
		greeting.RequesterSubAccountID,
	)
	if err != nil {
		return nil, err
	}

	now := time.Now().UTC()
	greeting.Status = usermodel.GreetingStatusReplied
	greeting.PromotedConversationID = conversationID
	greeting.DecisionAt = &now
	if err := s.commands.CommitCommand(ctx, greetingrepo.GreetingCommit{
		Greeting:          greeting,
		ActorSubAccountID: actorID,
		IdempotencyKey:    idempotencyKey,
		Operation:         "ReplyGreetingRequest",
		EventID:           "greeting:" + greeting.ID + ":" + userevent.GreetingRequestReplied,
		EventName:         userevent.GreetingRequestReplied,
		EventPayload: map[string]any{
			"id":                           greeting.ID,
			"requesterSubAccountId":        greeting.RequesterSubAccountID,
			"targetSubAccountId":           greeting.TargetSubAccountID,
			"promotedConversationId":       conversationID,
			"targetAllowsStrangerGreeting": true,
		},
		OccurredAt: now,
	}); err != nil {
		return nil, err
	}
	return greeting, nil
}

func (s *GreetingService) Ignore(ctx context.Context, actorID, requestID, idempotencyKey string) (*usermodel.GreetingRequest, error) {
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if idempotencyKey != "" {
		if replayed, found, err := s.commands.LoadCommandReceipt(
			ctx, actorID, idempotencyKey, "IgnoreGreetingRequest",
		); err != nil {
			return nil, err
		} else if found {
			return replayed, nil
		}
	}
	greeting, err := s.loadAuthorizedGreeting(ctx, actorID, requestID)
	if err != nil {
		return nil, err
	}
	if greeting.Status != usermodel.GreetingStatusPending {
		return nil, generated.AppErrorFromGreetingInvalidStatusTransition("only pending greeting can be ignored")
	}
	now := time.Now().UTC()
	greeting.Status = usermodel.GreetingStatusIgnored
	greeting.DecisionAt = &now
	if err := s.commands.CommitCommand(ctx, greetingrepo.GreetingCommit{
		Greeting:          greeting,
		ActorSubAccountID: actorID,
		IdempotencyKey:    idempotencyKey,
		Operation:         "IgnoreGreetingRequest",
		EventID:           "greeting:" + greeting.ID + ":" + userevent.GreetingRequestIgnored,
		EventName:         userevent.GreetingRequestIgnored,
		EventPayload: map[string]any{
			"id":                           greeting.ID,
			"requesterSubAccountId":        greeting.RequesterSubAccountID,
			"targetSubAccountId":           greeting.TargetSubAccountID,
			"decisionAt":                   now.Format(time.RFC3339),
			"targetAllowsStrangerGreeting": true,
		},
		OccurredAt: now,
	}); err != nil {
		return nil, err
	}
	return greeting, nil
}

func (s *GreetingService) Cancel(ctx context.Context, actorID, requestID, idempotencyKey string) (*usermodel.GreetingRequest, error) {
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if idempotencyKey != "" {
		if replayed, found, err := s.commands.LoadCommandReceipt(
			ctx, actorID, idempotencyKey, "CancelGreetingRequest",
		); err != nil {
			return nil, err
		} else if found {
			return replayed, nil
		}
	}
	greeting, err := s.greetings.FindByID(ctx, requestID)
	if err != nil {
		return nil, err
	}
	if greeting == nil || greeting.RequesterSubAccountID != actorID {
		return nil, generated.AppErrorFromGreetingNotFound("greeting request not found or access denied")
	}
	if greeting.Status != usermodel.GreetingStatusPending {
		return nil, generated.AppErrorFromGreetingInvalidStatusTransition("only pending greeting can be cancelled")
	}
	now := time.Now().UTC()
	greeting.Status = usermodel.GreetingStatusCancelled
	greeting.DecisionAt = &now
	if err := s.commands.CommitCommand(ctx, greetingrepo.GreetingCommit{
		Greeting:          greeting,
		ActorSubAccountID: actorID,
		IdempotencyKey:    idempotencyKey,
		Operation:         "CancelGreetingRequest",
		EventID:           "greeting:" + greeting.ID + ":" + userevent.GreetingRequestCancelled,
		EventName:         userevent.GreetingRequestCancelled,
		EventPayload: map[string]any{
			"id":                           greeting.ID,
			"requesterSubAccountId":        greeting.RequesterSubAccountID,
			"targetSubAccountId":           greeting.TargetSubAccountID,
			"targetAllowsStrangerGreeting": true,
		},
		OccurredAt: now,
	}); err != nil {
		return nil, err
	}
	return greeting, nil
}

func (s *GreetingService) HasPendingBetween(ctx context.Context, subAccountA, subAccountB string) (bool, error) {
	return s.greetings.HasPendingBetween(ctx, subAccountA, subAccountB)
}

func (s *GreetingService) HasFormalConversation(ctx context.Context, subAccountA, subAccountB string) (bool, error) {
	replied, err := s.greetings.HasRepliedBetween(ctx, subAccountA, subAccountB)
	if err != nil {
		return false, err
	}
	if replied {
		return true, nil
	}
	return s.conversations.HasDirectBetween(ctx, subAccountA, subAccountB)
}

func (s *GreetingService) loadAuthorizedGreeting(ctx context.Context, actorID, requestID string) (*usermodel.GreetingRequest, error) {
	greeting, err := s.greetings.FindByID(ctx, requestID)
	if err != nil {
		return nil, err
	}
	if greeting == nil || greeting.TargetSubAccountID != actorID {
		return nil, generated.AppErrorFromGreetingNotFound("greeting request not found or access denied")
	}
	return greeting, nil
}

func (s *GreetingService) isBlockedEitherWay(ctx context.Context, subAccountA, subAccountB string) (bool, error) {
	if s.relationships == nil {
		return false, nil
	}
	relationship, err := s.relationships.GetRelationship(ctx, subAccountA, subAccountB)
	if err != nil {
		return false, err
	}
	return relationship.IsBlocked || relationship.IsBlockedBy, nil
}

func (s *GreetingService) isMutual(ctx context.Context, subAccountA, subAccountB string) (bool, error) {
	if s.relationships == nil {
		return false, nil
	}
	relationship, err := s.relationships.GetRelationship(ctx, subAccountA, subAccountB)
	if err != nil {
		return false, err
	}
	return relationship.IsMutual, nil
}

func normalizeGreetingSource(source string) string {
	source = strings.TrimSpace(source)
	switch source {
	case "profile", "recommendation", "group_member", "invite":
		return source
	default:
		return "profile"
	}
}
