package application

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	generated "quwoquan_service/services/chat-service/generated/chat/conversation"
	conversationevent "quwoquan_service/services/chat-service/generated/chat/conversation/contract/event"
	membershipevent "quwoquan_service/services/chat-service/generated/chat/conversation_membership/contract/event"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

const (
	circleGroupEventCreated  = "CircleGroupCreated"
	circleGroupEventArchived = "CircleGroupArchived"

	circleGroupMembershipEventActivated   = "CircleGroupMembershipActivated"
	circleGroupMembershipEventLeft        = "CircleGroupMembershipLeft"
	circleGroupMembershipEventRemoved     = "CircleGroupMembershipRemoved"
	circleGroupMembershipEventRoleChanged = "CircleGroupMembershipRoleChanged"

	circleGroupBindingStatusActive   = "active"
	circleGroupBindingStatusArchived = "archived"
)

// CircleGroupChatSourceEvent is the normalized, trusted payload read from the
// Circle transactional-outbox Redis Streams. It deliberately is not a public
// HTTP DTO.
type CircleGroupChatSourceEvent struct {
	EventID    string
	EventType  string
	GroupID    string
	CircleID   string
	Version    int64
	Name       string
	OwnerID    string
	UserID     string
	Role       string
	State      string
	OccurredAt time.Time
}

// CircleGroupChatSyncService is the application boundary for the two Circle
// source streams. CircleGroup remains the write authority; this service only
// creates and updates the Chat-side projection.
type CircleGroupChatSyncService struct {
	conversations *ConversationService
	members       *MemberService
}

// CircleGroupChatSyncProjector is the adapter-facing application port. It
// keeps Redis consumer tests and transport composition independent from the
// concrete orchestration service.
type CircleGroupChatSyncProjector interface {
	Apply(context.Context, CircleGroupChatSourceEvent) error
}

func NewCircleGroupChatSyncService(
	conversations *ConversationService,
	members *MemberService,
) *CircleGroupChatSyncService {
	return &CircleGroupChatSyncService{
		conversations: conversations,
		members:       members,
	}
}

func (s *CircleGroupChatSyncService) Apply(
	ctx context.Context,
	event CircleGroupChatSourceEvent,
) error {
	if s == nil || s.conversations == nil || s.members == nil {
		return errors.New("circle group chat sync service is not configured")
	}
	event = normalizeCircleGroupChatSourceEvent(event)
	if err := validateCircleGroupChatSourceEvent(event); err != nil {
		return err
	}
	switch event.EventType {
	case circleGroupEventCreated:
		return s.conversations.projectCircleGroupCreated(ctx, event)
	case circleGroupEventArchived:
		return s.conversations.projectCircleGroupArchived(ctx, event)
	case circleGroupMembershipEventActivated,
		circleGroupMembershipEventLeft,
		circleGroupMembershipEventRemoved,
		circleGroupMembershipEventRoleChanged:
		return s.members.projectCircleGroupMembership(ctx, event)
	default:
		return fmt.Errorf("unsupported circle group source event %q", event.EventType)
	}
}

func normalizeCircleGroupChatSourceEvent(event CircleGroupChatSourceEvent) CircleGroupChatSourceEvent {
	event.EventID = strings.TrimSpace(event.EventID)
	event.EventType = strings.TrimSpace(event.EventType)
	event.GroupID = strings.TrimSpace(event.GroupID)
	event.CircleID = strings.TrimSpace(event.CircleID)
	event.Name = strings.TrimSpace(event.Name)
	event.OwnerID = strings.TrimSpace(event.OwnerID)
	event.UserID = strings.TrimSpace(event.UserID)
	event.Role = strings.TrimSpace(event.Role)
	event.State = strings.TrimSpace(event.State)
	return event
}

func validateCircleGroupChatSourceEvent(event CircleGroupChatSourceEvent) error {
	if event.EventID == "" || event.EventType == "" || event.GroupID == "" ||
		event.CircleID == "" || event.Version <= 0 {
		return fmt.Errorf("circle group source event identity is incomplete")
	}
	switch event.EventType {
	case circleGroupEventCreated:
		if event.Name == "" || event.OwnerID == "" {
			return fmt.Errorf("CircleGroupCreated payload is incomplete")
		}
	case circleGroupEventArchived:
		// group/circle/version suffice; a late archive must still prevent create.
	case circleGroupMembershipEventActivated, circleGroupMembershipEventRoleChanged:
		if event.UserID == "" || event.Role == "" || event.State != "active" {
			return fmt.Errorf("%s payload must contain an active user and role", event.EventType)
		}
	case circleGroupMembershipEventLeft:
		if event.UserID == "" || event.State != "left" {
			return fmt.Errorf("CircleGroupMembershipLeft payload must contain left user")
		}
	case circleGroupMembershipEventRemoved:
		if event.UserID == "" || event.State != "removed" {
			return fmt.Errorf("CircleGroupMembershipRemoved payload must contain removed user")
		}
	default:
		return fmt.Errorf("unsupported circle group source event %q", event.EventType)
	}
	return nil
}

