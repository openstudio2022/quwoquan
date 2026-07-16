package application

import (
	"context"
	"strings"
	"time"

	"github.com/google/uuid"

	relports "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/ports"
	userevent "quwoquan_service/services/user-service/internal/domain/user/event"
	usermodel "quwoquan_service/services/user-service/internal/domain/user/model"
	greetingrepo "quwoquan_service/services/user-service/internal/domain/user/ports"
	"quwoquan_service/services/user-service/internal/generated"
)

const greetingDefaultTTL = 30 * 24 * time.Hour

type GreetingService struct {
	greetings     greetingrepo.GreetingRequestStore
	relationships relports.RelationshipReader
	conversations ConversationGateway
	events        UserEventPublisher
}

func NewGreetingService(
	greetings greetingrepo.GreetingRequestStore,
	relationships relports.RelationshipReader,
	conversations ConversationGateway,
	events UserEventPublisher,
) *GreetingService {
	conversations = requireConversationGateway(conversations)
	events = requireUserEventPublisher(events)
	return &GreetingService{
		greetings:     greetings,
		relationships: relationships,
		conversations: conversations,
		events:        events,
	}
}

type SendGreetingRequest struct {
	RequesterSubAccountID string
	TargetSubAccountID    string
	RequestMessage        string
	Source                string
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
		Status:                "pending",
		Source:                source,
		ExpireAt:              &expireAt,
	}

	if err := s.greetings.Create(ctx, greeting); err != nil {
		return nil, err
	}

	_ = s.events.PublishUserEvent(ctx, userevent.GreetingRequestSent, targetID, requesterID, map[string]any{
		"id":                    greeting.ID,
		"requesterSubAccountId": requesterID,
		"targetSubAccountId":    targetID,
		"source":                source,
		"expireAt":              expireAt.Format(time.RFC3339),
	})
	return greeting, nil
}

func (s *GreetingService) ListInbox(ctx context.Context, targetID, status, cursor string, limit int) ([]usermodel.GreetingRequest, string, error) {
	return s.greetings.ListInbox(ctx, targetID, status, cursor, limit)
}

func (s *GreetingService) ListOutbox(ctx context.Context, requesterID, status, cursor string, limit int) ([]usermodel.GreetingRequest, string, error) {
	return s.greetings.ListOutbox(ctx, requesterID, status, cursor, limit)
}

func (s *GreetingService) Reply(ctx context.Context, actorID, requestID string) (*usermodel.GreetingRequest, error) {
	greeting, err := s.loadAuthorizedGreeting(ctx, actorID, requestID)
	if err != nil {
		return nil, err
	}
	if greeting.Status != "pending" {
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
	greeting.Status = "replied"
	greeting.PromotedConversationID = conversationID
	greeting.DecisionAt = &now
	if err := s.greetings.Update(ctx, greeting); err != nil {
		return nil, err
	}

	_ = s.events.PublishUserEvent(ctx, userevent.GreetingRequestReplied, greeting.RequesterSubAccountID, greeting.TargetSubAccountID, map[string]any{
		"id":                     greeting.ID,
		"requesterSubAccountId":  greeting.RequesterSubAccountID,
		"targetSubAccountId":     greeting.TargetSubAccountID,
		"promotedConversationId": conversationID,
	})
	return greeting, nil
}

func (s *GreetingService) Ignore(ctx context.Context, actorID, requestID string) (*usermodel.GreetingRequest, error) {
	greeting, err := s.loadAuthorizedGreeting(ctx, actorID, requestID)
	if err != nil {
		return nil, err
	}
	if greeting.Status != "pending" {
		return nil, generated.AppErrorFromGreetingInvalidStatusTransition("only pending greeting can be ignored")
	}
	now := time.Now().UTC()
	greeting.Status = "ignored"
	greeting.DecisionAt = &now
	if err := s.greetings.Update(ctx, greeting); err != nil {
		return nil, err
	}
	_ = s.events.PublishUserEvent(ctx, userevent.GreetingRequestIgnored, greeting.RequesterSubAccountID, greeting.TargetSubAccountID, map[string]any{
		"id":                    greeting.ID,
		"requesterSubAccountId": greeting.RequesterSubAccountID,
		"targetSubAccountId":    greeting.TargetSubAccountID,
		"decisionAt":            now.Format(time.RFC3339),
	})
	return greeting, nil
}

func (s *GreetingService) Cancel(ctx context.Context, actorID, requestID string) (*usermodel.GreetingRequest, error) {
	greeting, err := s.greetings.FindByID(ctx, requestID)
	if err != nil {
		return nil, err
	}
	if greeting == nil || greeting.RequesterSubAccountID != actorID {
		return nil, generated.AppErrorFromGreetingNotFound("greeting request not found or access denied")
	}
	if greeting.Status != "pending" {
		return nil, generated.AppErrorFromGreetingInvalidStatusTransition("only pending greeting can be cancelled")
	}
	greeting.Status = "cancelled"
	if err := s.greetings.Update(ctx, greeting); err != nil {
		return nil, err
	}
	_ = s.events.PublishUserEvent(ctx, userevent.GreetingRequestCancelled, greeting.TargetSubAccountID, greeting.RequesterSubAccountID, map[string]any{
		"id":                    greeting.ID,
		"requesterSubAccountId": greeting.RequesterSubAccountID,
		"targetSubAccountId":    greeting.TargetSubAccountID,
	})
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
