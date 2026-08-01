package gathering

import (
	"errors"
	"strings"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
)

type Gathering = contract.Gathering
type TargetRef = contract.GatheringTargetRef
type Participant = contract.GatheringParticipant
type Status = contract.GatheringStatus
type JoinPolicy = contract.GatheringJoinPolicy
type ParticipantState = contract.GatheringParticipantState

const (
	StatusDraft     = contract.GatheringStatusDraft
	StatusOpen      = contract.GatheringStatusOpen
	StatusFull      = contract.GatheringStatusFull
	StatusCancelled = contract.GatheringStatusCancelled
	StatusCompleted = contract.GatheringStatusCompleted

	JoinPolicyOpen     = contract.GatheringJoinPolicyOpen
	JoinPolicyApproval = contract.GatheringJoinPolicyApproval

	ParticipantStatePending  = contract.GatheringParticipantStatePending
	ParticipantStateJoined   = contract.GatheringParticipantStateJoined
	ParticipantStateLeft     = contract.GatheringParticipantStateLeft
	ParticipantStateRejected = contract.GatheringParticipantStateRejected
)

var ErrInvalidArgument = errors.New("invalid Gathering argument")

type CreateInput struct {
	ID               string
	CreatorPersonaID string
	Title            string
	Description      string
	TargetRef        TargetRef
	StartAt          time.Time
	EndAt            time.Time
	Capacity         int64
	JoinPolicy       JoinPolicy
	OccurredAt       time.Time
}

// Create starts in draft. The creator is the first joined participant, but no
// other participant may join until the chat conversation binding is durable.
func Create(input CreateInput) (Gathering, error) {
	id := strings.TrimSpace(input.ID)
	creator := strings.TrimSpace(input.CreatorPersonaID)
	title := strings.TrimSpace(input.Title)
	description := strings.TrimSpace(input.Description)
	target := normalizeTarget(input.TargetRef)
	if id == "" || creator == "" || title == "" || len([]rune(title)) > 120 ||
		len([]rune(description)) > 2000 || input.OccurredAt.IsZero() || input.StartAt.IsZero() ||
		input.Capacity < 2 || input.Capacity > 500 || !validTarget(target) ||
		!validJoinPolicy(input.JoinPolicy) {
		return Gathering{}, ErrInvalidArgument
	}
	if !input.EndAt.IsZero() && !input.EndAt.After(input.StartAt) {
		return Gathering{}, ErrInvalidArgument
	}
	now := input.OccurredAt.UTC()
	return Gathering{
		ID:                        id,
		Version:                   1,
		CreatorPersonaID:          creator,
		Title:                     title,
		Description:               description,
		TargetRef:                 target,
		StartAt:                   input.StartAt.UTC(),
		EndAt:                     utcOrZero(input.EndAt),
		Capacity:                  input.Capacity,
		JoinPolicy:                input.JoinPolicy,
		Status:                    StatusDraft,
		ConversationBindingStatus: contract.GatheringConversationBindingStatusPending,
		Participants: []Participant{{
			PersonaID:   creator,
			Role:        contract.GatheringParticipantRoleOwner,
			State:       ParticipantStateJoined,
			RequestedAt: now,
			DecidedAt:   now,
		}},
		CreatedAt: now,
		UpdatedAt: now,
	}, nil
}

// BindConversation is the idempotent saga completion point. Reusing the same
// conversation does not advance version; a different conversation is rejected.
func BindConversation(current Gathering, conversationID string, occurredAt time.Time) (Gathering, error) {
	conversationID = strings.TrimSpace(conversationID)
	if conversationID == "" || occurredAt.IsZero() {
		return Gathering{}, ErrInvalidArgument
	}
	if current.ConversationID != "" {
		if current.ConversationID == conversationID &&
			current.ConversationBindingStatus == contract.GatheringConversationBindingStatusBound {
			return current, nil
		}
		return Gathering{}, gatheringerrors.ErrGatheringConversationBindingFailed
	}
	if current.Status != StatusDraft {
		return Gathering{}, gatheringerrors.ErrGatheringNotOpen
	}
	next := current
	next.ConversationID = conversationID
	next.ConversationBindingStatus = contract.GatheringConversationBindingStatusBound
	next.Status = statusForCapacity(next)
	touch(&next, occurredAt)
	return next, nil
}

func MarkConversationBindingFailed(current Gathering, occurredAt time.Time) (Gathering, error) {
	if current.Status != StatusDraft || occurredAt.IsZero() {
		return Gathering{}, ErrInvalidArgument
	}
	if current.ConversationBindingStatus == contract.GatheringConversationBindingStatusFailed {
		return current, nil
	}
	next := current
	next.ConversationBindingStatus = contract.GatheringConversationBindingStatusFailed
	touch(&next, occurredAt)
	return next, nil
}