func (s *ConversationService) projectCircleGroupCreated(
	ctx context.Context,
	event CircleGroupChatSourceEvent,
) error {
	if s.circleGroupChatBindingProjections == nil {
		return errors.New("circle group binding projection store is not configured")
	}
	current, found, err := s.circleGroupChatBindingProjections.LoadCircleGroupChatBindingProjection(
		ctx,
		event.GroupID,
	)
	if err != nil {
		return err
	}
	if found {
		if current.CircleID != "" && current.CircleID != event.CircleID {
			return generated.AppErrorFromCircleGroupBindingConflict(
				"CircleGroupCreated circleId differs from persisted binding projection",
			)
		}
		if current.SourceVersion > event.Version {
			return nil
		}
		if current.SourceVersion == event.Version {
			if current.LastEventID != event.EventID {
				return generated.AppErrorFromCircleGroupBindingConflict(
					"CircleGroupCreated version is reused by a different source event",
				)
			}
			return nil
		}
		if current.Status == circleGroupBindingStatusArchived {
			// An archive wins over any delayed/replayed create, even if an
			// unexpected source version was emitted later.
			return nil
		}
	}
	_, err = s.ProvisionCircleGroupConversation(ctx, CircleGroupConversationProvisioningRequest{
		SourceEventID:  event.EventID,
		CircleID:       event.CircleID,
		CircleGroupID:  event.GroupID,
		OwnerPersonaID: event.OwnerID,
		Title:          event.Name,
	})
	if err != nil {
		return err
	}
	return s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		latest, exists, loadErr := s.circleGroupChatBindingProjections.LoadCircleGroupChatBindingProjection(
			txCtx,
			event.GroupID,
		)
		if loadErr != nil {
			return loadErr
		}
		if exists && (latest.Status == circleGroupBindingStatusArchived ||
			latest.SourceVersion > event.Version) {
			return nil
		}
		return s.circleGroupChatBindingProjections.SaveCircleGroupChatBindingProjection(
			txCtx,
			CircleGroupChatBindingProjectionState{
				CircleGroupID: event.GroupID,
				CircleID:      event.CircleID,
				SourceVersion: event.Version,
				Status:        circleGroupBindingStatusActive,
				LastEventID:   event.EventID,
				UpdatedAt:     sourceEventTime(event),
			},
		)
	})
}

