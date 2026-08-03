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
	GatheringProjectionJoined = "joined"
	GatheringProjectionLeft   = "left"
)

type GatheringBinding struct {
	GatheringID    string
	ConversationID string
	OwnerPersonaID string
	MaxGroupSize   int
	Active         bool
}

type GatheringConversationReader interface {
	ReadGatheringConversation(context.Context, string) (GatheringBinding, bool, error)
}

type GatheringMemberStore interface {
	CreateMember(context.Context, *membershipmodel.Member) error
	DeleteMember(context.Context, string, string) error
	FindMember(context.Context, string, string) (*membershipmodel.Member, error)
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
	SourceVersion  int64
	State          string
	LastEventID    string
	UpdatedAt      time.Time
}

type GatheringProjectionStateStore interface {
	LoadGatheringProjectionState(context.Context, string, string) (GatheringProjectionState, bool, error)
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
	SourceEventID  string
	SourceVersion  int64
	GatheringID    string
	PersonaID      string
	OwnerPersonaID string
	State          string
}

type GatheringProjectionResult struct {
	GatheringID    string `json:"gatheringId"`
	ConversationID string `json:"conversationId"`
	PersonaID      string `json:"personaId"`
	State          string `json:"state"`
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
	command.OwnerPersonaID = strings.TrimSpace(command.OwnerPersonaID)
	command.State = strings.TrimSpace(command.State)
	if command.SourceEventID == "" || command.SourceVersion <= 0 || command.GatheringID == "" ||
		command.PersonaID == "" || command.OwnerPersonaID == "" ||
		(command.State != GatheringProjectionJoined && command.State != GatheringProjectionLeft) {
		return GatheringProjectionResult{}, generated.AppErrorFromInvalidArgument(
			"Gathering membership source fact is incomplete",
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
	if binding.OwnerPersonaID != command.OwnerPersonaID {
		return GatheringProjectionResult{}, generated.AppErrorFromGatheringBindingConflict(
			"Gathering owner differs from the Chat binding",
		)
	}
	if command.PersonaID == command.OwnerPersonaID && command.State != GatheringProjectionJoined {
		return GatheringProjectionResult{}, generated.AppErrorFromGatheringBindingConflict(
			"Gathering owner cannot be removed by participant projection",
		)
	}

	result := GatheringProjectionResult{
		GatheringID: command.GatheringID, ConversationID: binding.ConversationID,
		PersonaID: command.PersonaID, State: command.State,
	}
	profile := GatheringMemberProfile{}
	if command.State == GatheringProjectionJoined {
		profile, err = facade.profiles.ReadGatheringMemberProfile(ctx, command.PersonaID)
		if err != nil {
			return GatheringProjectionResult{}, err
		}
	}
	err = facade.transactions.RunInTransaction(ctx, func(txCtx context.Context) error {
		current, currentFound, loadErr := facade.states.LoadGatheringProjectionState(
			txCtx, command.GatheringID, command.PersonaID,
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
				return nil
			}
			if current.SourceVersion == command.SourceVersion {
				if current.LastEventID != command.SourceEventID || current.State != command.State {
					return generated.AppErrorFromGatheringBindingConflict(
						"Gathering participant version was reused by another source fact",
					)
				}
				return nil
			}
		}

		changed, membershipEvents, applyErr := facade.apply(
			txCtx, binding, command, profile,
		)
		if applyErr != nil {
			return applyErr
		}
		if saveErr := facade.states.SaveGatheringProjectionState(txCtx, GatheringProjectionState{
			GatheringID: command.GatheringID, ConversationID: binding.ConversationID,
			PersonaID: command.PersonaID, SourceVersion: command.SourceVersion,
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
		if count > binding.MaxGroupSize {
			return generated.AppErrorFromGatheringBindingConflict(
				"Gathering membership projection exceeded the Chat group capacity",
			)
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

func (facade *GatheringProjectionFacade) apply(
	ctx context.Context,
	binding GatheringBinding,
	command GatheringProjectionCommand,
	profile GatheringMemberProfile,
) (bool, []GatheringOutboxEvent, error) {
	member, findErr := facade.members.FindMember(ctx, binding.ConversationID, command.PersonaID)
	if command.State == GatheringProjectionJoined {
		if findErr == nil {
			if member.MemberType != "user" {
				return false, nil, generated.AppErrorFromGatheringBindingConflict(
					"Gathering participant conflicts with a non-user Chat member",
				)
			}
			return false, nil, nil
		}
		if !errors.Is(findErr, membershipmodel.ErrNotFound) {
			return false, nil, findErr
		}
		count, err := facade.members.CountUserMembers(ctx, binding.ConversationID)
		if err != nil {
			return false, nil, err
		}
		if count >= binding.MaxGroupSize {
			return false, nil, generated.AppErrorFromGatheringBindingConflict(
				"Gathering participant exceeds Chat group capacity",
			)
		}
		joinedAt := facade.now().UTC()
		member = &membershipmodel.Member{
			ID:             deterministicMembershipID(command.GatheringID, command.PersonaID),
			ConversationId: binding.ConversationID, UserId: command.PersonaID,
			UserHandle: profile.UserHandle, DisplayName: profile.DisplayName,
			AvatarUrl: profile.AvatarURL, AvatarAssetId: profile.AvatarAssetID,
			AvatarVersion: profile.AvatarVersion, MemberType: "user", Role: "member",
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
				"memberId": member.ID, "userId": member.UserId, "displayName": member.DisplayName,
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
		EventID:   projectionEventID(command.SourceEventID, "ConversationMemberLeft"),
		EventType: "ConversationMemberLeft", AggregateID: member.ID,
		ConversationID: binding.ConversationID, ActorID: "gathering_projector",
		Payload: map[string]any{
			"memberId": member.ID, "userId": member.UserId, "memberType": member.MemberType,
			"leftAt": facade.now().UTC(),
		},
	}}, nil
}

func deterministicMembershipID(gatheringID, personaID string) string {
	digest := sha256.Sum256([]byte("gathering-membership\x00" + gatheringID + "\x00" + personaID))
	return "member_" + hex.EncodeToString(digest[:12])
}

func projectionEventID(sourceEventID, eventType string) string {
	digest := sha256.Sum256([]byte(sourceEventID + "\x00" + eventType))
	return "chat_evt_" + hex.EncodeToString(digest[:16])
}