// Reevaluate completes an expired Gathering using endAt when present and
// startAt otherwise. Terminal states remain stable.
func Reevaluate(current Gathering, now time.Time) Gathering {
	if now.IsZero() || current.Status == StatusCancelled || current.Status == StatusCompleted {
		return current
	}
	deadline := current.EndAt
	if deadline.IsZero() {
		deadline = current.StartAt
	}
	if deadline.IsZero() || now.Before(deadline) {
		return current
	}
	next := current
	next.Status = StatusCompleted
	touch(&next, now)
	return next
}

// RequestJoin reserves a roster row before the conversation membership saga.
// The row remains pending until ConfirmJoin observes a successful idempotent
// Chat membership write. This prevents transport failures from fabricating a
// joined participant.
func RequestJoin(current Gathering, personaID string, occurredAt time.Time) (Gathering, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" || occurredAt.IsZero() {
		return Gathering{}, ErrInvalidArgument
	}
	current = Reevaluate(current, occurredAt)
	if current.Status == StatusCompleted || current.Status == StatusCancelled || current.Status == StatusDraft {
		return Gathering{}, gatheringerrors.ErrGatheringNotOpen
	}
	if index := participantIndex(current.Participants, personaID); index >= 0 {
		state := current.Participants[index].State
		if state == ParticipantStateJoined || state == ParticipantStatePending {
			return current, nil
		}
	}
	if current.Status == StatusFull || reservedCount(current) >= current.Capacity {
		return Gathering{}, gatheringerrors.ErrGatheringFull
	}
	next := current
	participant := Participant{
		PersonaID:   personaID,
		Role:        contract.GatheringParticipantRoleMember,
		State:       ParticipantStatePending,
		RequestedAt: occurredAt.UTC(),
		DecidedAt:   time.Time{},
	}
	if index := participantIndex(next.Participants, personaID); index >= 0 {
		next.Participants[index] = participant
	} else {
		next.Participants = append(next.Participants, participant)
	}
	next.Status = statusForCapacity(next)
	touch(&next, occurredAt)
	return next, nil
}

// ConfirmJoin advances one pending reservation only after Chat has confirmed
// the idempotent group-membership command.
func ConfirmJoin(current Gathering, personaID string, occurredAt time.Time) (Gathering, error) {
	if occurredAt.IsZero() {
		return Gathering{}, ErrInvalidArgument
	}
	current = Reevaluate(current, occurredAt)
	if current.Status != StatusOpen && current.Status != StatusFull {
		return Gathering{}, gatheringerrors.ErrGatheringNotOpen
	}
	index := participantIndex(current.Participants, strings.TrimSpace(personaID))
	if index < 0 {
		return Gathering{}, gatheringerrors.ErrGatheringParticipantStateInvalid
	}
	if current.Participants[index].State == ParticipantStateJoined {
		return current, nil
	}
	if current.Participants[index].State != ParticipantStatePending {
		return Gathering{}, gatheringerrors.ErrGatheringParticipantStateInvalid
	}
	if JoinedCount(current) >= current.Capacity {
		return Gathering{}, gatheringerrors.ErrGatheringFull
	}
	next := current
	next.Participants[index].State = ParticipantStateJoined
	next.Participants[index].DecidedAt = occurredAt.UTC()
	next.Status = statusForCapacity(next)
	touch(&next, occurredAt)
	return next, nil
}

// Join is the domain-only synchronous convenience used when no external
// membership transport participates. Application facades use RequestJoin and
// ConfirmJoin around the Chat port.
func Join(current Gathering, personaID string, occurredAt time.Time) (Gathering, error) {
	next, err := RequestJoin(current, personaID, occurredAt)
	if err != nil {
		return Gathering{}, err
	}
	if next.JoinPolicy == JoinPolicyApproval || participantState(next, personaID) == ParticipantStateJoined {
		return next, nil
	}
	return ConfirmJoin(next, personaID, occurredAt)
}

func Approve(current Gathering, actorPersonaID, participantPersonaID string, occurredAt time.Time) (Gathering, error) {
	if strings.TrimSpace(actorPersonaID) != current.CreatorPersonaID {
		return Gathering{}, gatheringerrors.ErrGatheringPermissionDenied
	}
	if occurredAt.IsZero() {
		return Gathering{}, ErrInvalidArgument
	}
	current = Reevaluate(current, occurredAt)
	if current.Status != StatusOpen && current.Status != StatusFull {
		return Gathering{}, gatheringerrors.ErrGatheringNotOpen
	}
	index := participantIndex(current.Participants, strings.TrimSpace(participantPersonaID))
	if index < 0 || current.Participants[index].State != ParticipantStatePending {
		return Gathering{}, gatheringerrors.ErrGatheringParticipantStateInvalid
	}
	if current.Status == StatusFull || JoinedCount(current) >= current.Capacity {
		return Gathering{}, gatheringerrors.ErrGatheringFull
	}
	next := current
	next.Participants[index].State = ParticipantStateJoined
	next.Participants[index].DecidedAt = occurredAt.UTC()
	next.Status = statusForCapacity(next)
	touch(&next, occurredAt)
	return next, nil
}