func (s *ConversationService) projectCircleGroupArchived(
	ctx context.Context,
	event CircleGroupChatSourceEvent,
) error {
	if s.circleGroupChatBindingProjections == nil || s.circleGroupConversations == nil {
		return errors.New("circle group archive projection dependencies are not configured")
	}
	return s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		current, found, err := s.circleGroupChatBindingProjections.LoadCircleGroupChatBindingProjection(
			txCtx,
			event.GroupID,
		)
		if err != nil {
			return err
		}
		if found {
			if current.CircleID != "" && current.CircleID != event.CircleID {
				return generated.AppErrorFromCircleGroupBindingConflict(
					"CircleGroupArchived circleId differs from persisted binding projection",
				)
			}
			if current.SourceVersion > event.Version {
				return nil
			}
			if current.SourceVersion == event.Version && current.LastEventID != event.EventID {
				return generated.AppErrorFromCircleGroupBindingConflict(
					"CircleGroupArchived version is reused by a different source event",
				)
			}
		}
		if err := s.circleGroupChatBindingProjections.SaveCircleGroupChatBindingProjection(
			txCtx,
			CircleGroupChatBindingProjectionState{
				CircleGroupID: event.GroupID,
				CircleID:      event.CircleID,
				SourceVersion: event.Version,
				Status:        circleGroupBindingStatusArchived,
				LastEventID:   event.EventID,
				UpdatedAt:     sourceEventTime(event),
			},
		); err != nil {
			return err
		}
		conv, err := s.circleGroupConversations.FindConversationByCircleGroupID(txCtx, event.GroupID)
		if isConversationNotFound(err) {
			return nil
		}
		if err != nil {
			return err
		}
		if conv.CircleId != event.CircleID {
			return generated.AppErrorFromCircleGroupBindingConflict(
				"CircleGroupArchived found a conversation with a different circleId",
			)
		}
		if conv.Status == model.ConversationStatusDissolved {
			return nil
		}
		members, err := s.members.ListMembers(txCtx, conv.ID, ListMembersQuery{
			Limit: maxGroupSizeLimit + 1,
			Sort:  MemberListSortJoinedAsc,
		})
		if err != nil {
			return err
		}
		if len(members) > maxGroupSizeLimit {
			return generated.AppErrorFromCircleGroupBindingConflict(
				"bound conversation contains more members than its declared limit",
			)
		}
		for _, member := range members {
			if err := s.members.DeleteMember(txCtx, conv.ID, member.UserId); err != nil {
				return err
			}
			if err := s.userStates.DeleteUserState(txCtx, member.UserId, conv.ID); err != nil {
				return err
			}
		}
		conv.Status = model.ConversationStatusDissolved
		conv.MemberCount = 0
		conv.MembersRosterRevision++
		conv.UpdatedAt = sourceEventTime(event)
		if err := s.conversations.UpdateConversation(txCtx, conv.ID, conv); err != nil {
			return err
		}
		events := make([]AggregateOutboxEvent, 0, len(members)+2)
		for _, member := range members {
			events = append(events, AggregateOutboxEvent{
				EventID: chatAggregateEventID(
					event.EventID,
					string(membershipevent.ConversationMemberRemoved)+"\x00"+member.UserId,
				),
				EventType:      string(membershipevent.ConversationMemberRemoved),
				AggregateID:    member.ID,
				ConversationID: conv.ID,
				ActorID:        event.OwnerID,
				Payload: map[string]any{
					"memberId":    member.ID,
					"userId":      member.UserId,
					"memberType":  member.MemberType,
					"removedBy":   "circle_group_archived",
					"memberCount": 0,
				},
			})
		}
		events = append(events,
			AggregateOutboxEvent{
				EventID:        chatAggregateEventID(event.EventID, string(conversationevent.ConversationDissolved)),
				EventType:      string(conversationevent.ConversationDissolved),
				AggregateID:    conv.ID,
				ConversationID: conv.ID,
				ActorID:        event.OwnerID,
				Payload: map[string]any{
					"conversationId": conv.ID,
					"status":         conv.Status,
					"dissolvedBy":    "circle_group_archived",
					"dissolvedAt":    conv.UpdatedAt,
				},
			},
			AggregateOutboxEvent{
				EventID:        chatAggregateEventID(event.EventID, string(conversationevent.ConversationRosterUpdated)),
				EventType:      string(conversationevent.ConversationRosterUpdated),
				AggregateID:    conv.ID,
				ConversationID: conv.ID,
				ActorID:        event.OwnerID,
				Payload: map[string]any{
					"membersRosterRevision": conv.MembersRosterRevision,
					"updatedAt":             conv.UpdatedAt,
					"aspects":               []string{"members", "circle_group_archived"},
				},
			},
		)
		return s.conversationCommands.AppendAggregateOutboxEvents(txCtx, events)
	})
}

