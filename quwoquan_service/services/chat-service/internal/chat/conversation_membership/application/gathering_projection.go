package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"time"

	generated "quwoquan_service/services/chat-service/generated/chat/conversation"
	membershipmodel "quwoquan_service/services/chat-service/internal/chat/conversation_membership/domain/model"
)

const (
	GatheringProjectionSourceOrganizerAssignment = "organizer_assignment"
	GatheringProjectionSourceParticipation       = "participation"
	GatheringProjectionSourceBlock               = "block"

	GatheringProjectionStateActive  = "active"
	GatheringProjectionStateClosed  = "closed"
	GatheringProjectionStateRevoked = "revoked"
	GatheringProjectionStateBlocked = "blocked"
	GatheringProjectionStateCleared = "cleared"

	GatheringAccessStatusActive  = "active"
	GatheringAccessStatusRevoked = "revoked"

	GatheringAccessRoleAdmin       = "admin"
	GatheringAccessRoleParticipant = "participant"
	GatheringAccessRoleNone        = "none"
)

type GatheringBinding struct {
	GatheringID    string
	ConversationID string
	Active         bool
}

type GatheringConversationReader interface {
	ReadGatheringConversation(context.Context, string) (GatheringBinding, bool, error)
}

type GatheringMemberStore interface {
	CreateMember(context.Context, *membershipmodel.Member) error
	DeleteMember(context.Context, string, string) error
	FindMember(context.Context, string, string) (*membershipmodel.Member, error)
	UpdateMemberRole(context.Context, string, string, string) error
	CountUserMembers(context.Context, string) (int, error)
}

type GatheringUserStateWriter interface {
	EnsureGatheringUserState(context.Context, string, string, time.Time) error
	DeleteGatheringUserState(context.Context, string, string) error
}

type GatheringRosterWriter interface {
	BumpGatheringRoster(context.Context, string, int) error
}

type GatheringProjectionTransaction interface {
	RunInTransaction(context.Context, func(context.Context) error) error
}

type GatheringMemberProfile struct {
	UserHandle    string
	DisplayName   string
	AvatarURL     string
	AvatarAssetID string
	AvatarVersion int64
}

type GatheringMemberProfileReader interface {
	ReadGatheringMemberProfile(context.Context, string) (GatheringMemberProfile, error)
}

type GatheringProjectionState struct {
	GatheringID    string
	ConversationID string
	PersonaID      string
	SourceType     string
	SourceVersion  int64
	State          string
	LastEventID    string
	UpdatedAt      time.Time
}

type GatheringProjectionStateStore interface {
	LoadGatheringProjectionState(context.Context, string, string, string) (GatheringProjectionState, bool, error)
	SaveGatheringProjectionState(context.Context, GatheringProjectionState) error
}

type GatheringOutboxEvent struct {
	EventID        string
	EventType      string
	AggregateID    string
	ConversationID string
	ActorID        string
	Payload        map[string]any
}

type GatheringProjectionOutbox interface {
	AppendGatheringProjectionEvents(
		context.Context,
		[]GatheringOutboxEvent,
		[]GatheringOutboxEvent,
	) error
}

type GatheringProjectionCommand struct {
	SourceEventID string
	SourceVersion int64
	GatheringID   string
	PersonaID     string
	SourceType    string
	State         string
}

type GatheringProjectionResult struct {
	GatheringID    string `json:"gatheringId"`
	ConversationID string `json:"conversationId"`
	PersonaID      string `json:"personaId"`
	SourceType     string `json:"sourceType"`
	State          string `json:"state"`
	AccessStatus   string `json:"accessStatus"`
	AccessRole     string `json:"accessRole"`
}

type GatheringProjectionFacade struct {
	transactions GatheringProjectionTransaction
	bindings     GatheringConversationReader
	members      GatheringMemberStore
	userStates   GatheringUserStateWriter
	roster       GatheringRosterWriter
	profiles     GatheringMemberProfileReader
	states       GatheringProjectionStateStore
	outbox       GatheringProjectionOutbox
	now          func() time.Time
}