// Reject is a domain decision used by the approval workflow. It intentionally
// does not create a second public operation; the currently requested public
// command surface remains Create/Get/Join/Approve/Leave/Cancel/Complete.
func Reject(current Gathering, actorPersonaID, participantPersonaID string, occurredAt time.Time) (Gathering, error) {
	if strings.TrimSpace(actorPersonaID) != current.CreatorPersonaID {
		return Gathering{}, gatheringerrors.ErrGatheringPermissionDenied
	}
	index := participantIndex(current.Participants, strings.TrimSpace(participantPersonaID))
	if occurredAt.IsZero() || index < 0 || current.Participants[index].State != ParticipantStatePending {
		return Gathering{}, gatheringerrors.ErrGatheringParticipantStateInvalid
	}
	next := current
	next.Participants[index].State = ParticipantStateRejected
	next.Participants[index].DecidedAt = occurredAt.UTC()
	touch(&next, occurredAt)
	return next, nil
}

func Leave(current Gathering, personaID string, occurredAt time.Time) (Gathering, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == current.CreatorPersonaID {
		return Gathering{}, gatheringerrors.ErrGatheringPermissionDenied
	}
	if occurredAt.IsZero() {
		return Gathering{}, ErrInvalidArgument
	}
	current = Reevaluate(current, occurredAt)
	if current.Status != StatusOpen && current.Status != StatusFull {
		return Gathering{}, gatheringerrors.ErrGatheringNotOpen
	}
	index := participantIndex(current.Participants, personaID)
	if index < 0 || (current.Participants[index].State != ParticipantStateJoined && current.Participants[index].State != ParticipantStatePending) {
		return Gathering{}, gatheringerrors.ErrGatheringParticipantStateInvalid
	}
	next := current
	next.Participants[index].State = ParticipantStateLeft
	next.Participants[index].DecidedAt = occurredAt.UTC()
	next.Status = statusForCapacity(next)
	touch(&next, occurredAt)
	return next, nil
}

func Cancel(current Gathering, actorPersonaID string, occurredAt time.Time) (Gathering, error) {
	if strings.TrimSpace(actorPersonaID) != current.CreatorPersonaID {
		return Gathering{}, gatheringerrors.ErrGatheringPermissionDenied
	}
	if occurredAt.IsZero() {
		return Gathering{}, ErrInvalidArgument
	}
	if current.Status == StatusCancelled {
		return current, nil
	}
	if current.Status == StatusCompleted {
		return Gathering{}, gatheringerrors.ErrGatheringNotOpen
	}
	next := current
	next.Status = StatusCancelled
	touch(&next, occurredAt)
	return next, nil
}

func Complete(current Gathering, actorPersonaID string, occurredAt time.Time) (Gathering, error) {
	if strings.TrimSpace(actorPersonaID) != current.CreatorPersonaID {
		return Gathering{}, gatheringerrors.ErrGatheringPermissionDenied
	}
	if occurredAt.IsZero() {
		return Gathering{}, ErrInvalidArgument
	}
	if current.Status == StatusCompleted {
		return current, nil
	}
	if current.Status == StatusCancelled {
		return Gathering{}, gatheringerrors.ErrGatheringNotOpen
	}
	next := current
	next.Status = StatusCompleted
	touch(&next, occurredAt)
	return next, nil
}

func JoinedCount(current Gathering) int64 {
	var count int64
	for _, participant := range current.Participants {
		if participant.State == ParticipantStateJoined {
			count++
		}
	}
	return count
}

func reservedCount(current Gathering) int64 {
	var count int64
	for _, participant := range current.Participants {
		if participant.State == ParticipantStateJoined || participant.State == ParticipantStatePending {
			count++
		}
	}
	return count
}

func statusForCapacity(current Gathering) Status {
	if JoinedCount(current) >= current.Capacity {
		return StatusFull
	}
	return StatusOpen
}

func participantIndex(participants []Participant, personaID string) int {
	for index := range participants {
		if participants[index].PersonaID == personaID {
			return index
		}
	}
	return -1
}

func participantState(current Gathering, personaID string) ParticipantState {
	index := participantIndex(current.Participants, strings.TrimSpace(personaID))
	if index < 0 {
		return ParticipantState("")
	}
	return current.Participants[index].State
}

func touch(current *Gathering, occurredAt time.Time) {
	current.Version++
	current.UpdatedAt = occurredAt.UTC()
}

func validJoinPolicy(value JoinPolicy) bool {
	return value == JoinPolicyOpen || value == JoinPolicyApproval
}

func normalizeTarget(value TargetRef) TargetRef {
	value.ObjectTypeRef = strings.TrimSpace(value.ObjectTypeRef)
	value.ObjectID = strings.TrimSpace(value.ObjectID)
	value.RouteID = strings.TrimSpace(value.RouteID)
	return value
}

func validTarget(value TargetRef) bool {
	return value.ObjectTypeRef != "" && value.ObjectID != "" && value.RouteID != ""
}

func utcOrZero(value time.Time) time.Time {
	if value.IsZero() {
		return time.Time{}
	}
	return value.UTC()
}