func (s *MemberService) projectCircleGroupMembership(
	ctx context.Context,
	event CircleGroupChatSourceEvent,
) error {
	if s.circleGroupMembershipProjections == nil || s.circleGroupChatBindingProjections == nil {
		return errors.New("circle group membership projection stores are not configured")
	}
	convReader, ok := s.conversations.(CircleGroupConversationReader)
	if !ok {
		return errors.New("circle group conversation reader is not configured")
	}
	conv, err := convReader.FindConversationByCircleGroupID(ctx, event.GroupID)
	if err != nil {
		return err
	}
	if conv.CircleId != event.CircleID || !IsCircleBoundConversation(*conv) {
		return generated.AppErrorFromCircleGroupBindingConflict(
			"CircleGroupMembership does not match an active CircleGroup-bound conversation",
		)
	}
	if conv.Status != model.ConversationStatusActive {
		// Archive/terminal state wins over a delayed membership message.
		return nil
	}

	profile, _ := s.profiles.ResolveMany(ctx, []string{event.UserID})
	return s.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		binding, bindingFound, bindingErr := s.circleGroupChatBindingProjections.LoadCircleGroupChatBindingProjection(
			txCtx,
			event.GroupID,
		)
		if bindingErr != nil {
			return bindingErr
		}
		if bindingFound && binding.Status == circleGroupBindingStatusArchived {
			return nil
		}
		currentConversation, currentConversationErr := s.conversations.FindConversationByID(txCtx, conv.ID)
		if currentConversationErr != nil {
			return currentConversationErr
		}
		if currentConversation.Status != model.ConversationStatusActive {
			return nil
		}
		current, found, err := s.circleGroupMembershipProjections.LoadCircleGroupMembershipProjection(
			txCtx,
			event.GroupID,
			event.UserID,
		)
		if err != nil {
			return err
		}
		if found {
			if current.ConversationID != conv.ID {
				return generated.AppErrorFromCircleGroupBindingConflict(
					"CircleGroupMembership projection points to a different conversation",
				)
			}
			if current.SourceVersion > event.Version {
				return nil
			}
			if current.SourceVersion == event.Version {
				if current.LastEventID != event.EventID {
					return generated.AppErrorFromCircleGroupBindingConflict(
						"CircleGroupMembership version is reused by a different source event",
					)
				}
				return nil
			}
		}

		changed, events, err := s.applyCircleGroupMembershipFact(
			txCtx,
			*conv,
			event,
			profile[event.UserID],
		)
		if err != nil {
			return err
		}
		if err := s.circleGroupMembershipProjections.SaveCircleGroupMembershipProjection(
			txCtx,
			CircleGroupMembershipProjectionState{
				CircleGroupID:  event.GroupID,
				ConversationID: conv.ID,
				UserID:         event.UserID,
				SourceVersion:  event.Version,
				State:          event.State,
				Role:           event.Role,
				LastEventID:    event.EventID,
				UpdatedAt:      sourceEventTime(event),
			},
		); err != nil {
			return err
		}
		if !changed {
			return nil
		}
		count, err := s.members.CountMembers(txCtx, conv.ID)
		if err != nil {
			return err
		}
		if err := s.members.BumpMembersRosterRevision(txCtx, conv.ID, &count); err != nil {
			return err
		}
		roster, err := s.rosterUpdatedEvent(
			txCtx,
			event.EventID,
			conv.ID,
			"circle_group_projector",
			[]string{"members", "circle_group_projection"},
		)
		if err != nil {
			return err
		}
		events = append(events, roster)
		if err := s.membershipCommands.AppendAggregateOutboxEvents(txCtx, events); err != nil {
			return err
		}
		return s.scheduler.EnqueueRecompute(txCtx, GroupAvatarRecomputeTask{
			ConversationID: conv.ID,
			ActorID:        "circle_group_projector",
			Trigger:        "circle_group_membership.projected",
		})
	})
}