func NewGatheringProjectionFacade(
	transactions GatheringProjectionTransaction,
	bindings GatheringConversationReader,
	members GatheringMemberStore,
	userStates GatheringUserStateWriter,
	roster GatheringRosterWriter,
	profiles GatheringMemberProfileReader,
	states GatheringProjectionStateStore,
	outbox GatheringProjectionOutbox,
) *GatheringProjectionFacade {
	if transactions == nil || bindings == nil || members == nil || userStates == nil || roster == nil ||
		profiles == nil || states == nil || outbox == nil {
		panic("Gathering membership projection requires all object ports")
	}
	return &GatheringProjectionFacade{
		transactions: transactions, bindings: bindings, members: members, userStates: userStates,
		roster: roster, profiles: profiles, states: states, outbox: outbox, now: time.Now,
	}
}

func (facade *GatheringProjectionFacade) Project(
	ctx context.Context,
	command GatheringProjectionCommand,
) (GatheringProjectionResult, error) {
	command.SourceEventID = strings.TrimSpace(command.SourceEventID)
	command.GatheringID = strings.TrimSpace(command.GatheringID)
	command.PersonaID = strings.TrimSpace(command.PersonaID)
	command.SourceType = strings.TrimSpace(command.SourceType)
	command.State = strings.TrimSpace(command.State)
	if command.SourceEventID == "" || command.SourceVersion <= 0 || command.GatheringID == "" ||
		command.PersonaID == "" || !validGatheringProjectionFact(command.SourceType, command.State) {
		return GatheringProjectionResult{}, generated.AppErrorFromInvalidArgument(
			"Gathering access source fact is incomplete or invalid",
		)
	}
	binding, found, err := facade.bindings.ReadGatheringConversation(ctx, command.GatheringID)
	if err != nil {
		return GatheringProjectionResult{}, err
	}
	if !found || !binding.Active {
		return GatheringProjectionResult{}, generated.AppErrorFromConversationNotFound(
			"active Gathering conversation binding is missing",
		)
	}

	result := GatheringProjectionResult{
		GatheringID: command.GatheringID, ConversationID: binding.ConversationID,
		PersonaID: command.PersonaID, SourceType: command.SourceType, State: command.State,
	}
	err = facade.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		current, currentFound, loadErr := facade.states.LoadGatheringProjectionState(
			txCtx, command.GatheringID, command.PersonaID, command.SourceType,
		)
		if loadErr != nil {
			return loadErr
		}
		if currentFound {
			if current.ConversationID != binding.ConversationID {
				return generated.AppErrorFromGatheringBindingConflict(
					"Gathering membership watermark points to another conversation",
				)
			}
			if current.SourceVersion > command.SourceVersion {
				result.State = current.State
				return facade.resolveGatheringAccess(txCtx, binding.ConversationID, command, nil, &result)
			}
			if current.SourceVersion == command.SourceVersion {
				if current.LastEventID != command.SourceEventID || current.State != command.State {
					return generated.AppErrorFromGatheringBindingConflict(
						"Gathering access version was reused by another source fact",
					)
				}
				return facade.resolveGatheringAccess(txCtx, binding.ConversationID, command, nil, &result)
			}
		}

		access, resolveErr := facade.loadGatheringAccess(txCtx, binding.ConversationID, command, &command)
		if resolveErr != nil {
			return resolveErr
		}
		result.AccessStatus = access.Status
		result.AccessRole = access.Role
		changed, membershipEvents, applyErr := facade.applyAccess(txCtx, binding, command, access)
		if applyErr != nil {
			return applyErr
		}
		if saveErr := facade.states.SaveGatheringProjectionState(txCtx, GatheringProjectionState{
			GatheringID: command.GatheringID, ConversationID: binding.ConversationID,
			PersonaID: command.PersonaID, SourceType: command.SourceType, SourceVersion: command.SourceVersion,
			State: command.State, LastEventID: command.SourceEventID, UpdatedAt: facade.now().UTC(),
		}); saveErr != nil {
			return saveErr
		}
		if !changed {
			return nil
		}
		count, countErr := facade.members.CountUserMembers(txCtx, binding.ConversationID)
		if countErr != nil {
			return countErr
		}
		for index := range membershipEvents {
			membershipEvents[index].Payload["memberCount"] = count
		}
		if rosterErr := facade.roster.BumpGatheringRoster(txCtx, binding.ConversationID, count); rosterErr != nil {
			return rosterErr
		}
		return facade.outbox.AppendGatheringProjectionEvents(
			txCtx,
			membershipEvents,
			[]GatheringOutboxEvent{{
				EventID:   projectionEventID(command.SourceEventID, "ConversationRosterUpdated"),
				EventType: "ConversationRosterUpdated", AggregateID: binding.ConversationID,
				ConversationID: binding.ConversationID, ActorID: "gathering_projector",
				Payload: map[string]any{
					"conversationId": binding.ConversationID, "memberCount": count,
					"aspects":   []string{"members", "gathering_projection"},
					"updatedAt": facade.now().UTC(),
				},
			}},
		)
	})
	return result, err
}

type gatheringResolvedAccess struct {
	Status string
	Role   string
}

func (facade *GatheringProjectionFacade) resolveGatheringAccess(
	ctx context.Context,
	conversationID string,
	command GatheringProjectionCommand,
	overlay *GatheringProjectionCommand,
	result *GatheringProjectionResult,
) error {
	access, err := facade.loadGatheringAccess(ctx, conversationID, command, overlay)
	if err != nil {
		return err
	}
	result.AccessStatus = access.Status
	result.AccessRole = access.Role
	return nil
}

func (facade *GatheringProjectionFacade) loadGatheringAccess(
	ctx context.Context,
	conversationID string,
	command GatheringProjectionCommand,
	overlay *GatheringProjectionCommand,
) (gatheringResolvedAccess, error) {
	states := map[string]string{}
	for _, sourceType := range []string{
		GatheringProjectionSourceOrganizerAssignment,
		GatheringProjectionSourceParticipation,
		GatheringProjectionSourceBlock,
	} {
		state, found, err := facade.states.LoadGatheringProjectionState(
			ctx, command.GatheringID, command.PersonaID, sourceType,
		)
		if err != nil {
			return gatheringResolvedAccess{}, err
		}
		if found {
			if state.ConversationID != "" && state.ConversationID != conversationID {
				return gatheringResolvedAccess{}, generated.AppErrorFromGatheringBindingConflict(
					"Gathering access watermark points to another conversation",
				)
			}
			states[sourceType] = state.State
		}
	}
	if overlay != nil {
		states[overlay.SourceType] = overlay.State
	}
	if states[GatheringProjectionSourceBlock] == GatheringProjectionStateBlocked {
		return gatheringResolvedAccess{Status: GatheringAccessStatusRevoked, Role: GatheringAccessRoleNone}, nil
	}
	if states[GatheringProjectionSourceOrganizerAssignment] == GatheringProjectionStateActive {
		return gatheringResolvedAccess{Status: GatheringAccessStatusActive, Role: GatheringAccessRoleAdmin}, nil
	}
	if states[GatheringProjectionSourceParticipation] == GatheringProjectionStateActive {
		return gatheringResolvedAccess{Status: GatheringAccessStatusActive, Role: GatheringAccessRoleParticipant}, nil
	}
	return gatheringResolvedAccess{Status: GatheringAccessStatusRevoked, Role: GatheringAccessRoleNone}, nil
}