func (s *MemberService) applyCircleGroupMembershipFact(
	ctx context.Context,
	conv model.Conversation,
	event CircleGroupChatSourceEvent,
	profile ProfileSnapshot,
) (bool, []AggregateOutboxEvent, error) {
	switch event.EventType {
	case circleGroupMembershipEventActivated, circleGroupMembershipEventRoleChanged:
		role, err := mapCircleGroupRole(event.Role)
		if err != nil {
			return false, nil, err
		}
		member, findErr := s.members.FindMember(ctx, conv.ID, event.UserID)
		if isMemberNotFound(findErr) {
			userCount, countErr := s.members.CountUserMembers(ctx, conv.ID)
			if countErr != nil {
				return false, nil, countErr
			}
			if userCount >= conv.MaxGroupSize {
				return false, nil, generated.AppErrorFromCircleGroupBindingConflict(
					"CircleGroupMembership active fact exceeds Chat projection capacity",
				)
			}
			member = &model.ConversationMember{
				ID:             generateID(),
				ConversationId: conv.ID,
				UserId:         event.UserID,
				DisplayName:    profile.DisplayName,
				AvatarUrl:      profile.AvatarURL,
				AvatarAssetId:  profile.AvatarAssetID,
				AvatarVersion:  int64(profile.AvatarVersion),
				MemberType:     "user",
				Role:           role,
				InvitedBy:      "circle_group_projector",
				JoinedAt:       sourceEventTime(event),
			}
			if err := s.members.CreateMember(ctx, member); err != nil {
				return false, nil, err
			}
			if err := s.userStates.UpsertUserState(ctx, &model.ConversationUserState{
				ID:             generateID(),
				UserId:         event.UserID,
				ConversationId: conv.ID,
				UpdatedAt:      sourceEventTime(event),
			}); err != nil {
				return false, nil, err
			}
			return true, []AggregateOutboxEvent{{
				EventID: chatAggregateEventID(
					event.EventID,
					string(membershipevent.ConversationMemberAdded)+"\x00"+event.UserID,
				),
				EventType:      string(membershipevent.ConversationMemberAdded),
				AggregateID:    member.ID,
				ConversationID: conv.ID,
				ActorID:        "circle_group_projector",
				Payload: map[string]any{
					"memberId":    member.ID,
					"userId":      member.UserId,
					"displayName": member.DisplayName,
					"memberType":  member.MemberType,
					"role":        member.Role,
					"invitedBy":   member.InvitedBy,
					"joinedAt":    member.JoinedAt,
				},
			}}, nil
		}
		if findErr != nil {
			return false, nil, findErr
		}
		if member.MemberType != "user" {
			return false, nil, generated.AppErrorFromCircleGroupBindingConflict(
				"CircleGroup member conflicts with a non-human Chat member",
			)
		}
		if member.Role == role {
			if _, stateErr := s.userStates.FindUserState(ctx, event.UserID, conv.ID); isUserStateNotFound(stateErr) {
				if err := s.userStates.UpsertUserState(ctx, &model.ConversationUserState{
					ID: generateID(), UserId: event.UserID, ConversationId: conv.ID, UpdatedAt: sourceEventTime(event),
				}); err != nil {
					return false, nil, err
				}
				return true, nil, nil
			} else if stateErr != nil {
				return false, nil, stateErr
			}
			return false, nil, nil
		}
		if err := s.members.UpdateMemberRole(ctx, conv.ID, event.UserID, role); err != nil {
			return false, nil, err
		}
		return true, []AggregateOutboxEvent{{
			EventID: chatAggregateEventID(
				event.EventID,
				string(membershipevent.ConversationMemberRoleChanged)+"\x00"+event.UserID,
			),
			EventType:      string(membershipevent.ConversationMemberRoleChanged),
			AggregateID:    member.ID,
			ConversationID: conv.ID,
			ActorID:        "circle_group_projector",
			Payload: map[string]any{
				"memberId":  member.ID,
				"userId":    event.UserID,
				"role":      role,
				"changedBy": "circle_group_projector",
			},
		}}, nil
	case circleGroupMembershipEventLeft, circleGroupMembershipEventRemoved:
		member, findErr := s.members.FindMember(ctx, conv.ID, event.UserID)
		if findErr != nil && !isMemberNotFound(findErr) {
			return false, nil, findErr
		}
		if member != nil {
			if err := s.members.DeleteMember(ctx, conv.ID, event.UserID); err != nil {
				return false, nil, err
			}
		}
		if err := s.userStates.DeleteUserState(ctx, event.UserID, conv.ID); err != nil {
			return false, nil, err
		}
		eventType := membershipevent.ConversationMemberRemoved
		if event.EventType == circleGroupMembershipEventLeft {
			eventType = membershipevent.ConversationMemberLeft
		}
		memberID := conv.ID
		memberType := "user"
		if member != nil {
			memberID = member.ID
			memberType = member.MemberType
		}
		return true, []AggregateOutboxEvent{{
			EventID:        chatAggregateEventID(event.EventID, string(eventType)+"\x00"+event.UserID),
			EventType:      string(eventType),
			AggregateID:    memberID,
			ConversationID: conv.ID,
			ActorID:        "circle_group_projector",
			Payload: map[string]any{
				"memberId":   memberID,
				"userId":     event.UserID,
				"memberType": memberType,
				"removedBy":  "circle_group_projector",
				"leftAt":     sourceEventTime(event),
			},
		}}, nil
	default:
		return false, nil, fmt.Errorf("unsupported circle group membership event %q", event.EventType)
	}
}

func mapCircleGroupRole(role string) (string, error) {
	switch strings.TrimSpace(role) {
	case "owner":
		return "owner", nil
	case "manager":
		return "admin", nil
	case "member":
		return "member", nil
	default:
		return "", generated.AppErrorFromCircleGroupBindingConflict(
			"unsupported CircleGroupMembership role " + strings.TrimSpace(role),
		)
	}
}

func isMemberNotFound(err error) bool {
	return errors.Is(err, model.ErrMemberNotFound)
}

func isUserStateNotFound(err error) bool {
	return errors.Is(err, model.ErrUserStateNotFound)
}

func sourceEventTime(event CircleGroupChatSourceEvent) time.Time {
	if event.OccurredAt.IsZero() {
		return time.Now().UTC()
	}
	return event.OccurredAt.UTC()
}