func (facade *GatheringProjectionFacade) applyAccess(
	ctx context.Context,
	binding GatheringBinding,
	command GatheringProjectionCommand,
	access gatheringResolvedAccess,
) (bool, []GatheringOutboxEvent, error) {
	member, findErr := facade.members.FindMember(ctx, binding.ConversationID, command.PersonaID)
	if access.Status == GatheringAccessStatusActive {
		role := "member"
		if access.Role == GatheringAccessRoleAdmin {
			role = "admin"
		}
		if findErr == nil {
			if member.MemberType != "user" {
				return false, nil, generated.AppErrorFromGatheringBindingConflict(
					"Gathering access conflicts with a non-user Chat member",
				)
			}
			if member.Role == role {
				return false, nil, nil
			}
			if err := facade.members.UpdateMemberRole(ctx, binding.ConversationID, command.PersonaID, role); err != nil {
				return false, nil, err
			}
			member.Role = role
			return true, []GatheringOutboxEvent{{
				EventID:   projectionEventID(command.SourceEventID, "ConversationMemberRoleChanged"),
				EventType: "ConversationMemberRoleChanged", AggregateID: member.ID,
				ConversationID: binding.ConversationID, ActorID: "gathering_projector",
				Payload: map[string]any{
					"conversationId": binding.ConversationID, "memberId": member.ID,
					"userId": member.UserId, "role": member.Role, "changedBy": "gathering_projector",
				},
			}}, nil
		}
		if !errors.Is(findErr, membershipmodel.ErrNotFound) {
			return false, nil, findErr
		}
		profile, err := facade.profiles.ReadGatheringMemberProfile(ctx, command.PersonaID)
		if err != nil {
			return false, nil, err
		}
		joinedAt := facade.now().UTC()
		member = &membershipmodel.Member{
			ID:             deterministicMembershipID(command.GatheringID, command.PersonaID),
			ConversationId: binding.ConversationID, UserId: command.PersonaID,
			UserHandle: profile.UserHandle, DisplayName: profile.DisplayName,
			AvatarUrl: profile.AvatarURL, AvatarAssetId: profile.AvatarAssetID,
			AvatarVersion: profile.AvatarVersion, MemberType: "user", Role: role,
			InvitedBy: "gathering_projector", JoinedAt: joinedAt,
		}
		if err := facade.members.CreateMember(ctx, member); err != nil {
			return false, nil, err
		}
		if err := facade.userStates.EnsureGatheringUserState(
			ctx, command.PersonaID, binding.ConversationID, joinedAt,
		); err != nil {
			return false, nil, err
		}
		return true, []GatheringOutboxEvent{{
			EventID:   projectionEventID(command.SourceEventID, "ConversationMemberAdded"),
			EventType: "ConversationMemberAdded", AggregateID: member.ID,
			ConversationID: binding.ConversationID, ActorID: "gathering_projector",
			Payload: map[string]any{
				"conversationId": binding.ConversationID, "memberId": member.ID,
				"userId": member.UserId, "displayName": member.DisplayName,
				"memberType": member.MemberType, "role": member.Role,
				"invitedBy": member.InvitedBy, "joinedAt": member.JoinedAt,
			},
		}}, nil
	}

	if findErr != nil && !errors.Is(findErr, membershipmodel.ErrNotFound) {
		return false, nil, findErr
	}
	if member == nil {
		return false, nil, nil
	}
	if err := facade.members.DeleteMember(ctx, binding.ConversationID, command.PersonaID); err != nil {
		return false, nil, err
	}
	if err := facade.userStates.DeleteGatheringUserState(ctx, command.PersonaID, binding.ConversationID); err != nil {
		return false, nil, err
	}
	return true, []GatheringOutboxEvent{{
		EventID:   projectionEventID(command.SourceEventID, "ConversationMemberRemoved"),
		EventType: "ConversationMemberRemoved", AggregateID: member.ID,
		ConversationID: binding.ConversationID, ActorID: "gathering_projector",
		Payload: map[string]any{
			"conversationId": binding.ConversationID, "memberId": member.ID,
			"userId": member.UserId, "memberType": member.MemberType,
			"removedBy": "gathering_projector",
		},
	}}, nil
}

func validGatheringProjectionFact(sourceType, state string) bool {
	switch sourceType {
	case GatheringProjectionSourceOrganizerAssignment, GatheringProjectionSourceParticipation:
		return state == GatheringProjectionStateActive ||
			state == GatheringProjectionStateClosed ||
			state == GatheringProjectionStateRevoked
	case GatheringProjectionSourceBlock:
		return state == GatheringProjectionStateBlocked || state == GatheringProjectionStateCleared
	default:
		return false
	}
}

func deterministicMembershipID(gatheringID, personaID string) string {
	digest := sha256.Sum256([]byte("gathering-membership\x00" + gatheringID + "\x00" + personaID))
	return "member_" + hex.EncodeToString(digest[:12])
}

func projectionEventID(sourceEventID, eventType string) string {
	digest := sha256.Sum256([]byte(sourceEventID + "\x00" + eventType))
	return "chat_evt_" + hex.EncodeToString(digest[:16])
}
